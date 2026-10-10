from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    AttendanceStatus,
    Contact,
    CrmStatus,
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
    OrganizationMembership,
    Payment,
    PaymentStatus,
    PaymentTransaction,
    Staff,
    StaffLocation,
    StaffRole,
    Student,
    StudentAvailability,
    StudentStatus,
    StudentSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
    SubscriptionUsage,
    TrialLesson,
    TrialStatus,
    User,
)
from app.models.hardening import (
    EnrollmentHistory,
    GroupRoomAssignment,
    GroupScheduleHistory,
    IndividualAttendance,
    IndividualLessonSession,
    IndividualSubscriptionUsage,
    LessonDerivedBilling,
    LessonFinalization,
    LessonResourceAssignment,
    MakeupCompletionLink,
    Room,
    StaffCapability,
    TrialResourceAssignment,
)
from app.services import crm
from app.services.schedule_matching import enrollment_schedule_note, evaluate_schedule_match


ROLE_CAPABILITIES: dict[StaffRole, set[str]] = {
    StaffRole.OWNER: {"*"},
    StaffRole.ADMIN: {
        "leads.manage", "students.manage", "groups.manage", "schedule.manage", "attendance.manage",
        "finance.view", "finance.manage", "staff.manage", "settings.manage", "reports.view", "teaching",
    },
    StaffRole.MANAGER: {
        "leads.manage", "students.manage", "groups.manage", "schedule.manage", "attendance.manage",
        "reports.view", "teaching",
    },
    StaffRole.TEACHER: {"attendance.manage", "teaching"},
    StaffRole.ACCOUNTANT: {"finance.view", "finance.manage", "reports.view"},
}


def organization_timezone(db: Session, org_id: UUID) -> ZoneInfo:
    organization = crm.require_organization(db, org_id)
    try:
        return ZoneInfo(organization.timezone)
    except Exception:
        return ZoneInfo("UTC")


def organization_today(db: Session, org_id: UUID) -> date:
    return datetime.now(organization_timezone(db, org_id)).date()


def _local_date(db: Session, org_id: UUID, value: datetime) -> date:
    tz = organization_timezone(db, org_id)
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(tz).date()


def _utc_naive(db: Session, org_id: UUID, value: datetime) -> datetime:
    tz = organization_timezone(db, org_id)
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def strict_group_ids_for_user(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole) -> set[UUID] | None:
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


def ensure_group_access(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole, group_id: UUID) -> Group:
    group = crm.scoped_get(db, Group, org_id, group_id)
    allowed = strict_group_ids_for_user(db, org_id, user_id, role)
    if allowed is not None and group_id not in allowed:
        raise HTTPException(status_code=403, detail="Немає доступу до цієї групи")
    return group


def staff_for_user(db: Session, org_id: UUID, user_id: UUID | None) -> Staff | None:
    if user_id is None:
        return None
    return db.scalar(select(Staff).where(
        Staff.organization_id == org_id,
        Staff.user_id == user_id,
        Staff.is_active.is_(True),
    ))


def has_capability(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole, capability: str) -> bool:
    base = "*" in ROLE_CAPABILITIES.get(role, set()) or capability in ROLE_CAPABILITIES.get(role, set())
    staff = staff_for_user(db, org_id, user_id)
    if staff is None:
        return base
    override = db.scalar(select(StaffCapability).where(
        StaffCapability.organization_id == org_id,
        StaffCapability.staff_id == staff.id,
        StaffCapability.capability == capability,
    ))
    return override.allowed if override is not None else base


def _ensure_not_last_owner(db: Session, org_id: UUID, membership: OrganizationMembership, next_role: StaffRole, next_active: bool) -> None:
    if membership.role != StaffRole.OWNER:
        return
    if next_active and next_role == StaffRole.OWNER:
        return
    other_owner = db.scalar(select(OrganizationMembership.id).where(
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.role == StaffRole.OWNER,
        OrganizationMembership.is_active.is_(True),
        OrganizationMembership.id != membership.id,
    ).limit(1))
    if other_owner is None:
        raise HTTPException(status_code=409, detail="Не можна забрати доступ у єдиного власника організації")


def update_staff_and_access(
    db: Session,
    org_id: UUID,
    staff_id: UUID,
    data,
    actor_user_id: UUID | None,
) -> Staff:
    staff = crm.scoped_get(db, Staff, org_id, staff_id)
    payload = data.model_dump(exclude_unset=True)
    before = {
        "full_name": staff.full_name,
        "email": staff.email,
        "role": staff.role.value,
        "can_teach": staff.can_teach,
        "is_active": staff.is_active,
    }

    if payload.get("email"):
        duplicate = db.scalar(select(Staff.id).where(
            Staff.organization_id == org_id,
            Staff.email == payload["email"],
            Staff.id != staff.id,
        ))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Працівник з такою поштою вже існує")

    next_role = payload.get("role", staff.role)
    next_active = payload.get("is_active", staff.is_active)
    next_can_teach = payload.get("can_teach", staff.can_teach)
    if next_role == StaffRole.TEACHER:
        next_can_teach = True
        payload["can_teach"] = True
    if staff.can_teach and not next_can_teach:
        assigned = db.scalar(select(GroupStaff.id).where(
            GroupStaff.organization_id == org_id,
            GroupStaff.staff_id == staff.id,
        ).limit(1))
        if assigned is not None:
            raise HTTPException(status_code=409, detail="Спочатку приберіть працівника з навчальних груп")

    membership = None
    user = None
    if staff.user_id is not None:
        membership = db.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == staff.user_id,
        ).with_for_update())
        user = db.get(User, staff.user_id)
        if membership is not None:
            _ensure_not_last_owner(db, org_id, membership, next_role, next_active)
            membership.role = next_role
            membership.is_active = next_active
        if user is not None and payload.get("email"):
            normalized = payload["email"].strip().lower()
            duplicate_user = db.scalar(select(User.id).where(User.email == normalized, User.id != user.id))
            if duplicate_user is not None:
                raise HTTPException(status_code=409, detail="Ця пошта вже використовується іншим обліковим записом")
            user.email = normalized

    for key, value in payload.items():
        setattr(staff, key, value)
    staff.role = next_role
    staff.is_active = next_active
    staff.can_teach = next_can_teach

    after = {
        "full_name": staff.full_name,
        "email": staff.email,
        "role": staff.role.value,
        "can_teach": staff.can_teach,
        "is_active": staff.is_active,
        "membership_active": membership.is_active if membership is not None else None,
    }
    crm.record_audit(db, org_id, "staff", staff.id, "staff.access_updated", {"before": before, "after": after}, actor_user_id)
    db.commit()
    db.refresh(staff)
    return staff


