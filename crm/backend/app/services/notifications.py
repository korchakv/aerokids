from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.hardening_extensions import NotificationOutbox


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


def enqueue_invitation(db: Session, org_id: UUID, recipient: str, raw_token: str, organization_name: str) -> NotificationOutbox:
    link = f"{settings.frontend_url.rstrip('/')}?invite={raw_token}"
    return enqueue(db, org_id, "auth", recipient, "staff_invitation", {
        "organization_name": organization_name,
        "link": link,
    })


def enqueue_password_reset(db: Session, org_id: UUID, recipient: str, raw_token: str, organization_name: str) -> NotificationOutbox:
    link = f"{settings.frontend_url.rstrip('/')}?reset={raw_token}"
    return enqueue(db, org_id, "auth", recipient, "password_reset", {
        "organization_name": organization_name,
        "link": link,
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


def deliver_pending(db: Session, limit: int = 50) -> dict:
    if not settings.transactional_email_enabled:
        return {"enabled": False, "sent": 0, "failed": 0, "pending": 0}

    rows = list(db.scalars(select(NotificationOutbox).where(
        NotificationOutbox.status.in_(["pending", "failed"]),
        NotificationOutbox.attempts < 5,
    ).order_by(NotificationOutbox.created_at).limit(limit)))
    sent = 0
    failed = 0
    for row in rows:
        subject, body = _render(row)
        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = row.recipient
        message["Subject"] = subject
        message.set_content(body)
        try:
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
            row.last_error = str(exc)[:500]
            failed += 1
        finally:
            row.attempts += 1
            db.commit()
    return {"enabled": True, "sent": sent, "failed": failed, "pending": len(rows) - sent - failed}
