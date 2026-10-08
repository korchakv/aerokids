"""Core group CRUD domain service extracted from the legacy CRM facade."""

from __future__ import annotations

from datetime import time
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    Enrollment,
    EnrollmentStatus,
    Group,
    GroupSchedule,
    GroupStaff,
    LessonSession,
    LessonStatus,
    Location,
    MakeupCredit,
    Organization,
    StudentSubscription,
    SubscriptionUsage,
)
from app.services import audit_service


def _require_organization(db: Session, org_id: UUID) -> Organization:
    organization = db.get(Organization, org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


def _scoped_get(db: Session, model, org_id: UUID, item_id: UUID):
    item = db.scalar(select(model).where(model.id == item_id, model.organization_id == org_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def create_group(db: Session, org_id: UUID, data) -> Group:
    _require_organization(db, org_id)
    if data.location_id:
        _scoped_get(db, Location, org_id, data.location_id)
    if data.min_age and data.max_age and data.min_age > data.max_age:
        raise HTTPException(status_code=422, detail="min_age cannot be greater than max_age")
    item = Group(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_group(
    db: Session,
    org_id: UUID,
    group_id: UUID,
    data,
    actor_user_id: UUID | None = None,
) -> Group:
    group = _scoped_get(db, Group, org_id, group_id)
    if data.location_id is not None:
        _scoped_get(db, Location, org_id, data.location_id)

    enrolled_count = len(list(db.scalars(select(Enrollment.id).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    ))))
    if data.capacity < enrolled_count:
        raise HTTPException(
            status_code=422,
            detail=f"Місткість групи не може бути меншою за кількість учасників ({enrolled_count}).",
        )

    group.name = data.name
    group.location_id = data.location_id
    group.capacity = data.capacity
    group.min_age = data.min_age
    group.max_age = data.max_age

    existing_schedules = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
    )))
    schedules_by_key = {(item.weekday, item.start_time): item for item in existing_schedules}
    desired_keys: set[tuple[int, time]] = set()

    for slot in data.schedule_slots:
        slot_time = time.fromisoformat(slot.start_time)
        key = (slot.weekday, slot_time)
        desired_keys.add(key)
        existing = schedules_by_key.get(key)
        if existing is None:
            db.add(GroupSchedule(
                organization_id=org_id,
                group_id=group.id,
                weekday=slot.weekday,
                start_time=slot_time,
                duration_minutes=slot.duration_minutes,
                is_active=True,
            ))
        else:
            existing.duration_minutes = slot.duration_minutes
            existing.is_active = True

    for existing in existing_schedules:
        if (existing.weekday, existing.start_time) not in desired_keys:
            existing.is_active = False

    audit_service.record_audit(
        db,
        org_id,
        "group",
        group.id,
        "group.updated",
        {
            "name": group.name,
            "location_id": str(group.location_id) if group.location_id else None,
            "capacity": group.capacity,
            "schedule_slots": [
                {
                    "weekday": slot.weekday,
                    "start_time": slot.start_time,
                    "duration_minutes": slot.duration_minutes,
                }
                for slot in data.schedule_slots
            ],
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(group)
    return group


def delete_group(
    db: Session,
    org_id: UUID,
    group_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    group = _scoped_get(db, Group, org_id, group_id)

    enrollment = db.scalar(select(Enrollment.id).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
    ).limit(1))
    if enrollment is not None:
        raise HTTPException(
            status_code=409,
            detail="У цій групі є або були учні. Щоб не втратити історію навчання, таку групу видалити не можна.",
        )

    subscription = db.scalar(select(StudentSubscription.id).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.group_id == group.id,
    ).limit(1))
    if subscription is not None:
        raise HTTPException(
            status_code=409,
            detail="Ця група вже використовується в абонементах. Щоб не втратити фінансову історію, її видалити не можна.",
        )

    lessons = list(db.scalars(select(LessonSession).where(
        LessonSession.organization_id == org_id,
        LessonSession.group_id == group.id,
    )))
    completed_lesson = next((lesson for lesson in lessons if lesson.status == LessonStatus.COMPLETED), None)
    if completed_lesson is not None:
        raise HTTPException(
            status_code=409,
            detail="У цієї групи вже є проведене заняття. Щоб не втратити історію, таку групу видалити не можна.",
        )

    lesson_ids = [lesson.id for lesson in lessons]
    if lesson_ids:
        attendance = db.scalar(select(Attendance.id).where(
            Attendance.organization_id == org_id,
            Attendance.session_id.in_(lesson_ids),
        ).limit(1))
        if attendance is not None:
            raise HTTPException(
                status_code=409,
                detail="У заняттях цієї групи вже є відмітки відвідування. Щоб не втратити історію, групу видалити не можна.",
            )

        usage = db.scalar(select(SubscriptionUsage.id).where(
            SubscriptionUsage.organization_id == org_id,
            SubscriptionUsage.session_id.in_(lesson_ids),
        ).limit(1))
        if usage is not None:
            raise HTTPException(
                status_code=409,
                detail="Заняття цієї групи вже враховані в абонементах. Щоб не втратити історію, групу видалити не можна.",
            )

        makeup = db.scalar(select(MakeupCredit.id).where(
            MakeupCredit.organization_id == org_id,
            (MakeupCredit.original_session_id.in_(lesson_ids) | MakeupCredit.target_session_id.in_(lesson_ids)),
        ).limit(1))
        if makeup is not None:
            raise HTTPException(
                status_code=409,
                detail="Із заняттями цієї групи пов’язане відпрацювання. Спочатку завершіть або приберіть його.",
            )

    if lesson_ids:
        db.execute(delete(LessonSession).where(
            LessonSession.organization_id == org_id,
            LessonSession.group_id == group.id,
        ))

    db.execute(delete(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
    ))
    db.execute(delete(GroupStaff).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.group_id == group.id,
    ))
    db.flush()

    audit_service.record_audit(
        db,
        org_id,
        "group",
        group.id,
        "group.deleted",
        {
            "name": group.name,
            "removed_empty_lesson_placeholders": len(lesson_ids),
        },
        actor_user_id=actor_user_id,
    )
    db.delete(group)
    db.commit()


def list_groups(db: Session, org_id: UUID) -> list[Group]:
    return list(
        db.scalars(
            select(Group)
            .where(Group.organization_id == org_id, Group.is_active.is_(True))
            .order_by(Group.name)
        )
    )
