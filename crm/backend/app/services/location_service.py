from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Group, LessonSession, Location, StaffLocation, Student, TrialLesson
from app.services import audit_service, crm


def create_location(db: Session, org_id: UUID, data) -> Location:
    crm.require_organization(db, org_id)
    item = Location(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_locations(db: Session, org_id: UUID) -> list[Location]:
    return list(db.scalars(
        select(Location)
        .where(Location.organization_id == org_id, Location.is_active.is_(True))
        .order_by(Location.name)
    ))


def delete_location(
    db: Session,
    org_id: UUID,
    location_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    location = crm.scoped_get(db, Location, org_id, location_id)

    group = db.scalar(select(Group.id).where(
        Group.organization_id == org_id,
        Group.location_id == location.id,
    ).limit(1))
    if group is not None:
        raise HTTPException(
            status_code=409,
            detail="Цю локацію використовує група. Спочатку змініть локацію в групі або видаліть порожню групу.",
        )

    lesson = db.scalar(select(LessonSession.id).where(
        LessonSession.organization_id == org_id,
        LessonSession.location_id == location.id,
    ).limit(1))
    if lesson is not None:
        raise HTTPException(
            status_code=409,
            detail="Для цієї локації вже є заняття в історії або розкладі. Щоб не втратити дані, її видалити не можна.",
        )

    trial = db.scalar(select(TrialLesson.id).where(
        TrialLesson.organization_id == org_id,
        TrialLesson.location_id == location.id,
    ).limit(1))
    if trial is not None:
        raise HTTPException(
            status_code=409,
            detail="Для цієї локації вже є пробні заняття. Щоб не втратити історію, її видалити не можна.",
        )

    staff_link = db.scalar(select(StaffLocation.id).where(
        StaffLocation.organization_id == org_id,
        StaffLocation.location_id == location.id,
    ).limit(1))
    if staff_link is not None:
        raise HTTPException(
            status_code=409,
            detail="Ця локація призначена працівнику. Спочатку приберіть її в картці працівника.",
        )

    student_preference = db.scalar(select(Student.id).where(
        Student.organization_id == org_id,
        Student.preferred_location_id == location.id,
    ).limit(1))
    if student_preference is not None:
        raise HTTPException(
            status_code=409,
            detail="Ця локація вказана в побажаннях учня. Спочатку змініть бажану локацію в картці учня.",
        )

    audit_service.record_audit(
        db,
        org_id,
        "location",
        location.id,
        "location.deleted",
        {"name": location.name},
        actor_user_id=actor_user_id,
    )
    db.delete(location)
    db.commit()


def update_location(db: Session, org_id: UUID, location_id: UUID, data) -> Location:
    item = crm.scoped_get(db, Location, org_id, location_id)
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"]:
        duplicate = db.scalar(select(Location).where(
            Location.organization_id == org_id,
            Location.name == payload["name"],
            Location.id != location_id,
        ))
        if duplicate:
            raise HTTPException(status_code=409, detail="Location name already exists")
    for key, value in payload.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item