def set_staff_capabilities(
    db: Session,
    org_id: UUID,
    staff_id: UUID,
    values: dict[str, bool],
    actor_user_id: UUID | None,
) -> list[StaffCapability]:
    crm.scoped_get(db, Staff, org_id, staff_id)
    allowed_keys = {
        "leads.manage", "students.manage", "groups.manage", "schedule.manage", "attendance.manage",
        "finance.view", "finance.manage", "staff.manage", "settings.manage", "reports.view", "teaching",
    }
    unknown = set(values) - allowed_keys
    if unknown:
        raise HTTPException(status_code=422, detail=f"Невідомі права: {', '.join(sorted(unknown))}")
    existing = {row.capability: row for row in db.scalars(select(StaffCapability).where(
        StaffCapability.organization_id == org_id,
        StaffCapability.staff_id == staff_id,
    ))}
    for key, allowed in values.items():
        row = existing.get(key)
        if row is None:
            row = StaffCapability(organization_id=org_id, staff_id=staff_id, capability=key, allowed=allowed)
            db.add(row)
            existing[key] = row
        else:
            row.allowed = allowed
    crm.record_audit(db, org_id, "staff", staff_id, "staff.capabilities_updated", {"capabilities": values}, actor_user_id)
    db.commit()
    return list(db.scalars(select(StaffCapability).where(
        StaffCapability.organization_id == org_id,
        StaffCapability.staff_id == staff_id,
    ).order_by(StaffCapability.capability)))


def list_rooms(db: Session, org_id: UUID, location_id: UUID | None = None) -> list[Room]:
    stmt = select(Room).where(Room.organization_id == org_id, Room.is_active.is_(True))
    if location_id is not None:
        crm.scoped_get(db, Location, org_id, location_id)
        stmt = stmt.where(Room.location_id == location_id)
    return list(db.scalars(stmt.order_by(Room.name)))


def create_room(db: Session, org_id: UUID, location_id: UUID, name: str, capacity: int | None) -> Room:
    crm.scoped_get(db, Location, org_id, location_id)
    room = Room(organization_id=org_id, location_id=location_id, name=name.strip(), capacity=capacity)
    db.add(room)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="У цій локації вже є кімната з такою назвою") from exc
    db.refresh(room)
    return room


def assign_group_room(db: Session, org_id: UUID, group_id: UUID, room_id: UUID | None) -> GroupRoomAssignment | None:
    group = crm.scoped_get(db, Group, org_id, group_id)
    existing = db.scalar(select(GroupRoomAssignment).where(
        GroupRoomAssignment.organization_id == org_id,
        GroupRoomAssignment.group_id == group.id,
    ))
    if room_id is None:
        if existing is not None:
            db.delete(existing)
        return None
    room = db.scalar(select(Room).where(Room.organization_id == org_id, Room.id == room_id, Room.is_active.is_(True)))
    if room is None:
        raise HTTPException(status_code=404, detail="Кімнату не знайдено")
    if group.location_id is not None and room.location_id != group.location_id:
        raise HTTPException(status_code=409, detail="Кімната належить іншій локації")
    if existing is None:
        existing = GroupRoomAssignment(organization_id=org_id, group_id=group.id, room_id=room.id)
        db.add(existing)
    else:
        existing.room_id = room.id
    return existing


def group_room_id(db: Session, org_id: UUID, group_id: UUID) -> UUID | None:
    return db.scalar(select(GroupRoomAssignment.room_id).where(
        GroupRoomAssignment.organization_id == org_id,
        GroupRoomAssignment.group_id == group_id,
    ))


def primary_group_staff_id(db: Session, org_id: UUID, group_id: UUID) -> UUID | None:
    row = db.scalar(select(GroupStaff.staff_id).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.group_id == group_id,
    ).order_by(GroupStaff.is_primary.desc(), GroupStaff.id))
    return row


def _overlaps(start_a: datetime, duration_a: int, start_b: datetime, duration_b: int) -> bool:
    return start_a < start_b + timedelta(minutes=duration_b) and start_a + timedelta(minutes=duration_a) > start_b


def _conflict_window_label(db: Session, org_id: UUID, starts_at: datetime, duration_minutes: int) -> str:
    start_utc = _utc_naive(db, org_id, starts_at).replace(tzinfo=timezone.utc)
    end_utc = start_utc + timedelta(minutes=duration_minutes)
    tz = organization_timezone(db, org_id)
    local_start = start_utc.astimezone(tz)
    local_end = end_utc.astimezone(tz)
    end_label = local_end.strftime("%H:%M")
    if local_end.date() != local_start.date():
        end_label = local_end.strftime("%d.%m.%Y %H:%M")
    return f"{local_start:%d.%m.%Y} {local_start:%H:%M}–{end_label}"


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
    start = _utc_naive(db, org_id, starts_at)

    sessions = list(db.scalars(select(LessonSession).where(
        LessonSession.organization_id == org_id,
        LessonSession.status != LessonStatus.CANCELLED,
    )))
    for session in sessions:
        if exclude_session_id is not None and session.id == exclude_session_id:
            continue
        existing_start = _utc_naive(db, org_id, session.starts_at)
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
            location_id is not None and session.location_id is not None and location_id == session.location_id
            and (room_id is None or existing_room is None)
        )
        if same_group or same_staff or same_room or same_location_without_room:
            reasons = []
            if same_group:
                reasons.append("група вже має заняття")
            if same_staff:
                reasons.append("викладач зайнятий")
            if same_room:
                reasons.append("кімната зайнята")
            elif same_location_without_room:
                reasons.append("локація зайнята")
            interval = _conflict_window_label(db, org_id, session.starts_at, session.duration_minutes)
            return f"Конфлікт розкладу ({', '.join(reasons)}: {interval})"

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
        trial_start = _utc_naive(db, org_id, trial.starts_at)
        if not _overlaps(start, duration_minutes, trial_start, trial_duration):
            continue
        trial_staff = resources.staff_id if resources else None
        trial_room = resources.room_id if resources else None
        same_staff = bool(staff_id is not None and trial_staff is not None and staff_id == trial_staff)
        same_room = bool(room_id is not None and trial_room is not None and room_id == trial_room)
        same_location_without_room = bool(
            location_id is not None and trial.location_id is not None and location_id == trial.location_id
            and (room_id is None or trial_room is None)
        )
        if same_staff or same_room or same_location_without_room:
            interval = _conflict_window_label(db, org_id, trial.starts_at, trial_duration)
            return f"Конфлікт із пробним заняттям: {interval}"

    individuals = list(db.scalars(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org_id,
        IndividualLessonSession.status != "cancelled",
    )))
    for lesson in individuals:
        if exclude_individual_id is not None and lesson.id == exclude_individual_id:
            continue
        individual_start = _utc_naive(db, org_id, lesson.starts_at)
        if not _overlaps(start, duration_minutes, individual_start, lesson.duration_minutes):
            continue
        same_staff = bool(staff_id is not None and lesson.staff_id is not None and staff_id == lesson.staff_id)
        same_room = bool(room_id is not None and lesson.room_id is not None and room_id == lesson.room_id)
        same_location_without_room = bool(
            location_id is not None and lesson.location_id is not None and location_id == lesson.location_id
            and (room_id is None or lesson.room_id is None)
        )
        if same_staff or same_room or same_location_without_room:
            interval = _conflict_window_label(db, org_id, lesson.starts_at, lesson.duration_minutes)
            return f"Конфлікт з індивідуальним заняттям: {interval}"
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
    )) if _local_date(db, org_id, row.starts_at) >= today]


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
    crm.record_audit(db, org_id, "group", group.id, "schedule.reconciled", {
        "created_sessions": created,
        "active_slots": _slot_payload(active_slots),
    }, actor_user_id)
    return created


