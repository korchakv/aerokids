from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_db, get_org_access
from app.models.core import (
    Attendance,
    AttendanceStatus,
    Enrollment,
    EnrollmentStatus,
    Group,
    GroupSchedule,
    GroupStaff,
    LessonSession,
    Location,
    Staff,
    StaffRole,
    Student,
    StudentStatus,
    StudentSubscription,
    SubscriptionStatus,
)
from app.models.hardening import (
    GroupRoomAssignment,
    GroupScheduleHistory,
    IndividualAttendance,
    IndividualLessonSession,
    LessonResourceAssignment,
    Room,
    StaffCapability,
    TrialResourceAssignment,
)
from app.models.hardening_extensions import AttendanceDecision, IndividualDerivedBilling
from app.schemas import (
    AttendanceBulkUpdate,
    AttendanceRead,
    EnrollmentCreate,
    EnrollmentRead,
    GroupDetail,
    GroupFormationCreate,
    GroupFormationResult,
    GroupFormationScheduleSlot,
    GroupRead,
    GroupRosterStudent,
    GroupScheduleCreate,
    GroupScheduleRead,
    LessonSessionRead,
    StaffGroupAssignment,
    StaffRead,
    StaffUpdate,
    StudentLifecycleUpdate,
    StudentSubscriptionCreate,
    StudentSubscriptionRead,
    StudentTransfer,
    SubscriptionChargeCreate,
    SubscriptionChargeResult,
    TrialLessonRead,
)
from app.services import crm, hardening, workspace_service


router = APIRouter()


class RoomCreate(BaseModel):
    location_id: UUID
    name: str = Field(min_length=1, max_length=160)
    capacity: int | None = Field(default=None, ge=1, le=500)


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    location_id: UUID
    name: str
    capacity: int | None
    is_active: bool


class CapabilityUpdate(BaseModel):
    capabilities: dict[str, bool]


class CapabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    capability: str
    allowed: bool


class HardenedGroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    location_id: UUID | None = None
    room_id: UUID | None = None
    capacity: int = Field(ge=1, le=100)
    min_age: int | None = Field(default=None, ge=3, le=30)
    max_age: int | None = Field(default=None, ge=3, le=30)
    schedule_slots: list[GroupFormationScheduleSlot] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_values(self):
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            raise ValueError("min_age cannot be greater than max_age")
        keys = [(slot.weekday, slot.start_time) for slot in self.schedule_slots]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate group schedule slots are not allowed")
        return self


class HardenedGroupFormation(GroupFormationCreate):
    room_id: UUID | None = None


class HardenedLessonCreate(BaseModel):
    group_id: UUID
    location_id: UUID | None = None
    room_id: UUID | None = None
    staff_id: UUID | None = None
    starts_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=360)
    topic: str | None = Field(default=None, max_length=240)
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def quarter_hour(self):
        if self.starts_at.minute % 15 != 0 or self.starts_at.second != 0:
            raise ValueError("Час має бути кратним 15 хвилинам")
        return self


class HardenedTrialCreate(BaseModel):
    student_id: UUID
    location_id: UUID | None = None
    room_id: UUID | None = None
    staff_id: UUID | None = None
    starts_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=180)


class HardenedTrialUpdate(BaseModel):
    starts_at: datetime | None = None
    location_id: UUID | None = None
    room_id: UUID | None = None
    staff_id: UUID | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=180)


class IndividualLessonCreate(BaseModel):
    student_id: UUID
    location_id: UUID | None = None
    room_id: UUID | None = None
    staff_id: UUID | None = None
    starts_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=360)
    topic: str | None = Field(default=None, max_length=240)
    notes: str | None = Field(default=None, max_length=4000)


class IndividualLessonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    student_id: UUID
    location_id: UUID | None
    room_id: UUID | None
    staff_id: UUID | None
    starts_at: datetime
    duration_minutes: int
    topic: str | None
    notes: str | None
    status: str
    finalized_at: datetime | None


