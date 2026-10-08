from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    Group,
    GroupSchedule,
    GroupStaff,
    LessonSession,
    LessonStatus,
    Location,
    Organization,
    StaffRole,
)
from app.services import crm


def create_group_schedule(db: Session, org_id: UUID, data) -> GroupSchedule:
    crm.scoped_get(db, Group, org_id, data.group_id)
    item = GroupSchedule(
        organization_id=org_id,
        group_id=data.group_id,
        weekday=data.weekday,
        start_time=time.fromisoformat(data.start_time),
        duration_minutes=data.duration_minutes,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This group already has the same schedule slot") from exc
    db.refresh(item)
    return item


def list_group_schedules(
    db: Session,
    org_id: UUID,
    group_id: UUID | None = None,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> list[GroupSchedule]:
    allowed = crm.assigned_group_ids_for_user(db, org_id, user_id, role)
    stmt = select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.is_active.is_(True),
    )
    if group_id is not None:
        crm.ensure_group_access(db, org_id, user_id, role, group_id)
        stmt = stmt.where(GroupSchedule.group_id == group_id)
    elif allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(GroupSchedule.group_id.in_(allowed))
    return list(db.scalars(stmt.order_by(GroupSchedule.weekday, GroupSchedule.start_time)))


def comparable_dt(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(timezone_name))
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def lesson_conflict_reason(
    db: Session,
    org_id: UUID,
    group: Group,
    location_id: UUID | None,
    starts_at: datetime,
    duration_minutes: int,
) -> str | None:
    organization = crm.require_organization(db, org_id)
    start = comparable_dt(starts_at, organization.timezone)
    end = start + timedelta(minutes=duration_minutes)
    sessions = list(db.scalars(
        select(LessonSession).where(
            LessonSession.organization_id == org_id,
            LessonSession.status != LessonStatus.CANCELLED,
        )
    ))
    new_staff_ids = set(db.scalars(select(GroupStaff.staff_id).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.group_id == group.id,
    )))

    for existing in sessions:
        existing_start = comparable_dt(existing.starts_at, organization.timezone)
        existing_end = existing_start + timedelta(minutes=existing.duration_minutes)
        if not (start < existing_end and end > existing_start):
            continue

        existing_group = crm.scoped_get(db, Group, org_id, existing.group_id)
        same_group = existing.group_id == group.id
        same_location = bool(location_id and existing.location_id and location_id == existing.location_id)
        shared_staff = False
        if existing.group_id != group.id and new_staff_ids:
            existing_staff_ids = set(db.scalars(select(GroupStaff.staff_id).where(
                GroupStaff.organization_id == org_id,
                GroupStaff.group_id == existing.group_id,
            )))
            shared_staff = bool(new_staff_ids & existing_staff_ids)

        if same_group or same_location or shared_staff:
            reasons = []
            if same_group:
                reasons.append("ця група вже має заняття")
            if same_location:
                reasons.append("локація зайнята")
            if shared_staff:
                reasons.append("викладач зайнятий")
            return (
                f"Час зайнятий: {existing_group.name} "
                f"{existing_start.strftime('%d.%m %H:%M')}–{existing_end.strftime('%H:%M')} "
                f"({', '.join(reasons)}). Оберіть інший час."
            )
    return None