def update_group_hardened(db: Session, org_id: UUID, group_id: UUID, data, actor_user_id: UUID | None) -> Group:
    group = db.scalar(select(Group).where(Group.organization_id == org_id, Group.id == group_id).with_for_update())
    if group is None:
        raise HTTPException(status_code=404, detail="Групу не знайдено")
    if data.location_id is not None:
        crm.scoped_get(db, Location, org_id, data.location_id)
    enrolled_count = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    )) or 0
    if data.capacity < enrolled_count:
        raise HTTPException(status_code=422, detail=f"Місткість не може бути меншою за {enrolled_count}")

    before = {
        "name": group.name,
        "location_id": str(group.location_id) if group.location_id else None,
        "room_id": str(group_room_id(db, org_id, group.id)) if group_room_id(db, org_id, group.id) else None,
    }
    group.name = data.name
    group.location_id = data.location_id
    group.capacity = data.capacity
    group.min_age = data.min_age
    group.max_age = data.max_age
    assign_group_room(db, org_id, group.id, getattr(data, "room_id", None))

    existing = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
    )))
    by_key = {(row.weekday, row.start_time): row for row in existing}
    desired: set[tuple[int, time]] = set()
    for slot in data.schedule_slots:
        slot_time = time.fromisoformat(slot.start_time)
        key = (slot.weekday, slot_time)
        desired.add(key)
        row = by_key.get(key)
        if row is None:
            row = GroupSchedule(
                organization_id=org_id, group_id=group.id, weekday=slot.weekday,
                start_time=slot_time, duration_minutes=slot.duration_minutes, is_active=True,
            )
            db.add(row)
        else:
            row.duration_minutes = slot.duration_minutes
            row.is_active = True
    for row in existing:
        if (row.weekday, row.start_time) not in desired:
            row.is_active = False
    db.flush()
    active = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.is_active.is_(True),
    )))
    save_schedule_history(db, org_id, group, active, actor_user_id)
    reconcile_group_future_sessions(db, org_id, group, actor_user_id)
    after_room = group_room_id(db, org_id, group.id)
    crm.record_audit(db, org_id, "group", group.id, "group.updated_hardened", {
        "before": before,
        "after": {
            "name": group.name,
            "location_id": str(group.location_id) if group.location_id else None,
            "room_id": str(after_room) if after_room else None,
            "capacity": group.capacity,
        },
    }, actor_user_id)
    db.commit()
    db.refresh(group)
    return group


def create_group_schedule_hardened(db: Session, org_id: UUID, data, actor_user_id: UUID | None) -> GroupSchedule:
    group = db.scalar(select(Group).where(Group.organization_id == org_id, Group.id == data.group_id).with_for_update())
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
            organization_id=org_id, group_id=group.id, weekday=data.weekday,
            start_time=slot_time, duration_minutes=data.duration_minutes, is_active=True,
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


def _group_capacity_locked(db: Session, org_id: UUID, group_id: UUID, student_id: UUID | None = None) -> Group:
    group = db.scalar(select(Group).where(Group.organization_id == org_id, Group.id == group_id).with_for_update())
    if group is None:
        raise HTTPException(status_code=404, detail="Групу не знайдено")
    if group.capacity is None:
        return group
    if student_id is not None:
        current = db.scalar(select(Enrollment.id).where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id == group.id,
            Enrollment.student_id == student_id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        ))
        if current is not None:
            return group
    occupied = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    )) or 0
    if occupied >= group.capacity:
        raise HTTPException(status_code=409, detail="У групі немає вільних місць")
    return group


def _schedule_match_for(db: Session, org_id: UUID, student: Student, group: Group) -> tuple[str, str]:
    slots = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.is_active.is_(True),
    )))
    windows = list(db.scalars(select(StudentAvailability).where(
        StudentAvailability.organization_id == org_id,
        StudentAvailability.student_id == student.id,
    )))
    match = evaluate_schedule_match(slots, windows, group.location_id, student.preferred_location_id)
    return match.status, enrollment_schedule_note(match, slots, windows)


