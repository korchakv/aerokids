from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Contact, Organization


def normalize_phone(value: str) -> str:
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("380") and len(digits) == 12:
        national = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        national = digits[1:]
    elif len(digits) == 9:
        national = digits
    else:
        raise HTTPException(status_code=422, detail="Вкажіть український номер у форматі +380 XX XXX XX XX")

    if not re.fullmatch(r"[3-9]\d{8}", national):
        raise HTTPException(status_code=422, detail="Некоректний номер телефону України")
    return "+380" + national


def _require_organization(db: Session, org_id: UUID) -> Organization:
    organization = db.get(Organization, org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


def create_contact(db: Session, org_id: UUID, data) -> Contact:
    _require_organization(db, org_id)
    phone = normalize_phone(data.phone)
    existing = db.scalar(
        select(Contact).where(
            Contact.organization_id == org_id,
            Contact.phone == phone,
        )
    )
    if existing is not None:
        return existing
    item = Contact(
        organization_id=org_id,
        **data.model_dump(exclude={"phone"}),
        phone=phone,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_contacts(db: Session, org_id: UUID) -> list[Contact]:
    return list(
        db.scalars(
            select(Contact)
            .where(Contact.organization_id == org_id)
            .order_by(Contact.full_name)
        )
    )