def materialize_recurring_lesson_sessions(
    db: Session,
    org_id: UUID,
    weeks_back: int = 0,
    weeks_forward: int = 8,
) -> int:
    """Create concrete lesson sessions from active recurring group schedules.

    Compatibility behavior is intentionally preserved here. Hardened read
    endpoints use the side-effect-free scheduling path in hardening services.
    """
    organization = db.get(Organization, org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        tz = ZoneInfo(organization.timezone)
    except Exception:
        tz = timezone.utc

    local_today = datetime.now(tz).date()
    current_monday = local_today - timedelta(days=local_today.weekday())
    window_start = current_monday - timedelta(weeks=weeks_back)
    window_end = current_monday + timedelta(weeks=weeks_forward + 1) - timedelta(days=1)

    schedules = list(db.scalars(
        select(GroupSchedule)
        .join(Group, Group.id == GroupSchedule.group_id)
        .where(
            GroupSchedule.organization_id == org_id,
            GroupSchedule.is_active.is_(True),
            Group.organization_id == org_id,
            Group.is_active.is_(True),
        )
        .order_by(GroupSchedule.group_id, GroupSchedule.weekday, GroupSchedule.start_time)
    ))
    if not schedules:
        return 0

    groups = {
        group.id: group
        for group in db.scalars(
            select(Group).where(
                Group.organization_id == org_id,
                Group.id.in_({slot.group_id for slot in schedules}),
            )
        )
    }

    created = 0
    for slot in schedules:
        group = groups.get(slot.group_id)
        if group is None:
            continue

        current_date = window_start + timedelta(days=slot.weekday)
        while current_date <= window_end:
            local_start = datetime.combine(current_date, slot.start_time).replace(tzinfo=tz)
            starts_at = local_start.astimezone(timezone.utc)
            exists = db.scalar(
                select(LessonSession.id).where(
                    LessonSession.organization_id == org_id,
                    LessonSession.group_id == group.id,
                    LessonSession.starts_at == starts_at,
                )
            )
            if exists is None:
                db.add(LessonSession(
                    organization_id=org_id,
                    group_id=group.id,
                    location_id=group.location_id,
                    starts_at=starts_at,
                    duration_minutes=slot.duration_minutes,
                    topic=None,
                    notes=None,
                    status=LessonStatus.SCHEDULED,
                ))
                created += 1
            current_date += timedelta(days=7)

    if created:
        db.commit()
    return created


def create_lesson_session(
    db: Session,
    org_id: UUID,
    data,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> LessonSession:
    group = crm.ensure_group_access(db, org_id, user_id, role, data.group_id)
    location_id = data.location_id if data.location_id is not None else group.location_id
    if location_id is not None:
        crm.scoped_get(db, Location, org_id, location_id)
    conflict = lesson_conflict_reason(
        db, org_id, group, location_id, data.starts_at, data.duration_minutes,
    )
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    item = LessonSession(
        organization_id=org_id,
        group_id=group.id,
        location_id=location_id,
        starts_at=data.starts_at,
        duration_minutes=data.duration_minutes,
        topic=data.topic,
        notes=data.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_lesson_sessions(
    db: Session,
    org_id: UUID,
    group_id: UUID | None = None,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> list[LessonSession]:
    materialize_recurring_lesson_sessions(db, org_id)
    allowed = crm.assigned_group_ids_for_user(db, org_id, user_id, role)
    stmt = select(LessonSession).where(LessonSession.organization_id == org_id)
    if group_id is not None:
        crm.ensure_group_access(db, org_id, user_id, role, group_id)
        stmt = stmt.where(LessonSession.group_id == group_id)
    elif allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(LessonSession.group_id.in_(allowed))
    rows = list(db.scalars(stmt.order_by(LessonSession.starts_at)))
    if not rows:
        return rows
    counts = {item.id: {"present": 0, "absent": 0, "late": 0, "excused": 0, "total": 0} for item in rows}
    for mark in db.scalars(select(Attendance).where(
        Attendance.organization_id == org_id,
        Attendance.session_id.in_(list(counts)),
    )):
        bucket = counts.get(mark.session_id)
        if bucket is None:
            continue
        key = mark.status.value
        if key in bucket:
            bucket[key] += 1
        bucket["total"] += 1
    for item in rows:
        summary = counts[item.id]
        item.attendance_present = summary["present"]
        item.attendance_absent = summary["absent"]
        item.attendance_late = summary["late"]
        item.attendance_excused = summary["excused"]
        item.attendance_total = summary["total"]
    return rows


def update_lesson_session(
    db: Session,
    org_id: UUID,
    session_id: UUID,
    data,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> LessonSession:
    item = crm.scoped_get(db, LessonSession, org_id, session_id)
    crm.ensure_group_access(db, org_id, user_id, role, item.group_id)
    changes = data.model_dump(exclude_unset=True)
    before = {"topic": item.topic, "notes": item.notes}
    if "topic" in changes:
        item.topic = changes["topic"]
    if "notes" in changes:
        item.notes = changes["notes"]
    crm.record_audit(
        db,
        org_id,
        "lesson_session",
        item.id,
        "lesson.details_updated",
        {"before": before, "after": {"topic": item.topic, "notes": item.notes}, "group_id": str(item.group_id)},
        actor_user_id=user_id,
    )
    db.commit()
    db.refresh(item)
    return item