def create_enrollment_hardened(db: Session, org_id: UUID, data, actor_user_id: UUID | None) -> Enrollment:
    student = db.scalar(select(Student).where(Student.organization_id == org_id, Student.id == data.student_id).with_for_update())
    if student is None:
        raise HTTPException(status_code=404, detail="Учня не знайдено")
    group = _group_capacity_locked(db, org_id, data.group_id, student.id)
    existing = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.group_id == group.id,
    ).with_for_update())
    start = data.started_at or organization_today(db, org_id)
    match, note = _schedule_match_for(db, org_id, student, group)
    if existing is not None and existing.status in {EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED}:
        return existing
    if existing is not None:
        db.add(EnrollmentHistory(
            organization_id=org_id,
            enrollment_id=existing.id,
            student_id=existing.student_id,
            group_id=existing.group_id,
            started_at=existing.started_at,
            ended_at=existing.ended_at,
            status=existing.status.value,
        ))
        existing.status = EnrollmentStatus.ACTIVE
        existing.started_at = start
        existing.ended_at = None
        existing.schedule_match = match
        existing.schedule_note = note
        enrollment = existing
    else:
        enrollment = Enrollment(
            organization_id=org_id,
            student_id=student.id,
            group_id=group.id,
            status=EnrollmentStatus.ACTIVE,
            started_at=start,
            schedule_match=match,
            schedule_note=note,
        )
        db.add(enrollment)
    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    crm.record_audit(db, org_id, "student", student.id, "student.enrolled_hardened", {
        "group_id": str(group.id), "started_at": start.isoformat(), "schedule_match": match,
    }, actor_user_id)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def return_student_to_waiting(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    actor_user_id: UUID | None,
) -> Student:
    student = db.scalar(
        select(Student)
        .where(Student.organization_id == org_id, Student.id == student_id)
        .with_for_update()
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Учня не знайдено")

    active_enrollments = list(db.scalars(
        select(Enrollment)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
        .with_for_update()
    ))
    if not active_enrollments and student.crm_status != CrmStatus.ENROLLED:
        raise HTTPException(status_code=409, detail="Учень не зарахований до групи")

    today = organization_today(db, org_id)
    for enrollment in active_enrollments:
        enrollment.status = EnrollmentStatus.FINISHED
        enrollment.ended_at = today

    student.crm_status = CrmStatus.WAITING_FOR_GROUP
    student.student_status = StudentStatus.ACTIVE
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    crm.record_audit(db, org_id, "student", student.id, "student.returned_to_waiting", {
        "ended_enrollments": len(active_enrollments),
        "group_ids": [str(row.group_id) for row in active_enrollments],
        "ended_at": today.isoformat(),
    }, actor_user_id)
    db.commit()
    db.refresh(student)
    return student


def transfer_student_hardened(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    to_group_id: UUID,
    started_at: date | None,
    actor_user_id: UUID | None,
) -> Enrollment:
    student = db.scalar(select(Student).where(Student.organization_id == org_id, Student.id == student_id).with_for_update())
    if student is None:
        raise HTTPException(status_code=404, detail="Учня не знайдено")
    target = _group_capacity_locked(db, org_id, to_group_id, student.id)
    start = started_at or organization_today(db, org_id)
    current_rows = list(db.scalars(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    ).with_for_update()))
    for row in current_rows:
        if row.group_id == target.id:
            return row
        row.status = EnrollmentStatus.FINISHED
        row.ended_at = start - timedelta(days=1)
    existing = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.group_id == target.id,
    ).with_for_update())
    match, note = _schedule_match_for(db, org_id, student, target)
    if existing is not None:
        db.add(EnrollmentHistory(
            organization_id=org_id,
            enrollment_id=existing.id,
            student_id=existing.student_id,
            group_id=existing.group_id,
            started_at=existing.started_at,
            ended_at=existing.ended_at,
            status=existing.status.value,
        ))
        existing.status = EnrollmentStatus.ACTIVE
        existing.started_at = start
        existing.ended_at = None
        existing.schedule_match = match
        existing.schedule_note = note
        enrollment = existing
    else:
        enrollment = Enrollment(
            organization_id=org_id, student_id=student.id, group_id=target.id,
            status=EnrollmentStatus.ACTIVE, started_at=start, schedule_match=match, schedule_note=note,
        )
        db.add(enrollment)
    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    crm.record_audit(db, org_id, "student", student.id, "student.transferred_hardened", {
        "to_group_id": str(target.id), "started_at": start.isoformat(),
    }, actor_user_id)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def historical_roster_ids(db: Session, org_id: UUID, group_id: UUID, on_date: date) -> set[UUID]:
    ids = set(db.scalars(select(Enrollment.student_id).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group_id,
        Enrollment.started_at <= on_date,
        (Enrollment.ended_at.is_(None) | (Enrollment.ended_at >= on_date)),
    )))
    ids.update(db.scalars(select(EnrollmentHistory.student_id).where(
        EnrollmentHistory.organization_id == org_id,
        EnrollmentHistory.group_id == group_id,
        EnrollmentHistory.started_at <= on_date,
        (EnrollmentHistory.ended_at.is_(None) | (EnrollmentHistory.ended_at >= on_date)),
    )))
    return ids


def historical_roster(db: Session, org_id: UUID, group_id: UUID, on_date: date) -> list[dict]:
    crm.scoped_get(db, Group, org_id, group_id)
    ids = historical_roster_ids(db, org_id, group_id, on_date)
    if not ids:
        return []
    students = list(db.scalars(select(Student).where(
        Student.organization_id == org_id,
        Student.id.in_(ids),
    ).order_by(Student.first_name, Student.last_name)))
    return [{
        "student_id": row.id,
        "first_name": row.first_name,
        "last_name": row.last_name,
        "age": row.age_at_inquiry,
    } for row in students]


def list_group_schedules_strict(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole, group_id: UUID | None = None):
    allowed = strict_group_ids_for_user(db, org_id, user_id, role)
    stmt = select(GroupSchedule).where(GroupSchedule.organization_id == org_id, GroupSchedule.is_active.is_(True))
    if group_id is not None:
        ensure_group_access(db, org_id, user_id, role, group_id)
        stmt = stmt.where(GroupSchedule.group_id == group_id)
    elif allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(GroupSchedule.group_id.in_(allowed))
    return list(db.scalars(stmt.order_by(GroupSchedule.weekday, GroupSchedule.start_time)))


def list_lesson_sessions_read_only(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole, group_id: UUID | None = None):
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


def create_lesson_session_hardened(db: Session, org_id: UUID, data, user_id: UUID | None, role: StaffRole) -> LessonSession:
    group = ensure_group_access(db, org_id, user_id, role, data.group_id)
    location_id = data.location_id if data.location_id is not None else group.location_id
    if location_id is not None:
        crm.scoped_get(db, Location, org_id, location_id)
    room_id = getattr(data, "room_id", None) or group_room_id(db, org_id, group.id)
    if room_id is not None:
        room = db.scalar(select(Room).where(Room.organization_id == org_id, Room.id == room_id))
        if room is None:
            raise HTTPException(status_code=404, detail="Кімнату не знайдено")
        if location_id is not None and room.location_id != location_id:
            raise HTTPException(status_code=409, detail="Кімната належить іншій локації")
    staff_id = getattr(data, "staff_id", None) or primary_group_staff_id(db, org_id, group.id)
    if staff_id is not None:
        staff = crm.scoped_get(db, Staff, org_id, staff_id)
        if not staff.is_active or not staff.can_teach:
            raise HTTPException(status_code=409, detail="Обраний працівник не може вести заняття")
    conflict = resource_conflict_reason(
        db, org_id, data.starts_at, data.duration_minutes, location_id, room_id, staff_id, group_id=group.id,
    )
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    session = LessonSession(
        organization_id=org_id, group_id=group.id, location_id=location_id,
        starts_at=data.starts_at, duration_minutes=data.duration_minutes,
        topic=data.topic, notes=data.notes, status=LessonStatus.SCHEDULED,
    )
    db.add(session)
    db.flush()
    db.add(LessonResourceAssignment(
        organization_id=org_id, session_id=session.id, staff_id=staff_id, room_id=room_id,
    ))
    crm.record_audit(db, org_id, "lesson_session", session.id, "lesson.created_hardened", {
        "group_id": str(group.id), "staff_id": str(staff_id) if staff_id else None, "room_id": str(room_id) if room_id else None,
    }, user_id)
    db.commit()
    db.refresh(session)
    return session


