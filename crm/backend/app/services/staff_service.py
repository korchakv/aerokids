from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    Group,
    GroupStaff,
    Location,
    OrganizationMembership,
    Staff,
    StaffLocation,
    StaffRole,
    User,
)
from app.services import crm


def create_staff(db: Session, org_id: UUID, data) -> Staff:
    crm.require_organization(db, org_id)
    if data.email:
        existing = db.scalar(select(Staff).where(Staff.organization_id == org_id, Staff.email == data.email))
        if existing:
            raise HTTPException(status_code=409, detail="Staff email already exists in this organization")
    locations = []
    for location_id in data.location_ids:
        locations.append(crm.scoped_get(db, Location, org_id, location_id))
    item = Staff(
        organization_id=org_id,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        role=data.role,
        can_teach=data.can_teach or data.role == StaffRole.TEACHER,
        notes=data.notes,
    )
    db.add(item)
    db.flush()
    for location in locations:
        db.add(StaffLocation(
            organization_id=org_id,
            staff_id=item.id,
            location_id=location.id,
        ))
    db.commit()
    db.refresh(item)
    return item


def list_staff(db: Session, org_id: UUID, active_only: bool = True) -> list[Staff]:
    stmt = select(Staff).where(Staff.organization_id == org_id)
    if active_only:
        stmt = stmt.where(Staff.is_active.is_(True))
    return list(db.scalars(stmt.order_by(Staff.full_name)))


def update_staff(db: Session, org_id: UUID, staff_id: UUID, data) -> Staff:
    item = crm.scoped_get(db, Staff, org_id, staff_id)
    payload = data.model_dump(exclude_unset=True)
    if "email" in payload and payload["email"]:
        duplicate = db.scalar(select(Staff).where(
            Staff.organization_id == org_id,
            Staff.email == payload["email"],
            Staff.id != staff_id,
        ))
        if duplicate:
            raise HTTPException(status_code=409, detail="Staff email already exists in this organization")
    next_role = payload.get("role", item.role)
    next_can_teach = payload.get("can_teach", item.can_teach)
    if next_role == StaffRole.TEACHER:
        next_can_teach = True
        payload["can_teach"] = True
    if item.can_teach and not next_can_teach:
        assigned_group = db.scalar(select(GroupStaff.id).where(
            GroupStaff.organization_id == org_id,
            GroupStaff.staff_id == staff_id,
        ).limit(1))
        if assigned_group is not None:
            raise HTTPException(status_code=409, detail="Remove this staff member from teaching groups before disabling teaching")
    for key, value in payload.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def set_staff_locations(db: Session, org_id: UUID, staff_id: UUID, location_ids: list[UUID]) -> Staff:
    item = crm.scoped_get(db, Staff, org_id, staff_id)
    unique_ids = list(dict.fromkeys(location_ids))
    for location_id in unique_ids:
        crm.scoped_get(db, Location, org_id, location_id)

    existing = list(db.scalars(select(StaffLocation).where(
        StaffLocation.organization_id == org_id,
        StaffLocation.staff_id == staff_id,
    )))
    for row in existing:
        db.delete(row)
    for location_id in unique_ids:
        db.add(StaffLocation(
            organization_id=org_id,
            staff_id=staff_id,
            location_id=location_id,
        ))
    db.commit()
    db.refresh(item)
    return item


def assign_staff_to_group(
    db: Session,
    org_id: UUID,
    staff_id: UUID,
    group_id: UUID,
    is_primary: bool = False,
) -> GroupStaff:
    staff = crm.scoped_get(db, Staff, org_id, staff_id)
    crm.scoped_get(db, Group, org_id, group_id)
    if not staff.is_active:
        raise HTTPException(status_code=409, detail="Inactive staff member cannot be assigned")
    if not staff.can_teach:
        raise HTTPException(status_code=409, detail="Staff member is not marked as able to teach")

    existing = db.scalar(select(GroupStaff).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff_id,
        GroupStaff.group_id == group_id,
    ))

    if is_primary:
        primary_rows = list(db.scalars(select(GroupStaff).where(
            GroupStaff.organization_id == org_id,
            GroupStaff.group_id == group_id,
            GroupStaff.is_primary.is_(True),
        )))
        for row in primary_rows:
            if row.staff_id != staff_id:
                row.is_primary = False

    if existing:
        existing.is_primary = is_primary
        db.commit()
        db.refresh(existing)
        return existing

    item = GroupStaff(
        organization_id=org_id,
        staff_id=staff_id,
        group_id=group_id,
        is_primary=is_primary,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def staff_profile(db: Session, org_id: UUID, staff_id: UUID):
    item = crm.scoped_get(db, Staff, org_id, staff_id)
    location_ids = list(db.scalars(select(StaffLocation.location_id).where(
        StaffLocation.organization_id == org_id,
        StaffLocation.staff_id == staff_id,
    )))
    group_ids = list(db.scalars(select(GroupStaff.group_id).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff_id,
    )))
    return item, location_ids, group_ids


def create_membership(db: Session, org_id: UUID, data):
    crm.require_organization(db, org_id)
    normalized_email = data.email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        user = User(email=normalized_email, full_name=data.full_name)
        db.add(user)
        db.flush()

    existing = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.user_id == user.id,
    ))
    if existing:
        existing.role = data.role
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing, user

    membership = OrganizationMembership(
        organization_id=org_id,
        user_id=user.id,
        role=data.role,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership, user
