from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.hardening_extensions import NotificationOutbox
from app.db.session import SessionLocal


logger = logging.getLogger("schoolcrm.notifications")


def enqueue(
    db: Session,
    org_id: UUID,
    kind: str,
    recipient: str,
    template_key: str,
    payload: dict,
) -> NotificationOutbox:
    row = NotificationOutbox(
        organization_id=org_id,
        kind=kind,
        recipient=recipient.strip().lower(),
        template_key=template_key,
        payload=payload,
        status="pending",
    )
    db.add(row)
    return row


def _expiry_payload(expires_at: datetime | None) -> dict:
    if expires_at is None:
        return {}
    utc_expiry = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at.astimezone(timezone.utc)
    return {"expires_at": utc_expiry.isoformat()}


def enqueue_invitation(db: Session, org_id: UUID, recipient: str, raw_token: str, organization_name: str, *, expires_at: datetime | None = None) -> NotificationOutbox:
    link = f"{settings.frontend_url.rstrip('/')}?invite={raw_token}"
    return enqueue(db, org_id, "auth", recipient, "staff_invitation", {
        "organization_name": organization_name,
        "link": link,
        **_expiry_payload(expires_at),
    })


def enqueue_password_reset(db: Session, org_id: UUID, recipient: str, raw_token: str, organization_name: str, *, expires_at: datetime | None = None) -> NotificationOutbox:
    link = f"{settings.frontend_url.rstrip('/')}?reset={raw_token}"
    return enqueue(db, org_id, "auth", recipient, "password_reset", {
        "organization_name": organization_name,
        "link": link,
        **_expiry_payload(expires_at),
    })


def _render(row: NotificationOutbox) -> tuple[str, str]:
    organization = row.payload.get("organization_name") or "CRM"
    link = row.payload.get("link") or ""
    if row.template_key == "staff_invitation":
        return (
            f"Запрошення до {organization}",
            f"Вас запросили до CRM організації «{organization}».\n\nВідкрити одноразове запрошення:\n{link}\n",
        )
    if row.template_key == "password_reset":
        return (
            f"Зміна пароля — {organization}",
            f"Для вашого облікового запису створено одноразове посилання для зміни пароля.\n\n{link}\n",
        )
    return ("Повідомлення CRM", str(row.payload))


def deliver_pending(db: Session, limit: int = 50, *, organization_id: UUID | None = None, outbox_id: UUID | None = None) -> dict:
    enabled = settings.transactional_email_enabled
    scope = [NotificationOutbox.status.in_(["pending", "failed"])]
    if organization_id is not None:
        scope.append(NotificationOutbox.organization_id == organization_id)
    if outbox_id is not None:
        scope.append(NotificationOutbox.id == outbox_id)
    expired_filter = NotificationOutbox.payload["expires_at"].as_string() <= datetime.now(timezone.utc).isoformat()
    # Expired credentials must be scrubbed even while SMTP is disabled.
    eligible = [*scope, or_(NotificationOutbox.attempts < 5, expired_filter) if enabled else expired_filter]
    ids = list(db.scalars(select(NotificationOutbox.id).where(*eligible)
                          .order_by(NotificationOutbox.created_at).limit(limit)))
    sent = 0
    failed = 0
    expired = 0
    for row_id in ids:
        # Claim each row separately: committing the preceding delivery must not
        # release locks for messages we have yet to send.
        row = db.scalar(select(NotificationOutbox).where(
            NotificationOutbox.id == row_id, *eligible,
        ).with_for_update(skip_locked=True))
        if row is None:
            continue
        expiry = row.payload.get("expires_at")
        if expiry:
            expires_at = datetime.fromisoformat(expiry)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                row.status = "expired"
                row.payload = {"expired": True, "template_key": row.template_key}
                row.last_error = None
                db.commit()
                expired += 1
                continue
        if not enabled:
            continue
        try:
            subject, body = _render(row)
            message = EmailMessage()
            message["From"] = settings.smtp_from_email
            message["To"] = row.recipient
            message["Subject"] = subject
            message.set_content(body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password or "")
                smtp.send_message(message)
            row.status = "sent"
            row.sent_at = datetime.now(timezone.utc)
            row.last_error = None
            # The one-time credential is no longer needed after successful
            # delivery; remove it from persistent outbox storage.
            row.payload = {"delivered": True, "template_key": row.template_key}
            sent += 1
        except Exception as exc:
            row.status = "failed"
            # Provider exception text may contain recipient or credential data.
            row.last_error = type(exc).__name__
            failed += 1
        finally:
            row.attempts += 1
            db.commit()
    pending = db.scalar(select(func.count()).select_from(NotificationOutbox).where(
        *scope, NotificationOutbox.attempts < 5,
    )) or 0
    return {"enabled": enabled, "sent": sent, "failed": failed, "expired": expired, "pending": pending}


def deliver_one(organization_id: UUID, outbox_id: UUID) -> None:
    """Try delivery after commit, using a session independent of the HTTP request."""
    if not settings.transactional_email_enabled or settings.read_only_mode:
        return
    with SessionLocal() as db:
        result = deliver_pending(db, limit=1, organization_id=organization_id, outbox_id=outbox_id)
        if result["failed"]:
            logger.warning("credential_email_delivery_failed")