def create_trial_hardened(db: Session, org_id: UUID, data, actor_user_id: UUID | None) -> TrialLesson:
    student = crm.scoped_get(db, Student, org_id, data.student_id)
    if data.location_id is not None:
        crm.scoped_get(db, Location, org_id, data.location_id)
    room_id = getattr(data, "room_id", None)
    if room_id is not None:
        room = db.scalar(select(Room).where(Room.organization_id == org_id, Room.id == room_id))
        if room is None:
            raise HTTPException(status_code=404, detail="Кімнату не знайдено")
        if data.location_id is not None and room.location_id != data.location_id:
            raise HTTPException(status_code=409, detail="Кімната належить іншій локації")
    staff_id = getattr(data, "staff_id", None)
    if staff_id is not None:
        staff = crm.scoped_get(db, Staff, org_id, staff_id)
        if not staff.is_active or not staff.can_teach:
            raise HTTPException(status_code=409, detail="Працівник не може проводити пробне")
    duration = getattr(data, "duration_minutes", 60)
    conflict = resource_conflict_reason(db, org_id, data.starts_at, duration, data.location_id, room_id, staff_id)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    trial = TrialLesson(
        organization_id=org_id, student_id=student.id, location_id=data.location_id,
        starts_at=data.starts_at, status=TrialStatus.SCHEDULED,
    )
    db.add(trial)
    db.flush()
    db.add(TrialResourceAssignment(
        organization_id=org_id, trial_id=trial.id, staff_id=staff_id, room_id=room_id, duration_minutes=duration,
    ))
    student.crm_status = CrmStatus.TRIAL_SCHEDULED
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    crm.record_audit(db, org_id, "student", student.id, "trial.scheduled", {
        "trial_id": str(trial.id), "staff_id": str(staff_id) if staff_id else None, "room_id": str(room_id) if room_id else None,
    }, actor_user_id)
    db.commit()
    db.refresh(trial)
    return trial


def update_trial_hardened(db: Session, org_id: UUID, trial_id: UUID, data, actor_user_id: UUID | None) -> TrialLesson:
    trial = crm.scoped_get(db, TrialLesson, org_id, trial_id)
    starts_at = data.starts_at or trial.starts_at
    location_id = data.location_id if data.location_id is not None else trial.location_id
    if location_id is not None:
        crm.scoped_get(db, Location, org_id, location_id)
    resources = db.scalar(select(TrialResourceAssignment).where(
        TrialResourceAssignment.organization_id == org_id,
        TrialResourceAssignment.trial_id == trial.id,
    ))
    if resources is None:
        resources = TrialResourceAssignment(organization_id=org_id, trial_id=trial.id, duration_minutes=60)
        db.add(resources)
    room_id = getattr(data, "room_id", None)
    if room_id is None:
        room_id = resources.room_id
    staff_id = getattr(data, "staff_id", None)
    if staff_id is None:
        staff_id = resources.staff_id
    duration = getattr(data, "duration_minutes", None) or resources.duration_minutes or 60
    conflict = resource_conflict_reason(
        db, org_id, starts_at, duration, location_id, room_id, staff_id, exclude_trial_id=trial.id,
    )
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    trial.starts_at = starts_at
    trial.location_id = location_id
    trial.status = TrialStatus.SCHEDULED
    resources.room_id = room_id
    resources.staff_id = staff_id
    resources.duration_minutes = duration
    student = crm.scoped_get(db, Student, org_id, trial.student_id)
    student.crm_status = CrmStatus.TRIAL_SCHEDULED
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    crm.record_audit(db, org_id, "student", student.id, "trial.rescheduled", {
        "trial_id": str(trial.id), "starts_at": starts_at.isoformat(),
    }, actor_user_id)
    db.commit()
    db.refresh(trial)
    return trial


def _subscription_used_units(db: Session, org_id: UUID, subscription_id: UUID) -> int:
    group_units = db.scalar(select(func.coalesce(func.sum(SubscriptionUsage.units), 0)).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.subscription_id == subscription_id,
    )) or 0
    individual_units = db.scalar(select(func.coalesce(func.sum(IndividualSubscriptionUsage.units), 0)).where(
        IndividualSubscriptionUsage.organization_id == org_id,
        IndividualSubscriptionUsage.subscription_id == subscription_id,
    )) or 0
    return int(group_units) + int(individual_units)


def _eligible_subscription(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    lesson_date: date,
    group_id: UUID | None,
) -> tuple[StudentSubscription, SubscriptionPlan] | None:
    rows = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student_id,
        StudentSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED]),
        StudentSubscription.starts_on <= lesson_date,
    ).order_by(StudentSubscription.starts_on, StudentSubscription.created_at)))
    for subscription in rows:
        if subscription.group_id is not None and group_id is not None and subscription.group_id != group_id:
            continue
        if subscription.group_id is not None and group_id is None:
            continue
        plan = crm.scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
        if subscription.ends_on is not None and plan.end_rule in {"date", "whichever_first"} and lesson_date > subscription.ends_on:
            continue
        included = subscription.lessons_included if subscription.lessons_included is not None else plan.lessons_included
        if included is not None and _subscription_used_units(db, org_id, subscription.id) >= included:
            continue
        return subscription, plan
    return None


def _should_consume(plan: SubscriptionPlan, status: AttendanceStatus, explicit: bool | None) -> bool:
    if status == AttendanceStatus.PRESENT:
        return True
    if status == AttendanceStatus.LATE:
        return plan.late_rule == "consume"
    if status == AttendanceStatus.EXCUSED:
        return plan.excused_rule == "consume"
    if status == AttendanceStatus.ABSENT:
        if plan.absent_rule == "consume":
            return True
        if plan.absent_rule == "dont_consume":
            return False
        return bool(explicit)
    return False