class IndividualAttendanceCreate(BaseModel):
    status: AttendanceStatus
    note: str | None = Field(default=None, max_length=300)


class IndividualAttendanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    session_id: UUID
    student_id: UUID
    status: str
    note: str | None


class LearningPauseCreate(BaseModel):
    keep_group_seat: bool = True
    pause_subscription: bool = False
    resume_on: date | None = None
    note: str | None = Field(default=None, max_length=300)


class LearningResumeCreate(BaseModel):
    resume_subscription: bool = False


def _require_capability(capability: str):
    def dependency(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
        if not hardening.has_capability(db, access.organization_id, access.user_id, access.role, capability):
            raise HTTPException(status_code=403, detail="Недостатньо прав для цієї дії")
        return access
    return dependency


def _require_any_capability(*capabilities: str):
    def dependency(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
        if not any(
            hardening.has_capability(db, access.organization_id, access.user_id, access.role, capability)
            for capability in capabilities
        ):
            raise HTTPException(status_code=403, detail="Недостатньо прав для цієї дії")
        return access
    return dependency


def _require_owner(access: OrgAccess = Depends(get_org_access)) -> OrgAccess:
    if access.role != StaffRole.OWNER:
        raise HTTPException(status_code=403, detail="Ця дія доступна лише власнику організації")
    return access


@router.patch("/staff/{staff_id}", response_model=StaffRead)
def update_staff_hardened(
    staff_id: UUID,
    data: StaffUpdate,
    access: OrgAccess = Depends(_require_capability("staff.manage")),
    db: Session = Depends(get_db),
):
    if data.role == StaffRole.OWNER and access.role != StaffRole.OWNER:
        raise HTTPException(status_code=403, detail="Лише власник може призначати роль власника")
    return hardening.update_staff_and_access(db, access.organization_id, staff_id, data, access.user_id)


@router.put("/staff/{staff_id}/capabilities", response_model=list[CapabilityRead])
def set_staff_capabilities(
    staff_id: UUID,
    data: CapabilityUpdate,
    access: OrgAccess = Depends(_require_owner),
    db: Session = Depends(get_db),
):
    return hardening.set_staff_capabilities(db, access.organization_id, staff_id, data.capabilities, access.user_id)


@router.get("/staff/{staff_id}/capabilities", response_model=list[CapabilityRead])
def get_staff_capabilities(
    staff_id: UUID,
    access: OrgAccess = Depends(_require_capability("staff.manage")),
    db: Session = Depends(get_db),
):
    crm.scoped_get(db, Staff, access.organization_id, staff_id)
    return list(db.scalars(select(StaffCapability).where(
        StaffCapability.organization_id == access.organization_id,
        StaffCapability.staff_id == staff_id,
    ).order_by(StaffCapability.capability)))


@router.delete("/locations/{location_id}", status_code=204)
def delete_location_hardened(
    location_id: UUID,
    access: OrgAccess = Depends(_require_capability("settings.manage")),
    db: Session = Depends(get_db),
):
    crm.scoped_get(db, Location, access.organization_id, location_id)
    room = db.scalar(select(Room.id).where(
        Room.organization_id == access.organization_id,
        Room.location_id == location_id,
    ).limit(1))
    if room is not None:
        raise HTTPException(
            status_code=409,
            detail="У локації налаштовані кімнати. Спочатку перенесіть або приберіть кімнати.",
        )
    individual = db.scalar(select(IndividualLessonSession.id).where(
        IndividualLessonSession.organization_id == access.organization_id,
        IndividualLessonSession.location_id == location_id,
    ).limit(1))
    if individual is not None:
        raise HTTPException(
            status_code=409,
            detail="Для цієї локації є індивідуальні заняття. Щоб не втратити історію, її видалити не можна.",
        )
    schedule_history = db.scalar(select(GroupScheduleHistory.id).where(
        GroupScheduleHistory.organization_id == access.organization_id,
        GroupScheduleHistory.location_id == location_id,
    ).limit(1))
    if schedule_history is not None:
        raise HTTPException(
            status_code=409,
            detail="Локація вже використовується в історії розкладу. Її можна деактивувати, але не видалити.",
        )
    crm.delete_location(db, access.organization_id, location_id, access.user_id)
    return None


@router.post("/rooms", response_model=RoomRead, status_code=201)
def create_room(
    data: RoomCreate,
    access: OrgAccess = Depends(_require_capability("groups.manage")),
    db: Session = Depends(get_db),
):
    return hardening.create_room(db, access.organization_id, data.location_id, data.name, data.capacity)


@router.get("/rooms", response_model=list[RoomRead])
def rooms(
    location_id: UUID | None = None,
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    return hardening.list_rooms(db, access.organization_id, location_id)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group_hardened(
    group_id: UUID,
    access: OrgAccess = Depends(_require_capability("groups.manage")),
    db: Session = Depends(get_db),
):
    group = crm.scoped_get(db, Group, access.organization_id, group_id)
    lesson_ids = list(db.scalars(select(LessonSession.id).where(
        LessonSession.organization_id == access.organization_id,
        LessonSession.group_id == group.id,
    )))
    if lesson_ids:
        db.execute(delete(LessonResourceAssignment).where(
            LessonResourceAssignment.organization_id == access.organization_id,
            LessonResourceAssignment.session_id.in_(lesson_ids),
        ))
    db.execute(delete(GroupRoomAssignment).where(
        GroupRoomAssignment.organization_id == access.organization_id,
        GroupRoomAssignment.group_id == group.id,
    ))
    db.execute(delete(GroupScheduleHistory).where(
        GroupScheduleHistory.organization_id == access.organization_id,
        GroupScheduleHistory.group_id == group.id,
    ))
    # Legacy delete_group contains the authoritative history guards. If one
    # rejects deletion, this request transaction is rolled back on session close.
    crm.delete_group(db, access.organization_id, group.id, access.user_id)
    return None


@router.put("/groups/{group_id}", response_model=GroupRead)
def update_group_hardened(
    group_id: UUID,
    data: HardenedGroupUpdate,
    access: OrgAccess = Depends(_require_capability("groups.manage")),
    db: Session = Depends(get_db),
):
    return hardening.update_group_hardened(db, access.organization_id, group_id, data, access.user_id)


@router.post("/group-schedules", response_model=GroupScheduleRead, status_code=201)
def create_group_schedule_hardened(
    data: GroupScheduleCreate,
    access: OrgAccess = Depends(_require_capability("schedule.manage")),
    db: Session = Depends(get_db),
):
    return hardening.create_group_schedule_hardened(db, access.organization_id, data, access.user_id)


@router.get("/group-schedules", response_model=list[GroupScheduleRead])
def group_schedules_hardened(
    group_id: UUID | None = None,
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    return hardening.list_group_schedules_strict(db, access.organization_id, access.user_id, access.role, group_id)


def _preflight_recurring_slots(db: Session, org_id: UUID, data: HardenedGroupFormation) -> None:
    if not data.schedule_slots:
        return
    tz = hardening.organization_timezone(db, org_id)
    today = hardening.organization_today(db, org_id)
    monday = today - timedelta(days=today.weekday())
    for slot in data.schedule_slots:
        slot_time = datetime.strptime(slot.start_time, "%H:%M").time()
        current = monday + timedelta(days=slot.weekday)
        if current < today:
            current += timedelta(days=7)
        for _ in range(9):
            starts_at = datetime.combine(current, slot_time).replace(tzinfo=tz)
            reason = hardening.resource_conflict_reason(
                db, org_id, starts_at, slot.duration_minutes, data.location_id, data.room_id, None,
            )
            if reason:
                raise HTTPException(status_code=409, detail=reason)
            current += timedelta(days=7)


@router.post("/groups/form", response_model=GroupFormationResult, status_code=201)
def form_group_hardened(
    data: HardenedGroupFormation,
    access: OrgAccess = Depends(_require_capability("groups.manage")),
    db: Session = Depends(get_db),
):
    _preflight_recurring_slots(db, access.organization_id, data)
    group, ids = crm.form_group(db, access.organization_id, data, access.user_id)
    # crm.form_group is kept for compatibility, but its legacy date.today()
    # default is server-local. Normalize newly-created enrollments to the
    # organization's own calendar date before any historical roster is used.
    formed_on = hardening.organization_today(db, access.organization_id)
    for enrollment in db.scalars(select(Enrollment).where(
        Enrollment.organization_id == access.organization_id,
        Enrollment.group_id == group.id,
        Enrollment.student_id.in_(ids),
    )):
        enrollment.started_at = formed_on
    if data.room_id is not None:
        hardening.assign_group_room(db, access.organization_id, group.id, data.room_id)
    active = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == access.organization_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.is_active.is_(True),
    )))
    hardening.save_schedule_history(db, access.organization_id, group, active, access.user_id)
    hardening.reconcile_group_future_sessions(db, access.organization_id, group, access.user_id)
    db.commit()
    return GroupFormationResult(group=group, enrolled_student_ids=ids)


@router.post("/enrollments", response_model=EnrollmentRead, status_code=201)
def create_enrollment_hardened(
    data: EnrollmentCreate,
    access: OrgAccess = Depends(_require_capability("students.manage")),
    db: Session = Depends(get_db),
):
    return hardening.create_enrollment_hardened(db, access.organization_id, data, access.user_id)


@router.post("/students/{student_id}/transfer", response_model=EnrollmentRead)
def transfer_student_hardened(
    student_id: UUID,
    data: StudentTransfer,
    access: OrgAccess = Depends(_require_capability("students.manage")),
    db: Session = Depends(get_db),
):
    return hardening.transfer_student_hardened(
        db, access.organization_id, student_id, data.to_group_id, data.started_at, access.user_id,
    )


@router.get("/groups/{group_id}/roster", response_model=list[GroupRosterStudent])
def group_roster_hardened(
    group_id: UUID,
    at: date | None = Query(default=None),
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    hardening.ensure_group_access(db, access.organization_id, access.user_id, access.role, group_id)
    on_date = at or hardening.organization_today(db, access.organization_id)
    return hardening.historical_roster(db, access.organization_id, group_id, on_date)


@router.get("/groups/{group_id}/detail", response_model=GroupDetail)
def group_detail_hardened(
    group_id: UUID,
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    return hardening.group_detail_strict(db, access.organization_id, group_id, access.user_id, access.role)


@router.post("/lesson-sessions", response_model=LessonSessionRead, status_code=201)
def create_lesson_session_hardened(
    data: HardenedLessonCreate,
    access: OrgAccess = Depends(_require_any_capability("schedule.manage", "teaching")),
    db: Session = Depends(get_db),
):
    return hardening.create_lesson_session_hardened(db, access.organization_id, data, access.user_id, access.role)


@router.get("/lesson-sessions", response_model=list[LessonSessionRead])
def lesson_sessions_read_only(
    group_id: UUID | None = None,
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    return hardening.list_lesson_sessions_read_only(db, access.organization_id, access.user_id, access.role, group_id)


@router.put("/lesson-sessions/{session_id}/attendance", response_model=list[AttendanceRead])
def save_attendance_hardened(
    session_id: UUID,
    data: AttendanceBulkUpdate,
    access: OrgAccess = Depends(_require_capability("attendance.manage")),
    db: Session = Depends(get_db),
):
    for item in data.items:
        if item.status == AttendanceStatus.LATE:
            existing = db.scalar(select(Attendance).where(
                Attendance.organization_id == access.organization_id,
                Attendance.session_id == session_id,
                Attendance.student_id == item.student_id,
            ))
            if existing is None or existing.status != AttendanceStatus.LATE:
                raise HTTPException(status_code=422, detail="Статус «Запізнення» залишено лише для старої історії")
    return hardening.save_attendance_hardened(
        db, access.organization_id, session_id, data.items, access.user_id, access.role,
    )


@router.post("/lesson-sessions/{session_id}/reopen", response_model=LessonSessionRead)
def reopen_lesson(
    session_id: UUID,
    access: OrgAccess = Depends(_require_capability("attendance.manage")),
    db: Session = Depends(get_db),
):
    return hardening.reopen_group_lesson(db, access.organization_id, session_id, access.user_id, access.role)


@router.get("/lesson-sessions/{session_id}/attendance", response_model=list[AttendanceRead])
def get_attendance_hardened(
    session_id: UUID,
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    session = crm.scoped_get(db, LessonSession, access.organization_id, session_id)
    hardening.ensure_group_access(db, access.organization_id, access.user_id, access.role, session.group_id)
    return list(db.scalars(select(Attendance).where(
        Attendance.organization_id == access.organization_id,
        Attendance.session_id == session.id,
    ).order_by(Attendance.student_id)))


@router.post("/trial-lessons", response_model=TrialLessonRead, status_code=201)
def create_trial_hardened(
    data: HardenedTrialCreate,
    access: OrgAccess = Depends(_require_capability("leads.manage")),
    db: Session = Depends(get_db),
):
    return hardening.create_trial_hardened(db, access.organization_id, data, access.user_id)


@router.patch("/trial-lessons/{trial_id}", response_model=TrialLessonRead)
def update_trial_hardened(
    trial_id: UUID,
    data: HardenedTrialUpdate,
    access: OrgAccess = Depends(_require_capability("leads.manage")),
    db: Session = Depends(get_db),
):
    return hardening.update_trial_hardened(db, access.organization_id, trial_id, data, access.user_id)


@router.post("/student-subscriptions", response_model=StudentSubscriptionRead, status_code=201)
def create_student_subscription_hardened(
    data: StudentSubscriptionCreate,
    access: OrgAccess = Depends(_require_capability("finance.manage")),
    db: Session = Depends(get_db),
):
    return hardening.create_student_subscription_hardened(db, access.organization_id, data)


@router.post("/billing/charges", response_model=SubscriptionChargeResult, status_code=201)
def create_subscription_charge_hardened(
    data: SubscriptionChargeCreate,
    access: OrgAccess = Depends(_require_capability("finance.manage")),
    db: Session = Depends(get_db),
):
    subscription, payment = hardening.create_subscription_charge_hardened(
        db, access.organization_id, data, access.user_id,
    )
    return SubscriptionChargeResult(subscription=subscription, payment=payment)


@router.post("/individual-lessons", response_model=IndividualLessonRead, status_code=201)
def create_individual_lesson(
    data: IndividualLessonCreate,
    access: OrgAccess = Depends(_require_capability("schedule.manage")),
    db: Session = Depends(get_db),
):
    return hardening.create_individual_lesson(db, access.organization_id, data, access.user_id)


@router.get("/individual-lessons", response_model=list[IndividualLessonRead])
def individual_lessons(
    student_id: UUID | None = None,
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    if access.role == StaffRole.TEACHER and not hardening.has_capability(
        db, access.organization_id, access.user_id, access.role, "schedule.manage"
    ):
        raise HTTPException(status_code=403, detail="Недостатньо прав для індивідуального розкладу")
    return hardening.list_individual_lessons(db, access.organization_id, student_id)


@router.put("/individual-lessons/{session_id}/attendance", response_model=IndividualAttendanceRead)
def individual_attendance(
    session_id: UUID,
    data: IndividualAttendanceCreate,
    access: OrgAccess = Depends(_require_capability("attendance.manage")),
    db: Session = Depends(get_db),
):
    if data.status == AttendanceStatus.LATE:
        raise HTTPException(status_code=422, detail="Статус «Запізнення» більше не використовується")
    return hardening.save_individual_attendance(
        db, access.organization_id, session_id, data.status, data.note, access.user_id,
    )


@router.delete("/students/{student_id}", status_code=204)
def delete_student_hardened(
    student_id: UUID,
    access: OrgAccess = Depends(_require_capability("students.manage")),
    db: Session = Depends(get_db),
):
    student = crm.scoped_get(db, Student, access.organization_id, student_id)
    individual_ids = list(db.scalars(select(IndividualLessonSession.id).where(
        IndividualLessonSession.organization_id == access.organization_id,
        IndividualLessonSession.student_id == student.id,
    )))
    if individual_ids:
        individual_attendance = db.scalar(select(IndividualAttendance.id).where(
            IndividualAttendance.organization_id == access.organization_id,
            IndividualAttendance.session_id.in_(individual_ids),
        ).limit(1))
        derived_billing = db.scalar(select(IndividualDerivedBilling.id).where(
            IndividualDerivedBilling.organization_id == access.organization_id,
            IndividualDerivedBilling.session_id.in_(individual_ids),
        ).limit(1))
        if individual_attendance is not None or derived_billing is not None:
            raise HTTPException(
                status_code=409,
                detail="Для учня вже є історія індивідуальних занять. Використайте «Архів», щоб не втратити дані.",
            )
        db.execute(delete(IndividualLessonSession).where(
            IndividualLessonSession.organization_id == access.organization_id,
            IndividualLessonSession.student_id == student.id,
        ))

    trial_ids = list(db.scalars(select(crm.TrialLesson.id).where(
        crm.TrialLesson.organization_id == access.organization_id,
        crm.TrialLesson.student_id == student.id,
    )))
    if trial_ids:
        db.execute(delete(TrialResourceAssignment).where(
            TrialResourceAssignment.organization_id == access.organization_id,
            TrialResourceAssignment.trial_id.in_(trial_ids),
        ))

    # A consume/no-consume choice without preserved attendance is draft state,
    # not immutable learning history, and may be removed with the draft student.
    db.execute(delete(AttendanceDecision).where(
        AttendanceDecision.organization_id == access.organization_id,
        AttendanceDecision.student_id == student.id,
    ))
    crm.delete_student(db, access.organization_id, student.id, access.user_id)
    return None


@router.patch("/students/{student_id}/status")
def update_student_lifecycle_hardened(
    student_id: UUID,
    data: StudentLifecycleUpdate,
    access: OrgAccess = Depends(_require_capability("students.manage")),
    db: Session = Depends(get_db),
):
    student = crm.scoped_get(db, Student, access.organization_id, student_id)
    today = hardening.organization_today(db, access.organization_id)
    if data.student_status == StudentStatus.PAUSED:
        student.student_status = StudentStatus.PAUSED
        for enrollment in db.scalars(select(Enrollment).where(
            Enrollment.organization_id == access.organization_id,
            Enrollment.student_id == student.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )):
            enrollment.status = EnrollmentStatus.PAUSED
    elif data.student_status == StudentStatus.ACTIVE:
        student.student_status = StudentStatus.ACTIVE
        for enrollment in db.scalars(select(Enrollment).where(
            Enrollment.organization_id == access.organization_id,
            Enrollment.student_id == student.id,
            Enrollment.status == EnrollmentStatus.PAUSED,
        )):
            enrollment.status = EnrollmentStatus.ACTIVE
    elif data.student_status == StudentStatus.ARCHIVED:
        student.student_status = StudentStatus.ARCHIVED
        for enrollment in db.scalars(select(Enrollment).where(
            Enrollment.organization_id == access.organization_id,
            Enrollment.student_id == student.id,
            Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
        )):
            enrollment.status = EnrollmentStatus.FINISHED
            enrollment.ended_at = today
        for subscription in db.scalars(select(StudentSubscription).where(
            StudentSubscription.organization_id == access.organization_id,
            StudentSubscription.student_id == student.id,
            StudentSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED]),
        )):
            subscription.auto_renew = False
    else:
        student.student_status = data.student_status
    crm.record_audit(db, access.organization_id, "student", student.id, "student.lifecycle_hardened", {
        "student_status": student.student_status.value,
    }, access.user_id)
    db.commit()
    db.refresh(student)
    return student


@router.post("/students/{student_id}/pause-learning")
def pause_learning(
    student_id: UUID,
    data: LearningPauseCreate,
    access: OrgAccess = Depends(_require_capability("students.manage")),
    db: Session = Depends(get_db),
):
    student = crm.scoped_get(db, Student, access.organization_id, student_id)
    student.student_status = StudentStatus.PAUSED
    enrollments = list(db.scalars(select(Enrollment).where(
        Enrollment.organization_id == access.organization_id,
        Enrollment.student_id == student.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    )))
    if data.keep_group_seat:
        for row in enrollments:
            row.status = EnrollmentStatus.PAUSED
    else:
        today = hardening.organization_today(db, access.organization_id)
        for row in enrollments:
            row.status = EnrollmentStatus.FINISHED
            row.ended_at = today
    paused_subscription_ids = []
    if data.pause_subscription:
        subscriptions = list(db.scalars(select(StudentSubscription).where(
            StudentSubscription.organization_id == access.organization_id,
            StudentSubscription.student_id == student.id,
            StudentSubscription.status == SubscriptionStatus.ACTIVE,
        )))
        for subscription in subscriptions:
            pause = crm.pause_subscription(
                db, access.organization_id, subscription.id,
                hardening.organization_today(db, access.organization_id), data.resume_on, data.note, access.user_id,
            )
            paused_subscription_ids.append(str(pause.subscription_id))
    crm.record_audit(db, access.organization_id, "student", student.id, "student.learning_paused", {
        "keep_group_seat": data.keep_group_seat,
        "paused_subscription_ids": paused_subscription_ids,
        "resume_on": data.resume_on.isoformat() if data.resume_on else None,
    }, access.user_id)
    db.commit()
    return {"student_id": student.id, "status": student.student_status.value, "paused_subscription_ids": paused_subscription_ids}


@router.post("/students/{student_id}/resume-learning")
def resume_learning(
    student_id: UUID,
    data: LearningResumeCreate,
    access: OrgAccess = Depends(_require_capability("students.manage")),
    db: Session = Depends(get_db),
):
    student = crm.scoped_get(db, Student, access.organization_id, student_id)
    student.student_status = StudentStatus.ACTIVE
    for row in db.scalars(select(Enrollment).where(
        Enrollment.organization_id == access.organization_id,
        Enrollment.student_id == student.id,
        Enrollment.status == EnrollmentStatus.PAUSED,
    )):
        row.status = EnrollmentStatus.ACTIVE
    resumed = []
    if data.resume_subscription:
        for subscription in list(db.scalars(select(StudentSubscription).where(
            StudentSubscription.organization_id == access.organization_id,
            StudentSubscription.student_id == student.id,
            StudentSubscription.status == SubscriptionStatus.PAUSED,
        ))):
            crm.resume_subscription(db, access.organization_id, subscription.id, None, access.user_id)
            resumed.append(str(subscription.id))
    crm.record_audit(db, access.organization_id, "student", student.id, "student.learning_resumed", {
        "resumed_subscription_ids": resumed,
    }, access.user_id)
    db.commit()
    return {"student_id": student.id, "status": student.student_status.value, "resumed_subscription_ids": resumed}


@router.post("/groups/{group_id}/archive")
def archive_group(
    group_id: UUID,
    access: OrgAccess = Depends(_require_capability("groups.manage")),
    db: Session = Depends(get_db),
):
    group = crm.scoped_get(db, Group, access.organization_id, group_id)
    group.is_active = False
    today = hardening.organization_today(db, access.organization_id)
    for schedule in db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == access.organization_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.is_active.is_(True),
    )):
        schedule.is_active = False
    for session in db.scalars(select(LessonSession).where(
        LessonSession.organization_id == access.organization_id,
        LessonSession.group_id == group.id,
        LessonSession.status == "SCHEDULED",
    )):
        if hardening._local_date(db, access.organization_id, session.starts_at) >= today:
            session.status = "CANCELLED"
    for enrollment in db.scalars(select(Enrollment).where(
        Enrollment.organization_id == access.organization_id,
        Enrollment.group_id == group.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    )):
        enrollment.status = EnrollmentStatus.FINISHED
        enrollment.ended_at = today
    crm.record_audit(db, access.organization_id, "group", group.id, "group.archived", {"ended_on": today.isoformat()}, access.user_id)
    db.commit()
    return {"group_id": group.id, "is_active": False}


@router.post("/staff/{staff_id}/groups", status_code=201)
def assign_staff_group_hardened(
    staff_id: UUID,
    data: StaffGroupAssignment,
    access: OrgAccess = Depends(_require_capability("staff.manage")),
    db: Session = Depends(get_db),
):
    staff = crm.scoped_get(db, Staff, access.organization_id, staff_id)
    group = crm.scoped_get(db, Group, access.organization_id, data.group_id)
    if not staff.is_active or not staff.can_teach:
        raise HTTPException(status_code=409, detail="Працівник не може бути призначений викладачем")
    room_id = hardening.group_room_id(db, access.organization_id, group.id)
    future = hardening._future_group_sessions(db, access.organization_id, group.id)
    for session in future:
        conflict = hardening.resource_conflict_reason(
            db, access.organization_id, session.starts_at, session.duration_minutes,
            session.location_id, room_id, staff.id, group_id=group.id, exclude_session_id=session.id,
        )
        if conflict:
            raise HTTPException(status_code=409, detail=conflict)
    assignment = crm.assign_staff_to_group(db, access.organization_id, staff.id, group.id, data.is_primary)
    for session in future:
        resources = db.scalar(select(LessonResourceAssignment).where(
            LessonResourceAssignment.organization_id == access.organization_id,
            LessonResourceAssignment.session_id == session.id,
        ))
        if resources is None:
            resources = LessonResourceAssignment(organization_id=access.organization_id, session_id=session.id)
            db.add(resources)
        if data.is_primary or resources.staff_id is None:
            resources.staff_id = staff.id
            resources.room_id = room_id
    crm.record_audit(db, access.organization_id, "staff", staff.id, "staff.assigned_group_hardened", {
        "group_id": str(group.id), "is_primary": data.is_primary,
    }, access.user_id)
    db.commit()
    return {"id": assignment.id, "group_id": assignment.group_id, "staff_id": assignment.staff_id, "is_primary": assignment.is_primary}


@router.get("/workspace/leads")
def workspace_leads_hardened(
    access: OrgAccess = Depends(_require_capability("leads.manage")),
    db: Session = Depends(get_db),
):
    return crm.list_lead_overview(db, access.organization_id)


@router.get("/workspace/students/page")
def workspace_students_page(
    q: str | None = None,
    status: StudentStatus | None = None,
    sort: str = Query(default="name", pattern="^(name|newest|oldest)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    return workspace_service.paginate_student_overview(
        db,
        access.organization_id,
        access.user_id,
        access.role,
        q=q,
        status=status,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/workspace/groups/page")
def workspace_groups_page(
    q: str | None = None,
    sort: str = Query(default="name", pattern="^(name|size_desc|size_asc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    return workspace_service.paginate_group_overview(
        db,
        access.organization_id,
        access.user_id,
        access.role,
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/workspace/students")
def workspace_students_paginated(
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    return hardening.filtered_workspace_students(db, access.organization_id, access.user_id, access.role, q, limit, offset)


@router.get("/workspace/groups")
def workspace_groups_paginated(
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    access: OrgAccess = Depends(get_org_access),
    db: Session = Depends(get_db),
):
    return hardening.filtered_workspace_groups(db, access.organization_id, access.user_id, access.role, q, limit, offset)
