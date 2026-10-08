"""Scheduling domain service.

Owns group schedule reconciliation, room/staff resource conflicts, lesson session
creation/reads and schedule history.  The legacy CRM and hardening modules keep
thin compatibility wrappers so callers do not need to change in one release.\nAll read functions remain side-effect free; materialization is explicit.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
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
    Staff,
    StaffRole,
    TrialLesson,
    TrialStatus,
)
from app.models.hardening import (
    GroupRoomAssignment,
    GroupScheduleHistory,
    IndividualLessonSession,
    LessonResourceAssignment,
    Room,
    TrialResourceAssignment,
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


def organization_timezone(db: Session, org_id: UUID) -> ZoneInfo:
    organization = _require_organization(db, org_id)
    try:
        return ZoneInfo(organization.timezone)
    except Exception:
        return ZoneInfo("UTC")


def organization_today(db: Session, org_id: UUID) -> date:
    return datetime.now(organization_timezone(db, org_id)).date()


def local_date(db: Session, org_id: UUID, value: datetime) -> date:
    tz = organization_timezone(db, org_id)
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(tz).date()


def utc_naive(db: Session, org_id: UUID, value: datetime) -> datetime:
    tz = organization_timezone(db, org_id)
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def strict_group_ids_for_user(
    db: Session,
    org_id: UUID,
    user_id: UUID | None,
    role: StaffRole,
) -> set[UUID] | None:
    if role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER}:
        return None
    if role != StaffRole.TEACHER or user_id is None:
        return set()
    staff = db.scalar(select(Staff).where(
        Staff.organization_id == org_id,
        Staff.user_id == user_id,
        Staff.is_active.is_(True),
    ))
    if staff is None:
        return set()
    return set(db.scalars(select(GroupStaff.group_id).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff.id,
    )))


def ensure_group_access(
    db: Session,
    org_id: UUID,
    user_id: UUID | None,
    role: StaffRole,
    group_id: UUID,
) -> Group:
    group = _scoped_get(db, Group, org_id, group_id)
    allowed = strict_group_ids_for_user(db, org_id, user_id, role)
    if allowed is not None and group_id not in allowed:
        raise HTTPException(status_code=403, detail="Немає доступу до цієї групи")
    return group


def group_room_id(db: Session, org_id: UUID, group_id: UUID) -> UUID | None:
    return db.scalar(select(GroupRoomAssignment.room_id).where(
        GroupRoomAssignment.organization_id == org_id,
        GroupRoomAssignment.group_id == group_id,
    ))


def primary_group_staff_id(db: Session, org_id: UUID, group_id: UUID) -> UUID | None:
    return db.scalar(select(GroupStaff.staff_id).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.group_id == group_id,
    ).order_by(GroupStaff.is_primary.desc(), GroupStaff.id))


def _overlaps(start_a: datetime, duration_a: int, start_b: datetime, duration_b: int) -> bool:
    return start_a < start_b + timedelta(minutes=duration_b) and start_a + timedelta(minutes=duration_a) > start_b


def resource_conflict_reason(
    db: Session,
    org_id: UUID,
    starts_at: datetime,
    duration_minutes: int,
    location_id: UUID | None,
    room_id: UUID | None,
    staff_id: UUID | None,
    group_id: UUID | None = None,
    exclude_session_id: UUID | None = None,
    exclude_trial_id: UUID | None = None,
    exclude_individual_id: UUID | None = None,
) -> str | None:
    start = utc_naive(db, org_id, starts_at)

    sessions = list(db.scalars(select(LessonSession).where(
        LessonSession.organization_id == org_id,
        LessonSession.status != LessonStatus.CANCELLED,
    )))
    for session in sessions:
        if exclude_session_id is not None and session.id == exclude_session_id:
            continue
        existing_start = utc_naive(db, org_id, session.starts_at)
        if not _overlaps(start, duration_minutes, existing_start, session.duration_minutes):
            continue
        resources = db.scalar(select(LessonResourceAssignment).where(
            LessonResourceAssignment.organization_id == org_id,
            LessonResourceAssignment.session_id == session.id,
        ))
        existing_room = resources.room_id if resources else group_room_id(db, org_id, session.group_id)
        existing_staff = resources.staff_id if resources else primary_group_staff_id(db, org_id, session.group_id)
        same_group = bool(group_id is not None and session.group_id == group_id)
        same_staff = bool(staff_id is not None and existing_staff is not None and staff_id == existing_staff)
        same_room = bool(room_id is not None and existing_room is not None and room_id == existing_room)
        same_location_without_room = bool(
            location_id is not None
            and session.location_id is not None
            and location_id == session.location_id
            and (room_id is None or existing_room is None)
        )
        if same_group or same_staff or same_room or same_location_without_room:
            reasons: list[str] = []
            if same_group:
                reasons.append("група вже має заняття")
            if same_staff:
                reasons.append("викладач зайнятий")
            if same_room:
                reasons.append("кімната зайнята")
            elif same_location_without_room:
                reasons.append("локація зайнята")
            return f"Конфлікт розкладу ({', '.join(reasons)})"

    trials = list(db.scalars(select(TrialLesson).where(
        TrialLesson.organization_id == org_id,
        TrialLesson.status == TrialStatus.SCHEDULED,
    )))
    for trial in trials:
        if exclude_trial_id is not None and trial.id == exclude_trial_id:
            continue
        resources = db.scalar(select(TrialResourceAssignment).where(
            TrialResourceAssignment.organization_id == org_id,
            TrialResourceAssignment.trial_id == trial.id,
        ))
        trial_duration = resources.duration_minutes if resources else 60
        trial_start = utc_naive(db, org_id, trial.starts_at)
        if not _overlaps(start, duration_minutes, trial_start, trial_duration):
            continue
        trial_staff = resources.staff_id if resources else None
        trial_room = resources.room_id if resources else None
        same_staff = bool(staff_id is not None and trial_staff is not None and staff_id == trial_staff)
        same_room = bool(room_id is not None and trial_room is not None and room_id == trial_room)
        same_location_without_room = bool(
            location_id is not None
            and trial.location_id is not None
            and location_id == trial.location_id
            and (room_id is None or trial_room is None)
        )
        if same_staff or same_room or same_location_without_room:
            return "Конфлікт із пробним заняттям"

    individuals = list(db.scalars(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org_id,
        IndividualLessonSession.status != "cancelled",
    )))
    for lesson in individuals:
        if exclude_individual_id is not None and lesson.id == exclude_individual_id:
            continue
        individual_start = utc_naive(db, org_id, lesson.starts_at)
        if not _overlaps(start, duration_minutes, individual_start, lesson.duration_minutes):
            continue
        same_staff = bool(staff_id is not None and lesson.staff_id is not None and staff_id == lesson.staff_id)
        same_room = bool(room_id is not None and lesson.room_id is not None and room_id == lesson.room_id)
        same_location_without_room = bool(
            location_id is not None
            and lesson.location_id is not None
            and location_id == lesson.location_id
            and (room_id is None or lesson.room_id is None)
        )
        if same_staff or same_room or same_location_without_room:
            return "Конфлікт з індивідуальним заняттям"
    return None


def _slot_payload(rows: list[GroupSchedule]) -> list[dict]:
    return [{
        "weekday": row.weekday,
        "start_time": row.start_time.strftime("%H:%M"),
        "duration_minutes": row.duration_minutes,
    } for row in sorted(rows, key=lambda item: (item.weekday, item.start_time))]


def save_schedule_history(
    db: Session,
    org_id: UUID,
    group: Group,
    slots: list[GroupSchedule],
    actor_user_id: UUID | None,
    effective_from: date | None = None,
) -> GroupScheduleHistory:
    effective = effective_from or organization_today(db, org_id)
    open_version = db.scalar(select(GroupScheduleHistory).where(
        GroupScheduleHistory.organization_id == org_id,
        GroupScheduleHistory.group_id == group.id,
        GroupScheduleHistory.effective_to.is_(None),
    ).order_by(GroupScheduleHistory.created_at.desc()))
    payload = _slot_payload(slots)
    room_id = group_room_id(db, org_id, group.id)
    if open_version is not None and open_version.effective_from == effective:
        open_version.location_id = group.location_id
        open_version.room_id = room_id
        open_version.slots = payload
        open_version.created_by_user_id = actor_user_id
        return open_version
    if open_version is not None:
        open_version.effective_to = effective - timedelta(days=1)
    version = GroupScheduleHistory(
        organization_id=org_id,
        group_id=group.id,
        effective_from=effective,
        location_id=group.location_id,
        room_id=room_id,
        slots=payload,
        created_by_user_id=actor_user_id,
    )
    db.add(version)
    return version


def _future_group_sessions(db: Session, org_id: UUID, group_id: UUID) -> list[LessonSession]:
    today = organization_today(db, org_id)
    return [row for row in db.scalars(select(LessonSession).where(
        LessonSession.organization_id == org_id,
        LessonSession.group_id == group_id,
        LessonSession.status == LessonStatus.SCHEDULED,
    )) if local_date(db, org_id, row.starts_at) >= today]


def reconcile_group_future_sessions(
    db: Session,
    org_id: UUID,
    group: Group,
    actor_user_id: UUID | None,
    weeks_forward: int = 8,
) -> int:
    active_slots = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.is_active.is_(True),
    ).order_by(GroupSchedule.weekday, GroupSchedule.start_time)))
    slot_map = {(slot.weekday, slot.start_time): slot for slot in active_slots}
    today = organization_today(db, org_id)
    tz = organization_timezone(db, org_id)
    room_id = group_room_id(db, org_id, group.id)
    staff_id = primary_group_staff_id(db, org_id, group.id)

    for session in _future_group_sessions(db, org_id, group.id):
        local = session.starts_at
        if local.tzinfo is None:
            local = local.replace(tzinfo=timezone.utc)
        local = local.astimezone(tz)
        key = (local.weekday(), local.time().replace(second=0, microsecond=0, tzinfo=None))
        slot = slot_map.get(key)
        has_attendance = db.scalar(select(Attendance.id).where(
            Attendance.organization_id == org_id,
            Attendance.session_id == session.id,
        ).limit(1)) is not None
        if slot is None and not has_attendance:
            session.status = LessonStatus.CANCELLED
            continue
        if slot is not None and not has_attendance:
            conflict = resource_conflict_reason(
                db, org_id, session.starts_at, slot.duration_minutes, group.location_id, room_id, staff_id,
                group_id=group.id, exclude_session_id=session.id,
            )
            if conflict:
                raise HTTPException(status_code=409, detail=conflict)
            session.duration_minutes = slot.duration_minutes
            session.location_id = group.location_id
            resources = db.scalar(select(LessonResourceAssignment).where(
                LessonResourceAssignment.organization_id == org_id,
                LessonResourceAssignment.session_id == session.id,
            ))
            if resources is None:
                resources = LessonResourceAssignment(organization_id=org_id, session_id=session.id)
                db.add(resources)
            resources.room_id = room_id
            resources.staff_id = staff_id

    if not active_slots:
        return 0

    monday = today - timedelta(days=today.weekday())
    end_date = monday + timedelta(weeks=weeks_forward + 1) - timedelta(days=1)
    created = 0
    for slot in active_slots:
        current = monday + timedelta(days=slot.weekday)
        if current < today:
            current += timedelta(days=7)
        while current <= end_date:
            local_start = datetime.combine(current, slot.start_time).replace(tzinfo=tz)
            starts_at = local_start.astimezone(timezone.utc)
            existing = db.scalar(select(LessonSession).where(
                LessonSession.organization_id == org_id,
                LessonSession.group_id == group.id,
                LessonSession.starts_at == starts_at,
            ))
            if existing is not None:
                if existing.status == LessonStatus.CANCELLED:
                    has_history = db.scalar(select(Attendance.id).where(
                        Attendance.organization_id == org_id,
                        Attendance.session_id == existing.id,
                    ).limit(1)) is not None
                    if not has_history:
                        conflict = resource_conflict_reason(
                            db, org_id, starts_at, slot.duration_minutes, group.location_id, room_id, staff_id,
                            group_id=group.id, exclude_session_id=existing.id,
                        )
                        if conflict:
                            raise HTTPException(status_code=409, detail=conflict)
                        existing.status = LessonStatus.SCHEDULED
                        existing.duration_minutes = slot.duration_minutes
                        existing.location_id = group.location_id
                current += timedelta(days=7)
                continue
            conflict = resource_conflict_reason(
                db, org_id, starts_at, slot.duration_minutes, group.location_id, room_id, staff_id, group_id=group.id,
            )
            if conflict:
                raise HTTPException(status_code=409, detail=conflict)
            session = LessonSession(
                organization_id=org_id,
                group_id=group.id,
                location_id=group.location_id,
                starts_at=starts_at,
                duration_minutes=slot.duration_minutes,
                status=LessonStatus.SCHEDULED,
            )
            db.add(session)
            db.flush()
            db.add(LessonResourceAssignment(
                organization_id=org_id,
                session_id=session.id,
                room_id=room_id,
                staff_id=staff_id,
            ))
            created += 1
            current += timedelta(days=7)

    audit_service.record_audit(db, org_id, "group", group.id, "schedule.reconciled", {
        "created_sessions": created,
        "active_slots": _slot_payload(active_slots),
    }, actor_user_id=actor_user_id)
    return created



def materialize_recurring_lesson_sessions(
    db: Session,
    org_id: UUID,
    weeks_back: int = 0,
    weeks_forward: int = 8,
) -> int:
    """Materialize active recurring schedules outside read-only request paths.

    Kept for billing/maintenance compatibility.  Unlike the legacy implementation
    it uses the same room/staff/location conflict engine and snapshots resources.
    """
    organization = _require_organization(db, org_id)
    tz = organization_timezone(db, org_id)
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

    group_ids = {slot.group_id for slot in schedules}
    groups = {
        group.id: group
        for group in db.scalars(select(Group).where(
            Group.organization_id == org_id,
            Group.id.in_(group_ids),
        ))
    }

    created = 0
    for slot in schedules:
        group = groups.get(slot.group_id)
        if group is None:
            continue
        room_id = group_room_id(db, org_id, group.id)
        staff_id = primary_group_staff_id(db, org_id, group.id)
        current_date = window_start + timedelta(days=slot.weekday)
        while current_date <= window_end:
            local_start = datetime.combine(current_date, slot.start_time).replace(tzinfo=tz)
            starts_at = local_start.astimezone(timezone.utc)
            existing = db.scalar(select(LessonSession).where(
                LessonSession.organization_id == org_id,
                LessonSession.group_id == group.id,
                LessonSession.starts_at == starts_at,
            ))
            if existing is None:
                conflict = resource_conflict_reason(
                    db,
                    org_id,
                    starts_at,
                    slot.duration_minutes,
                    group.location_id,
                    room_id,
                    staff_id,
                    group_id=group.id,
                )
                if conflict:
                    raise HTTPException(status_code=409, detail=conflict)
                session = LessonSession(
                    organization_id=org_id,
                    group_id=group.id,
                    location_id=group.location_id,
                    starts_at=starts_at,
                    duration_minutes=slot.duration_minutes,
                    status=LessonStatus.SCHEDULED,
                )
                db.add(session)
                db.flush()
                db.add(LessonResourceAssignment(
                    organization_id=org_id,
                    session_id=session.id,
                    room_id=room_id,
                    staff_id=staff_id,
                ))
                created += 1
            current_date += timedelta(days=7)

    if created:
        db.commit()
    return created

def create_group_schedule(
    db: Session,
    org_id: UUID,
    data,
    actor_user_id: UUID | None = None,
) -> GroupSchedule:
    group = db.scalar(select(Group).where(
        Group.organization_id == org_id,
        Group.id == data.group_id,
    ).with_for_update())
    if group is None:
        raise HTTPException(status_code=404, detail="Групу не знайдено")
    slot_time = time.fromisoformat(data.start_time)
    row = db.scalar(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.weekday == data.weekday,
        GroupSchedule.start_time == slot_time,
    ))
    if row is None:
        row = GroupSchedule(
            organization_id=org_id,
            group_id=group.id,
            weekday=data.weekday,
            start_time=slot_time,
            duration_minutes=data.duration_minutes,
            is_active=True,
        )
        db.add(row)
    elif row.is_active:
        raise HTTPException(status_code=409, detail="Такий час уже є в розкладі групи")
    else:
        row.duration_minutes = data.duration_minutes
        row.is_active = True
    db.flush()
    active = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.is_active.is_(True),
    )))
    save_schedule_history(db, org_id, group, active, actor_user_id)
    reconcile_group_future_sessions(db, org_id, group, actor_user_id)
    db.commit()
    db.refresh(row)
    return row


def list_group_schedules(
    db: Session,
    org_id: UUID,
    group_id: UUID | None = None,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> list[GroupSchedule]:
    allowed = strict_group_ids_for_user(db, org_id, user_id, role)
    stmt = select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.is_active.is_(True),
    )
    if group_id is not None:
        ensure_group_access(db, org_id, user_id, role, group_id)
        stmt = stmt.where(GroupSchedule.group_id == group_id)
    elif allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(GroupSchedule.group_id.in_(allowed))
    return list(db.scalars(stmt.order_by(GroupSchedule.weekday, GroupSchedule.start_time)))


def list_lesson_sessions(
    db: Session,
    org_id: UUID,
    group_id: UUID | None = None,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> list[LessonSession]:
    """Side-effect free lesson query."""
    allowed = strict_group_ids_for_user(db, org_id, user_id, role)
    stmt = select(LessonSession).where(LessonSession.organization_id == org_id)
    if group_id is not None:
        ensure_group_access(db, org_id, user_id, role, group_id)
        stmt = stmt.where(LessonSession.group_id == group_id)
    elif allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(LessonSession.group_id.in_(allowed))
    rows = list(db.scalars(stmt.order_by(LessonSession.starts_at)))
    if not rows:
        return rows

    counts = {row.id: {"present": 0, "absent": 0, "late": 0, "excused": 0, "total": 0} for row in rows}
    for mark in db.scalars(select(Attendance).where(
        Attendance.organization_id == org_id,
        Attendance.session_id.in_(list(counts)),
    )):
        bucket = counts[mark.session_id]
        key = mark.status.value
        if key in bucket:
            bucket[key] += 1
        bucket["total"] += 1
    for row in rows:
        summary = counts[row.id]
        row.attendance_present = summary["present"]
        row.attendance_absent = summary["absent"]
        row.attendance_late = summary["late"]
        row.attendance_excused = summary["excused"]
        row.attendance_total = summary["total"]
    return rows


def create_lesson_session(
    db: Session,
    org_id: UUID,
    data,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> LessonSession:
    group = ensure_group_access(db, org_id, user_id, role, data.group_id)
    location_id = data.location_id if data.location_id is not None else group.location_id
    if location_id is not None:
        _scoped_get(db, Location, org_id, location_id)

    room_id = getattr(data, "room_id", None) or group_room_id(db, org_id, group.id)
    if room_id is not None:
        room = _scoped_get(db, Room, org_id, room_id)
        if location_id is not None and room.location_id != location_id:
            raise HTTPException(status_code=409, detail="Кімната належить іншій локації")

    staff_id = getattr(data, "staff_id", None) or primary_group_staff_id(db, org_id, group.id)
    if staff_id is not None:
        staff = _scoped_get(db, Staff, org_id, staff_id)
        if not staff.is_active or not staff.can_teach:
            raise HTTPException(status_code=409, detail="Обраний працівник не може вести заняття")

    conflict = resource_conflict_reason(
        db,
        org_id,
        data.starts_at,
        data.duration_minutes,
        location_id,
        room_id,
        staff_id,
        group_id=group.id,
    )
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)

    session = LessonSession(
        organization_id=org_id,
        group_id=group.id,
        location_id=location_id,
        starts_at=data.starts_at,
        duration_minutes=data.duration_minutes,
        topic=data.topic,
        notes=data.notes,
        status=LessonStatus.SCHEDULED,
    )
    db.add(session)
    db.flush()
    db.add(LessonResourceAssignment(
        organization_id=org_id,
        session_id=session.id,
        staff_id=staff_id,
        room_id=room_id,
    ))
    audit_service.record_audit(
        db,
        org_id,
        "lesson_session",
        session.id,
        "lesson.created_hardened",
        {
            "group_id": str(group.id),
            "staff_id": str(staff_id) if staff_id else None,
            "room_id": str(room_id) if room_id else None,
        },
        actor_user_id=user_id,
    )
    db.commit()
    db.refresh(session)
    return session


def update_lesson_session(
    db: Session,
    org_id: UUID,
    session_id: UUID,
    data,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> LessonSession:
    item = _scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, item.group_id)
    changes = data.model_dump(exclude_unset=True)
    before = {"topic": item.topic, "notes": item.notes}
    if "topic" in changes:
        item.topic = changes["topic"]
    if "notes" in changes:
        item.notes = changes["notes"]
    audit_service.record_audit(
        db,
        org_id,
        "lesson_session",
        item.id,
        "lesson.details_updated",
        {
            "before": before,
            "after": {"topic": item.topic, "notes": item.notes},
            "group_id": str(item.group_id),
        },
        actor_user_id=user_id,
    )
    db.commit()
    db.refresh(item)
    return item