def _sync_excused_makeup(db: Session, org_id: UUID, session: LessonSession, student_id: UUID, plan: SubscriptionPlan | None, status: AttendanceStatus) -> None:
    existing = db.scalar(select(MakeupCredit).where(
        MakeupCredit.organization_id == org_id,
        MakeupCredit.original_session_id == session.id,
        MakeupCredit.student_id == student_id,
    ))
    if status == AttendanceStatus.EXCUSED and plan is not None and plan.excused_rule == "makeup":
        expires_on = None
        if plan.makeup_expiry_days:
            expires_on = _local_date(db, org_id, session.starts_at) + timedelta(days=plan.makeup_expiry_days)
        if existing is None:
            db.add(MakeupCredit(
                organization_id=org_id, student_id=student_id, original_session_id=session.id,
                status="pending", expires_on=expires_on,
            ))
        elif existing.status == "cancelled":
            existing.status = "pending"
            existing.expires_on = expires_on
    elif existing is not None and existing.status == "pending":
        existing.status = "cancelled"


def _consume_oldest_makeup(db: Session, org_id: UUID, student_id: UUID, target_session_id: UUID, on_date: date) -> bool:
    credit = db.scalar(select(MakeupCredit).where(
        MakeupCredit.organization_id == org_id,
        MakeupCredit.student_id == student_id,
        MakeupCredit.status == "pending",
        MakeupCredit.original_session_id != target_session_id,
        (MakeupCredit.expires_on.is_(None) | (MakeupCredit.expires_on >= on_date)),
    ).order_by(MakeupCredit.created_at))
    if credit is None:
        return False
    credit.status = "completed"
    credit.target_session_id = target_session_id
    credit.completed_at = datetime.now(timezone.utc)
    db.add(MakeupCompletionLink(
        organization_id=org_id, target_session_id=target_session_id, makeup_credit_id=credit.id,
    ))
    return True


def _renew_from_group_session(
    db: Session,
    org_id: UUID,
    subscription: StudentSubscription,
    plan: SubscriptionPlan,
    session: LessonSession,
    actor_user_id: UUID | None,
) -> None:
    included = subscription.lessons_included if subscription.lessons_included is not None else plan.lessons_included
    if not subscription.auto_renew or plan.renewal_trigger != "last_lesson" or included is None:
        return
    if _subscription_used_units(db, org_id, subscription.id) < included:
        return
    if not plan.is_active:
        return
    existing = db.scalar(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.renewal_of_id == subscription.id,
        StudentSubscription.status != SubscriptionStatus.CANCELLED,
    ))
    if existing is not None:
        return
    student = crm.scoped_get(db, Student, org_id, subscription.student_id)
    if student.student_status != StudentStatus.ACTIVE:
        return
    organization = crm.require_organization(db, org_id)
    after_date = _local_date(db, org_id, session.starts_at) + timedelta(days=1)
    next_start = crm._first_planned_lesson_date(db, org_id, subscription.group_id, after_date)
    credit_before = max(0, subscription.credit_minor)
    applied_credit = min(credit_before, plan.price_minor)
    carry_credit = max(0, credit_before - applied_credit)
    amount_due = max(0, plan.price_minor - applied_credit)
    child = StudentSubscription(
        organization_id=org_id, student_id=subscription.student_id, plan_id=plan.id,
        group_id=subscription.group_id, status=SubscriptionStatus.ACTIVE, starts_on=next_start,
        ends_on=crm._subscription_end_date(next_start, plan.period_days), price_minor=plan.price_minor,
        period_days=plan.period_days, lessons_included=plan.lessons_included,
        lesson_unit_price_minor=crm._lesson_unit_price(plan.price_minor, plan.lessons_included),
        credit_minor=carry_credit, discount_minor=0, discount_label=None, auto_renew=True,
        renewal_of_id=subscription.id,
    )
    db.add(child)
    db.flush()
    payment = Payment(
        organization_id=org_id, student_id=subscription.student_id, subscription_id=child.id,
        amount_minor=amount_due, currency=organization.currency, due_date=next_start,
        note=f"{plan.name} · продовження після фіналізації заняття",
        status=PaymentStatus.PAID if amount_due == 0 else PaymentStatus.PENDING,
        paid_at=datetime.now(timezone.utc) if amount_due == 0 else None,
    )
    db.add(payment)
    db.flush()
    db.add(LessonDerivedBilling(
        organization_id=org_id, session_id=session.id, parent_subscription_id=subscription.id,
        renewal_subscription_id=child.id, payment_id=payment.id, parent_credit_before_minor=credit_before,
    ))
    subscription.credit_minor = 0
    subscription.status = SubscriptionStatus.EXPIRED
    crm.record_audit(db, org_id, "student", subscription.student_id, "subscription.renewed_after_finalized_lesson", {
        "session_id": str(session.id), "subscription_id": str(child.id), "payment_id": str(payment.id),
    }, actor_user_id)


def _reopen_group_lesson_no_commit(db: Session, org_id: UUID, session: LessonSession, actor_user_id: UUID | None) -> None:
    links = list(db.scalars(select(LessonDerivedBilling).where(
        LessonDerivedBilling.organization_id == org_id,
        LessonDerivedBilling.session_id == session.id,
    )))
    for link in links:
        payment = crm.scoped_get(db, Payment, org_id, link.payment_id)
        transactions = list(db.scalars(select(PaymentTransaction).where(
            PaymentTransaction.organization_id == org_id,
            PaymentTransaction.payment_id == payment.id,
        )))
        if transactions or payment.status in {PaymentStatus.PAID, PaymentStatus.REFUNDED}:
            raise HTTPException(
                status_code=409,
                detail="Заняття вже створило фінансову операцію. Спочатку зробіть фінансове коригування.",
            )
        child = crm.scoped_get(db, StudentSubscription, org_id, link.renewal_subscription_id)
        parent = crm.scoped_get(db, StudentSubscription, org_id, link.parent_subscription_id)
        payment.status = PaymentStatus.CANCELLED
        child.status = SubscriptionStatus.CANCELLED
        parent.credit_minor = link.parent_credit_before_minor
        parent.status = SubscriptionStatus.ACTIVE
        db.delete(link)

    makeup_links = list(db.scalars(select(MakeupCompletionLink).where(
        MakeupCompletionLink.organization_id == org_id,
        MakeupCompletionLink.target_session_id == session.id,
    )))
    for link in makeup_links:
        credit = db.scalar(select(MakeupCredit).where(
            MakeupCredit.organization_id == org_id,
            MakeupCredit.id == link.makeup_credit_id,
        ))
        if credit is not None:
            credit.status = "pending"
            credit.target_session_id = None
            credit.completed_at = None
        db.delete(link)

    db.execute(delete(SubscriptionUsage).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.session_id == session.id,
    ))
    finalization = db.scalar(select(LessonFinalization).where(
        LessonFinalization.organization_id == org_id,
        LessonFinalization.session_id == session.id,
    ))
    if finalization is not None:
        db.delete(finalization)
    session.status = LessonStatus.SCHEDULED
    crm.record_audit(db, org_id, "lesson_session", session.id, "lesson.reopened", {}, actor_user_id)


