from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import Organization, Payment
from app.services import audit_service


def create_organization(db: Session, data) -> Organization:
    item = Organization(**data.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Organization slug already exists") from exc
    db.refresh(item)
    return item


def list_organizations(db: Session) -> list[Organization]:
    return list(db.scalars(select(Organization).order_by(Organization.name)))


def update_organization(
    db: Session,
    org_id: UUID,
    data,
    actor_user_id: UUID | None = None,
) -> Organization:
    item = require_organization(db, org_id)
    updates = data.model_dump(exclude_none=True)

    next_currency = updates.get("currency")
    if next_currency and next_currency != item.currency:
        has_payments = db.scalar(
            select(Payment.id).where(Payment.organization_id == org_id).limit(1)
        ) is not None
        if has_payments:
            raise HTTPException(
                status_code=409,
                detail="Organization currency cannot be changed after payments have been created",
            )

    for key, value in updates.items():
        setattr(item, key, value)
    audit_service.record_audit(
        db,
        org_id,
        "organization",
        item.id,
        "organization.settings_updated",
        updates,
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(item)
    return item


def require_organization(db: Session, org_id: UUID) -> Organization:
    item = db.get(Organization, org_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return item