def finalize_group_lesson(db: Session, org_id: UUID, session: LessonSession, actor_user_id: UUID | None) -> None:
    existing = db.scalar(select(LessonFinalization).where(
        LessonFinalization.organization_id == org_id,
        LessonFinalization.session_id == session.id,
    ))
    if existing is not None:
        return
    lesson_date = _local_date(db, org_id, session.starts_at)
    roster = historical_roster_ids(db, org_id, session.group_id, lesson_date)
    marks = list(db.scalars(select(Attendance).where(
        Attendance.organization_id == org_id,
        Attendance.session_id == session.id,
    )))
    marked_ids = {row.student_id for row in marks}
    if roster and not roster.issubset(marked_ids):
        raise HTTPException(status_code=409, detail="Перед завершенням відмітьте всіх учнів цього заняття")

    db.execute(delete(SubscriptionUsage).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.session_id == session.id,
    ))
    touched_subscriptions: dict[UUID, tuple[StudentSubscription, SubscriptionPlan]] = {}
    for mark in marks:
        eligible = _eligible_subscription(db, org_id, mark.student_id, lesson_date, session.group_id)
        plan = eligible[1] if eligible else None
        _sync_excused_makeup(db, org_id, session, mark.student_id, plan, mark.status)
        used_makeup = False
        if mark.status in {AttendanceStatus.PRESENT, AttendanceStatus.LATE}:
            used_makeup = _consume_oldest_makeup(db, org_id, mark.student_id, session.id, lesson_date)
        if eligible is not None and not used_makeup and _should_consume(plan, mark.status, getattr(mark, "consume_lesson", None)):
            subscription, plan = eligible
            usage = SubscriptionUsage(
                organization_id=org_id, subscription_id=subscription.id, student_id=mark.student_id,
                session_id=session.id, attendance_id=mark.id, units=1, source_status=mark.status.value,
            )
            db.add(usage)
            touched_subscriptions[subscription.id] = (subscription, plan)
    db.flush()
    for subscription, plan in touched_subscriptions.values():
        _renew_from_group_session(db, org_id, subscription, plan, session, actor_user_id)
    session.status = LessonStatus.COMPLETED
    db.add(LessonFinalization(
        organization_id=org_id, session_id=session.id, finalized_by_user_id=actor_user_id, revision=1,
    ))
    crm.record_audit(db, org_id, "lesson_session", session.id, "lesson.finalized", {
        "marked_count": len(marks), "lesson_date": lesson_date.isoformat(),
    }, actor_user_id)


def save_attendance_hardened(db: Session, org_id: UUID, session_id: UUID, items, user_id: UUID | None, role: StaffRole):
    session = crm.scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, session.group_id)
    finalization = db.scalar(select(LessonFinalization).where(
        LessonFinalization.organization_id == org_id,
        LessonFinalization.session_id == session.id,
    ))
    if finalization is not None:
        _reopen_group_lesson_no_commit(db, org_id, session, user_id)
        db.flush()

    lesson_date = _local_date(db, org_id, session.starts_at)
    roster = historical_roster_ids(db, org_id, session.group_id, lesson_date)
    submitted = [item.student_id for item in items]
    if len(set(submitted)) != len(submitted):
        raise HTTPException(status_code=422, detail="Учень переданий двічі")
    if not set(submitted).issubset(roster):
        raise HTTPException(status_code=409, detail="Можна відмічати лише учнів, які були в групі на дату заняття")
    result = []
    for mark in items:
        row = db.scalar(select(Attendance).where(
            Attendance.organization_id == org_id,
            Attendance.session_id == session.id,
            Attendance.student_id == mark.student_id,
        ))
        if row is None:
            row = Attendance(
                organization_id=org_id, session_id=session.id, student_id=mark.student_id,
                status=mark.status, note=mark.note,
            )
            db.add(row)
        else:
            row.status = mark.status
            row.note = mark.note
        result.append(row)
    db.flush()
    all_marks = set(db.scalars(select(Attendance.student_id).where(
        Attendance.organization_id == org_id,
        Attendance.session_id == session.id,
    )))
    if not roster or roster.issubset(all_marks):
        finalize_group_lesson(db, org_id, session, user_id)
    crm.record_audit(db, org_id, "lesson_session", session.id, "attendance.saved_hardened", {
        "marked_count": len(result), "historical_roster_count": len(roster),
    }, user_id)
    db.commit()
    for row in result:
        db.refresh(row)
    return result


def reopen_group_lesson(db: Session, org_id: UUID, session_id: UUID, user_id: UUID | None, role: StaffRole) -> LessonSession:
    session = crm.scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, session.group_id)
    _reopen_group_lesson_no_commit(db, org_id, session, user_id)
    db.commit()
    db.refresh(session)
    return session


def create_subscription_charge_hardened(db: Session, org_id: UUID, data, actor_user_id: UUID | None):
    if getattr(data, "group_id", None) is not None:
        group = crm.scoped_get(db, Group, org_id, data.group_id)
        enrollment = db.scalar(select(Enrollment.id).where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == data.student_id,
            Enrollment.group_id == group.id,
            Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
        ))
        if enrollment is None:
            raise HTTPException(status_code=409, detail="Учень не зарахований до обраної групи")
    return crm.create_subscription_charge(db, org_id, data, actor_user_id)


def create_student_subscription_hardened(db: Session, org_id: UUID, data):
    if getattr(data, "group_id", None) is not None:
        group = crm.scoped_get(db, Group, org_id, data.group_id)
        enrollment = db.scalar(select(Enrollment.id).where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == data.student_id,
            Enrollment.group_id == group.id,
            Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
        ))
        if enrollment is None:
            raise HTTPException(status_code=409, detail="Учень не зарахований до обраної групи")
    return crm.create_student_subscription(db, org_id, data)


def create_individual_lesson(db: Session, org_id: UUID, data, actor_user_id: UUID | None) -> IndividualLessonSession:
    student = crm.scoped_get(db, Student, org_id, data.student_id)
    if student.student_status != StudentStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Індивідуальне заняття можна створити лише для активного учня")
    if data.location_id is not None:
        crm.scoped_get(db, Location, org_id, data.location_id)
    if data.room_id is not None:
        room = db.scalar(select(Room).where(Room.organization_id == org_id, Room.id == data.room_id))
        if room is None:
            raise HTTPException(status_code=404, detail="Кімнату не знайдено")
        if data.location_id is not None and room.location_id != data.location_id:
            raise HTTPException(status_code=409, detail="Кімната належить іншій локації")
    if data.staff_id is not None:
        staff = crm.scoped_get(db, Staff, org_id, data.staff_id)
        if not staff.is_active or not staff.can_teach:
            raise HTTPException(status_code=409, detail="Працівник не може проводити заняття")
    conflict = resource_conflict_reason(
        db, org_id, data.starts_at, data.duration_minutes, data.location_id, data.room_id, data.staff_id,
    )
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    lesson = IndividualLessonSession(
        organization_id=org_id, student_id=student.id, location_id=data.location_id,
        room_id=data.room_id, staff_id=data.staff_id, starts_at=data.starts_at,
        duration_minutes=data.duration_minutes, topic=data.topic, notes=data.notes, status="scheduled",
    )
    db.add(lesson)
    db.flush()
    crm.record_audit(db, org_id, "student", student.id, "individual_lesson.created", {
        "session_id": str(lesson.id), "starts_at": lesson.starts_at.isoformat(),
    }, actor_user_id)
    db.commit()
    db.refresh(lesson)
    return lesson


def list_individual_lessons(db: Session, org_id: UUID, student_id: UUID | None = None) -> list[IndividualLessonSession]:
    stmt = select(IndividualLessonSession).where(IndividualLessonSession.organization_id == org_id)
    if student_id is not None:
        crm.scoped_get(db, Student, org_id, student_id)
        stmt = stmt.where(IndividualLessonSession.student_id == student_id)
    return list(db.scalars(stmt.order_by(IndividualLessonSession.starts_at)))


def save_individual_attendance(db: Session, org_id: UUID, session_id: UUID, status: AttendanceStatus, note: str | None, actor_user_id: UUID | None):
    session = db.scalar(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org_id,
        IndividualLessonSession.id == session_id,
    ).with_for_update())
    if session is None:
        raise HTTPException(status_code=404, detail="Індивідуальне заняття не знайдено")
    if session.status == "cancelled":
        raise HTTPException(status_code=409, detail="Скасоване заняття не можна провести")
    existing_usage = db.scalar(select(IndividualSubscriptionUsage).where(
        IndividualSubscriptionUsage.organization_id == org_id,
        IndividualSubscriptionUsage.session_id == session.id,
    ))
    if existing_usage is not None:
        db.delete(existing_usage)
        db.flush()
    mark = db.scalar(select(IndividualAttendance).where(
        IndividualAttendance.organization_id == org_id,
        IndividualAttendance.session_id == session.id,
    ))
    if mark is None:
        mark = IndividualAttendance(
            organization_id=org_id, session_id=session.id, student_id=session.student_id,
            status=status.value, note=note,
        )
        db.add(mark)
    else:
        mark.status = status.value
        mark.note = note
        mark.updated_at = datetime.now(timezone.utc)
    lesson_date = _local_date(db, org_id, session.starts_at)
    eligible = _eligible_subscription(db, org_id, session.student_id, lesson_date, None)
    if eligible is not None:
        subscription, plan = eligible
        if _should_consume(plan, status, None):
            db.add(IndividualSubscriptionUsage(
                organization_id=org_id, session_id=session.id, subscription_id=subscription.id,
                student_id=session.student_id, units=1, source_status=status.value,
            ))
    session.status = "completed"
    session.finalized_at = datetime.now(timezone.utc)
    crm.record_audit(db, org_id, "student", session.student_id, "individual_lesson.finalized", {
        "session_id": str(session.id), "status": status.value,
    }, actor_user_id)
    db.commit()
    db.refresh(mark)
    return mark


def filtered_workspace_students(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole, q: str | None, limit: int, offset: int):
    rows = crm.list_student_overview(db, org_id, user_id, StaffRole.OWNER if role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER} else role)
    if role == StaffRole.TEACHER:
        allowed = strict_group_ids_for_user(db, org_id, user_id, role) or set()
        rows = [row for row in rows if row.get("group_id") in allowed]
    if q:
        needle = q.casefold().strip()
        rows = [row for row in rows if needle in " ".join(filter(None, [
            row.get("first_name"), row.get("last_name"), row.get("student_phone"), row.get("contact_name"), row.get("contact_phone"),
        ])).casefold()]
    return rows[offset:offset + limit]


def filtered_workspace_groups(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole, q: str | None, limit: int, offset: int):
    rows = crm.list_group_overview(db, org_id, user_id, StaffRole.OWNER if role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER} else role)
    if role == StaffRole.TEACHER:
        allowed = strict_group_ids_for_user(db, org_id, user_id, role) or set()
        rows = [row for row in rows if row.get("group_id") in allowed]
    if q:
        needle = q.casefold().strip()
        rows = [row for row in rows if needle in " ".join(filter(None, [row.get("name"), row.get("location_name"), row.get("primary_teacher_name")])).casefold()]
    return rows[offset:offset + limit]


def group_detail_strict(db: Session, org_id: UUID, group_id: UUID, user_id: UUID | None, role: StaffRole):
    if role == StaffRole.ACCOUNTANT:
        result = crm.group_detail(db, org_id, group_id, user_id, role)
        return result
    ensure_group_access(db, org_id, user_id, role, group_id)
    result = crm.group_detail(db, org_id, group_id, user_id, StaffRole.OWNER)
    if role == StaffRole.TEACHER:
        for member in result["members"]:
            member["billing"] = None
            member["payments"] = []
    return result


def cleanup_stale_throttles(db: Session, older_than: datetime) -> dict[str, int]:
    from app.models.core import AuthLoginThrottle, PublicIntakeThrottle
    auth_rows = db.execute(delete(AuthLoginThrottle).where(AuthLoginThrottle.updated_at < older_than))
    intake_rows = db.execute(delete(PublicIntakeThrottle).where(PublicIntakeThrottle.updated_at < older_than))
    db.commit()
    return {
        "auth_login_throttles": int(auth_rows.rowcount or 0),
        "public_intake_throttles": int(intake_rows.rowcount or 0),
    }
