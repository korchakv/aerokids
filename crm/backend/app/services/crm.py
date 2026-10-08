import hashlib
import re
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import Attendance, AttendanceStatus, AuditEvent, Contact, CrmStatus, Enrollment, EnrollmentStatus, Group, GroupSchedule, GroupStaff, LessonSession, LessonStatus, Location, Organization, OrganizationMembership, Payment, PaymentMethod, PaymentReminder, PaymentStatus, PaymentTransaction, PublicIntakeThrottle, Staff, StaffLocation, StaffRole, Student, StudentAvailability, StudentContact, StudentStatus, StudentSubscription, SubscriptionPause, SubscriptionPlan, SubscriptionStatus, SubscriptionUsage, MakeupCredit, TrialLesson, TrialStatus, User
from app.schemas import ContactCreate, EnrollmentCreate, GroupCreate, GroupUpdate, IntakeCreate, LeadDetailsUpdate, LocationCreate, OrganizationCreate, StudentCreate, TrialLessonCreate
from app.services.schedule_matching import enrollment_schedule_note, evaluate_schedule_match

def record_audit(
    db: Session,
    org_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    event_type: str,
    payload: dict | None = None,
    actor_user_id: UUID | None = None,
) -> AuditEvent:
    from app.services import audit_service
    return audit_service.record_audit(
        db, org_id, entity_type, entity_id, event_type, payload, actor_user_id,
    )


def list_audit_events(
    db: Session,
    org_id: UUID,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: int = 100,
) -> list[dict]:
    from app.services import audit_service
    return audit_service.list_audit_events(db, org_id, entity_type, entity_id, limit)

def ensure_group_capacity(db: Session, org_id: UUID, group: Group, student_id: UUID | None = None) -> None:
    if group.capacity is None:
        return
    already_enrolled = False
    if student_id is not None:
        already_enrolled = db.scalar(select(Enrollment.id).where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student_id,
            Enrollment.group_id == group.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )) is not None
    if already_enrolled:
        return

    occupied = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    )) or 0
    if occupied >= group.capacity:
        raise HTTPException(status_code=409, detail="Group has no available seats")


def _lead_service_call(name: str, *args, **kwargs):
    from app.services import lead_service
    return getattr(lead_service, name)(*args, **kwargs)


def enforce_public_intake_rate_limit(*args, **kwargs):
    return _lead_service_call("enforce_public_intake_rate_limit", *args, **kwargs)


def normalize_phone(value: str) -> str:
    from app.services import contact_service
    return contact_service.normalize_phone(value)

def create_organization(db: Session, data: OrganizationCreate) -> Organization:
    from app.services import organization_service
    return organization_service.create_organization(db, data)


def list_organizations(db: Session) -> list[Organization]:
    from app.services import organization_service
    return organization_service.list_organizations(db)


def update_organization(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> Organization:
    from app.services import organization_service
    return organization_service.update_organization(db, org_id, data, actor_user_id)


def require_organization(db: Session, org_id: UUID) -> Organization:
    from app.services import organization_service
    return organization_service.require_organization(db, org_id)


def scoped_get(db: Session, model, org_id: UUID, item_id: UUID):
    item = db.scalar(select(model).where(model.id == item_id, model.organization_id == org_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def create_location(db: Session, org_id: UUID, data: LocationCreate) -> Location:
    from app.services import location_service
    return location_service.create_location(db, org_id, data)


def list_locations(db: Session, org_id: UUID) -> list[Location]:
    from app.services import location_service
    return location_service.list_locations(db, org_id)


def delete_location(
    db: Session,
    org_id: UUID,
    location_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    from app.services import location_service
    return location_service.delete_location(db, org_id, location_id, actor_user_id)


def create_contact(db: Session, org_id: UUID, data: ContactCreate) -> Contact:
    from app.services import contact_service
    return contact_service.create_contact(db, org_id, data)

def list_contacts(db: Session, org_id: UUID) -> list[Contact]:
    from app.services import contact_service
    return contact_service.list_contacts(db, org_id)

def create_student(db: Session, org_id: UUID, data: StudentCreate) -> Student:
    from app.services import student_service
    return student_service.create_student(db, org_id, data)

def list_students(db: Session, org_id: UUID) -> list[Student]:
    from app.services import student_service
    return student_service.list_students(db, org_id)

def delete_student(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    from app.services import student_service
    return student_service.delete_student(db, org_id, student_id, actor_user_id)

def attach_contact(db: Session, org_id: UUID, student_id: UUID, contact_id: UUID, relation: str | None, is_primary: bool) -> StudentContact:
    from app.services import student_service
    return student_service.attach_contact(db, org_id, student_id, contact_id, relation, is_primary)

def create_trial(db: Session, org_id: UUID, data: TrialLessonCreate, actor_user_id: UUID | None = None) -> TrialLesson:
    from app.services import trial_service
    return trial_service.create_trial(db, org_id, data, actor_user_id)


def update_trial(db: Session, org_id: UUID, trial_id: UUID, starts_at: datetime | None, location_id: UUID | None, actor_user_id: UUID | None = None) -> TrialLesson:
    from app.services import trial_service
    return trial_service.update_trial(db, org_id, trial_id, starts_at, location_id, actor_user_id)


def list_trials(db: Session, org_id: UUID) -> list[TrialLesson]:
    from app.services import trial_service
    return trial_service.list_trials(db, org_id)

def create_group(db: Session, org_id: UUID, data: GroupCreate) -> Group:
    from app.services import group_service
    return group_service.create_group(db, org_id, data)


def update_group(
    db: Session,
    org_id: UUID,
    group_id: UUID,
    data: GroupUpdate,
    actor_user_id: UUID | None = None,
) -> Group:
    from app.services import group_service
    return group_service.update_group(db, org_id, group_id, data, actor_user_id)


def delete_group(
    db: Session,
    org_id: UUID,
    group_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    from app.services import group_service
    return group_service.delete_group(db, org_id, group_id, actor_user_id)


def list_groups(db: Session, org_id: UUID) -> list[Group]:
    from app.services import group_service
    return group_service.list_groups(db, org_id)

def create_enrollment(
    db: Session,
    org_id: UUID,
    data: EnrollmentCreate,
    actor_user_id: UUID | None = None,
) -> Enrollment:
    student = scoped_get(db, Student, org_id, data.student_id)
    group = scoped_get(db, Group, org_id, data.group_id)
    previous_crm_status = student.crm_status

    ensure_group_capacity(db, org_id, group, data.student_id)
    existing = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.group_id == group.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    ))
    if existing is not None:
        return existing

    group_slots = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.is_active.is_(True),
    ).order_by(GroupSchedule.weekday, GroupSchedule.start_time)))
    windows = list(db.scalars(select(StudentAvailability).where(
        StudentAvailability.organization_id == org_id,
        StudentAvailability.student_id == student.id,
    )))
    match = evaluate_schedule_match(group_slots, windows, group.location_id, student.preferred_location_id)
    note = enrollment_schedule_note(match, group_slots, windows)

    item = Enrollment(
        organization_id=org_id,
        student_id=student.id,
        group_id=group.id,
        started_at=data.started_at or date.today(),
        schedule_match=match.status,
        schedule_note=note,
    )
    db.add(item)
    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "student.enrolled",
        {
            "group_id": str(group.id),
            "group_name": group.name,
            "schedule_match": match.status,
            "schedule_note": note,
            "previous_crm_status": previous_crm_status.value,
            "skipped_funnel_stages": previous_crm_status not in {CrmStatus.TRIAL_COMPLETED, CrmStatus.WAITING_FOR_GROUP},
        },
        actor_user_id=actor_user_id,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Student is already enrolled in this group") from exc
    db.refresh(item)
    return item


def find_intake_phone_duplicates(*args, **kwargs):
    return _lead_service_call("find_intake_phone_duplicates", *args, **kwargs)


def _append_repeat_intake_note(*args, **kwargs):
    return _lead_service_call("_append_repeat_intake_note", *args, **kwargs)


def create_intake(*args, **kwargs):
    return _lead_service_call("create_intake", *args, **kwargs)


def update_lead_details(*args, **kwargs):
    return _lead_service_call("update_lead_details", *args, **kwargs)


def update_student_crm_status(*args, **kwargs):
    return _lead_service_call("update_student_crm_status", *args, **kwargs)


def student_detail(db: Session, org_id: UUID, student_id: UUID) -> tuple[Student, list[Contact], list[TrialLesson]]:
    student = scoped_get(db, Student, org_id, student_id)
    contacts = list(db.scalars(
        select(Contact)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student_id,
            Contact.organization_id == org_id,
        )
        .order_by(StudentContact.is_primary.desc(), Contact.full_name)
    ))
    trials = list(db.scalars(
        select(TrialLesson)
        .where(TrialLesson.organization_id == org_id, TrialLesson.student_id == student_id)
        .order_by(TrialLesson.starts_at.desc())
    ))
    return student, contacts, trials


def complete_trial(db: Session, org_id: UUID, trial_id: UUID, status, recommended_level: str | None, teacher_notes: str | None, actor_user_id: UUID | None = None) -> TrialLesson:
    trial = scoped_get(db, TrialLesson, org_id, trial_id)
    trial.status = status
    trial.recommended_level = recommended_level
    trial.teacher_notes = teacher_notes
    student = scoped_get(db, Student, org_id, trial.student_id)
    student.lead_close_reason = None
    student.lead_close_note = None
    if status.value == "completed":
        # A completed trial still needs an explicit business decision:
        # ready for a group, thinking/follow-up, or declined.
        student.crm_status = CrmStatus.TRIAL_COMPLETED
        student.next_contact_at = None
    elif status.value == "no_show":
        # No-show remains an active lead that needs contact/rescheduling.
        student.crm_status = CrmStatus.CONTACTED
        student.next_contact_at = None
    elif status.value == "cancelled":
        student.crm_status = CrmStatus.CONTACTED
        student.next_contact_at = None
    record_audit(
        db,
        org_id,
        "student",
        student.id,
        f"trial.{status.value}",
        {"trial_id": str(trial.id), "recommended_level": recommended_level, "teacher_notes": teacher_notes},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(trial)
    return trial


def defer_lead(*args, **kwargs):
    return _lead_service_call("defer_lead", *args, **kwargs)


def update_lead_outcome(*args, **kwargs):
    return _lead_service_call("update_lead_outcome", *args, **kwargs)


def list_waiting_candidates(db: Session, org_id: UUID) -> list[dict]:
    students = list(db.scalars(
        select(Student)
        .where(Student.organization_id == org_id, Student.crm_status == CrmStatus.WAITING_FOR_GROUP)
        .order_by(Student.age_at_inquiry, Student.created_at)
    ))
    result: list[dict] = []
    for student in students:
        latest_trial = db.scalar(
            select(TrialLesson)
            .where(
                TrialLesson.organization_id == org_id,
                TrialLesson.student_id == student.id,
            )
            .order_by(TrialLesson.starts_at.desc())
            .limit(1)
        )
        result.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_phone": student.phone,
            "age": student.age_at_inquiry,
            "recommended_level": latest_trial.recommended_level if latest_trial else None,
            "source": student.source,
        })
    return result


def form_group(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> tuple[Group, list[UUID]]:
    require_organization(db, org_id)
    if data.location_id:
        scoped_get(db, Location, org_id, data.location_id)
    if data.min_age and data.max_age and data.min_age > data.max_age:
        raise HTTPException(status_code=422, detail="min_age cannot be greater than max_age")
    if len(set(data.student_ids)) != len(data.student_ids):
        raise HTTPException(status_code=422, detail="Duplicate students are not allowed")
    if len(data.student_ids) > data.capacity:
        raise HTTPException(status_code=422, detail="Selected students exceed group capacity")

    students: list[Student] = []
    for student_id in data.student_ids:
        student = scoped_get(db, Student, org_id, student_id)
        if student.crm_status != CrmStatus.WAITING_FOR_GROUP:
            raise HTTPException(status_code=409, detail=f"Student {student_id} is not waiting for a group")
        students.append(student)

    group = Group(
        organization_id=org_id,
        location_id=data.location_id,
        name=data.name,
        capacity=data.capacity,
        min_age=data.min_age,
        max_age=data.max_age,
    )
    db.add(group)
    try:
        db.flush()
        schedule_keys: set[tuple[int, str]] = set()
        for slot in data.schedule_slots:
            key = (slot.weekday, slot.start_time)
            if key in schedule_keys:
                raise HTTPException(status_code=422, detail="Duplicate group schedule slots are not allowed")
            schedule_keys.add(key)
            db.add(GroupSchedule(
                organization_id=org_id,
                group_id=group.id,
                weekday=slot.weekday,
                start_time=time.fromisoformat(slot.start_time),
                duration_minutes=slot.duration_minutes,
            ))

        for student in students:
            windows = list(db.scalars(select(StudentAvailability).where(
                StudentAvailability.organization_id == org_id,
                StudentAvailability.student_id == student.id,
            )))
            match = evaluate_schedule_match(data.schedule_slots, windows, data.location_id, student.preferred_location_id)
            note = enrollment_schedule_note(match, data.schedule_slots, windows)
            db.add(Enrollment(
                organization_id=org_id,
                student_id=student.id,
                group_id=group.id,
                started_at=date.today(),
                schedule_match=match.status,
                schedule_note=note,
            ))
            student.crm_status = CrmStatus.ENROLLED
            student.student_status = StudentStatus.ACTIVE
            student.next_contact_at = None
            student.deferred_until = None
            student.deferred_reason = None
            student.deferred_note = None
            record_audit(db, org_id, "student", student.id, "student.enrolled", {
                "group_id": str(group.id), "group_name": group.name,
                "schedule_match": match.status, "schedule_note": note,
            }, actor_user_id=actor_user_id)
        record_audit(db, org_id, "group", group.id, "group.created", {
            "name": group.name,
            "student_count": len(students),
            "schedule_slots": len(data.schedule_slots),
        }, actor_user_id=actor_user_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not form group; check name and enrollments") from exc

    db.refresh(group)
    return group, [student.id for student in students]


def enroll_student_without_group(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    actor_user_id: UUID | None = None,
) -> Student:
    student = scoped_get(db, Student, org_id, student_id)

    active_enrollment = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    ))
    if active_enrollment is not None:
        raise HTTPException(status_code=409, detail="Student is already enrolled in a group")

    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    student.lead_close_reason = None
    student.lead_close_note = None
    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "student.enrolled_without_group",
        {"group_id": None, "location_id": None},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(student)
    return student


def student_profile(db: Session, org_id: UUID, student_id: UUID):
    student, contacts, trials = student_detail(db, org_id, student_id)
    rows = db.execute(
        select(Enrollment, Group)
        .join(Group, Group.id == Enrollment.group_id)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student_id,
            Group.organization_id == org_id,
        )
        .order_by(Enrollment.started_at.desc())
    ).all()
    groups = [{
        "group_id": group.id,
        "group_name": group.name,
        "enrollment_id": enrollment.id,
        "enrollment_status": enrollment.status,
        "started_at": enrollment.started_at,
        "location_id": group.location_id,
    } for enrollment, group in rows]
    return student, contacts, trials, groups


def update_student_lifecycle(db: Session, org_id: UUID, student_id: UUID, status: StudentStatus, actor_user_id: UUID | None = None) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.student_status = status
    record_audit(db, org_id, "student", student.id, "student.status_changed", {"student_status": status.value}, actor_user_id=actor_user_id)
    if status == StudentStatus.ARCHIVED:
        active_enrollments = list(db.scalars(select(Enrollment).where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student_id,
            Enrollment.status == "ACTIVE",
        )))
        for enrollment in active_enrollments:
            enrollment.status = "FINISHED"
            enrollment.ended_at = date.today()
    db.commit()
    db.refresh(student)
    return student


def transfer_student(db: Session, org_id: UUID, student_id: UUID, to_group_id: UUID, started_at: date | None = None, actor_user_id: UUID | None = None) -> Enrollment:
    student = scoped_get(db, Student, org_id, student_id)
    target = scoped_get(db, Group, org_id, to_group_id)
    ensure_group_capacity(db, org_id, target, student_id)

    active_enrollments = list(db.scalars(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student_id,
        Enrollment.status == "ACTIVE",
    )))
    for enrollment in active_enrollments:
        if enrollment.group_id == target.id:
            return enrollment
        enrollment.status = "FINISHED"
        enrollment.ended_at = (started_at or date.today())

    existing = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student_id,
        Enrollment.group_id == target.id,
    ))
    if existing:
        existing.status = "ACTIVE"
        existing.started_at = started_at or date.today()
        existing.ended_at = None
        enrollment = existing
    else:
        enrollment = Enrollment(
            organization_id=org_id,
            student_id=student.id,
            group_id=target.id,
            started_at=started_at or date.today(),
        )
        db.add(enrollment)

    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    record_audit(db, org_id, "student", student.id, "student.transferred", {"to_group_id": str(target.id), "to_group_name": target.name}, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def create_group_schedule(db: Session, org_id: UUID, data) -> GroupSchedule:
    from app.services import scheduling_service
    return scheduling_service.create_group_schedule(db, org_id, data)

def list_group_schedules(db: Session, org_id: UUID, group_id: UUID | None = None, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[GroupSchedule]:
    from app.services import scheduling_service
    return scheduling_service.list_group_schedules(db, org_id, group_id, user_id, role)

def group_roster(db: Session, org_id: UUID, group_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[dict]:
    ensure_group_access(db, org_id, user_id, role, group_id)
    rows = db.execute(
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id == group_id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
            Student.organization_id == org_id,
            Student.student_status == StudentStatus.ACTIVE,
        )
        .order_by(Student.first_name, Student.last_name)
    ).scalars().all()
    return [{
        "student_id": student.id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "age": student.age_at_inquiry,
    } for student in rows]


def group_detail(db: Session, org_id: UUID, group_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> dict:
    if role == StaffRole.ACCOUNTANT:
        group = scoped_get(db, Group, org_id, group_id)
    else:
        group = ensure_group_access(db, org_id, user_id, role, group_id)

    schedules = list(db.scalars(
        select(GroupSchedule)
        .where(
            GroupSchedule.organization_id == org_id,
            GroupSchedule.group_id == group.id,
            GroupSchedule.is_active.is_(True),
        )
        .order_by(GroupSchedule.weekday, GroupSchedule.start_time)
    ))
    enrollments = list(db.scalars(
        select(Enrollment)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id == group.id,
            Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
        )
        .order_by(Enrollment.started_at, Enrollment.id)
    ))
    finance_visible = role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.TEACHER, StaffRole.ACCOUNTANT}
    members = []
    today = date.today()

    for enrollment in enrollments:
        student = scoped_get(db, Student, org_id, enrollment.student_id)
        contact = _primary_contact_for_student(db, org_id, student.id)

        attendance_rows = list(db.scalars(
            select(Attendance)
            .join(LessonSession, LessonSession.id == Attendance.session_id)
            .where(
                Attendance.organization_id == org_id,
                Attendance.student_id == student.id,
                LessonSession.organization_id == org_id,
                LessonSession.group_id == group.id,
            )
        ))
        attendance_counts = {
            "present": sum(row.status == AttendanceStatus.PRESENT for row in attendance_rows),
            "absent": sum(row.status == AttendanceStatus.ABSENT for row in attendance_rows),
            "late": sum(row.status == AttendanceStatus.LATE for row in attendance_rows),
            "excused": sum(row.status == AttendanceStatus.EXCUSED for row in attendance_rows),
        }
        attendance_total = len(attendance_rows)
        attended = attendance_counts["present"] + attendance_counts["late"]
        attendance_summary = {
            **attendance_counts,
            "total": attendance_total,
            "attendance_rate": round(attended / attendance_total * 100, 1) if attendance_total else 0.0,
        }

        billing = None
        payment_rows: list[Payment] = []
        if finance_visible:
            payment_rows = list(db.scalars(
                select(Payment)
                .where(Payment.organization_id == org_id, Payment.student_id == student.id)
                .order_by(Payment.created_at.desc())
            ))
            subscriptions = list(db.scalars(
                select(StudentSubscription)
                .where(StudentSubscription.organization_id == org_id, StudentSubscription.student_id == student.id)
                .order_by(StudentSubscription.starts_on.desc())
            ))
            subscription_by_id = {item.id: item for item in subscriptions}
            for payment in payment_rows:
                linked = subscription_by_id.get(payment.subscription_id) if payment.subscription_id else None
                payment.plan_id = linked.plan_id if linked else None
                _attach_payment_financials(db, org_id, payment)

            latest_subscription = subscriptions[0] if subscriptions else None
            plan = scoped_get(db, SubscriptionPlan, org_id, latest_subscription.plan_id) if latest_subscription else None
            lessons_used = None
            lessons_remaining = None
            if latest_subscription and plan:
                usage_summary = subscription_usage_summary(db, org_id, latest_subscription)
                lessons_used = usage_summary["used_lessons"]
                lessons_remaining = usage_summary["remaining_lessons"]
            pending = [item for item in payment_rows if item.status != PaymentStatus.CANCELLED and item.balance_minor > 0]
            dated_pending = [item for item in pending if item.due_date is not None]
            overdue = [item for item in dated_pending if item.due_date < today]
            due_today = [item for item in dated_pending if item.due_date == today]
            next_due_date = min((item.due_date for item in dated_pending), default=None)
            last_paid = next((item for item in payment_rows if item.paid_minor - item.refunded_minor > 0), None)
            if overdue:
                billing_status = "overdue"
            elif due_today:
                billing_status = "due"
            elif pending:
                billing_status = "upcoming"
            elif latest_subscription and latest_subscription.status == SubscriptionStatus.ACTIVE and (latest_subscription.ends_on is None or latest_subscription.ends_on >= today):
                billing_status = "current"
            else:
                billing_status = "no_plan"

            billing = {
                "status": billing_status,
                "plan_name": plan.name if plan else None,
                "lessons_used": lessons_used,
                "lessons_included": latest_subscription.lessons_included if latest_subscription else (plan.lessons_included if plan else None),
                "lessons_remaining": lessons_remaining,
                "amount_due_minor": sum(item.balance_minor for item in pending),
                "next_due_date": next_due_date,
                "last_paid_at": last_paid.paid_at if last_paid else None,
                "last_paid_minor": (last_paid.paid_minor - last_paid.refunded_minor) if last_paid else None,
                "subscription_ends_on": latest_subscription.ends_on if latest_subscription else None,
            }

        members.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_phone": student.phone,
            "age": student.age_at_inquiry,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "enrollment_started_at": enrollment.started_at,
            "enrollment_status": enrollment.status,
            "attendance": attendance_summary,
            "billing": billing,
            "payments": payment_rows,
        })

    return {"group": group, "schedules": schedules, "members": members}


def _comparable_dt(value: datetime, timezone_name: str) -> datetime:
    from app.services import scheduling_service
    return scheduling_service.comparable_dt(value, timezone_name)

def _lesson_conflict_reason(
    db: Session,
    org_id: UUID,
    group: Group,
    location_id: UUID | None,
    starts_at: datetime,
    duration_minutes: int,
) -> str | None:
    from app.services import scheduling_service
    return scheduling_service.lesson_conflict_reason(
        db, org_id, group, location_id, starts_at, duration_minutes,
    )

def materialize_recurring_lesson_sessions(
    db: Session,
    org_id: UUID,
    weeks_back: int = 0,
    weeks_forward: int = 8,
) -> int:
    from app.services import scheduling_service
    return scheduling_service.materialize_recurring_lesson_sessions(
        db, org_id, weeks_back, weeks_forward,
    )

def create_lesson_session(db: Session, org_id: UUID, data, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> LessonSession:
    from app.services import scheduling_service
    return scheduling_service.create_lesson_session(db, org_id, data, user_id, role)

def list_lesson_sessions(db: Session, org_id: UUID, group_id: UUID | None = None, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[LessonSession]:
    from app.services import scheduling_service
    return scheduling_service.list_lesson_sessions(db, org_id, group_id, user_id, role)

def update_lesson_session(db: Session, org_id: UUID, session_id: UUID, data, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> LessonSession:
    from app.services import scheduling_service
    return scheduling_service.update_lesson_session(db, org_id, session_id, data, user_id, role)

# Compatibility forwarding for the extracted attendance domain.
def _attendance_service_call(name: str, *args, **kwargs):
    from app.services import attendance_service
    return getattr(attendance_service, name)(*args, **kwargs)

def _eligible_subscription_for_session(*args, **kwargs):
    return _attendance_service_call("_eligible_subscription_for_session", *args, **kwargs)

def _attendance_should_consume(*args, **kwargs):
    return _attendance_service_call("_attendance_should_consume", *args, **kwargs)

def _sync_makeup_credit(*args, **kwargs):
    return _attendance_service_call("_sync_makeup_credit", *args, **kwargs)

def _complete_oldest_makeup(*args, **kwargs):
    return _attendance_service_call("_complete_oldest_makeup", *args, **kwargs)

def _renew_after_last_lesson(*args, **kwargs):
    return _attendance_service_call("_renew_after_last_lesson", *args, **kwargs)

def _sync_attendance_usage(*args, **kwargs):
    return _attendance_service_call("_sync_attendance_usage", *args, **kwargs)

def mark_attendance_bulk(*args, **kwargs):
    return _attendance_service_call("mark_attendance_bulk", *args, **kwargs)

def list_attendance(*args, **kwargs):
    return _attendance_service_call("list_attendance", *args, **kwargs)

def student_attendance_history(*args, **kwargs):
    return _attendance_service_call("student_attendance_history", *args, **kwargs)

def _billing_service_call(name: str, *args, **kwargs):
    from app.services import billing_service
    return getattr(billing_service, name)(*args, **kwargs)

def _payment_transactions(*args, **kwargs):
    return _billing_service_call("_payment_transactions", *args, **kwargs)

def _materialize_legacy_settlement(*args, **kwargs):
    return _billing_service_call("_materialize_legacy_settlement", *args, **kwargs)

def payment_financials(*args, **kwargs):
    return _billing_service_call("payment_financials", *args, **kwargs)

def _sync_payment_state(*args, **kwargs):
    return _billing_service_call("_sync_payment_state", *args, **kwargs)

def _attach_payment_financials(*args, **kwargs):
    return _billing_service_call("_attach_payment_financials", *args, **kwargs)

def _subscription_end_date(*args, **kwargs):
    return _billing_service_call("_subscription_end_date", *args, **kwargs)

def _lesson_unit_price(*args, **kwargs):
    return _billing_service_call("_lesson_unit_price", *args, **kwargs)

def _first_planned_lesson_date(*args, **kwargs):
    return _billing_service_call("_first_planned_lesson_date", *args, **kwargs)

def create_subscription_plan(*args, **kwargs):
    return _billing_service_call("create_subscription_plan", *args, **kwargs)

def update_subscription_plan(*args, **kwargs):
    return _billing_service_call("update_subscription_plan", *args, **kwargs)

def list_subscription_plans(*args, **kwargs):
    return _billing_service_call("list_subscription_plans", *args, **kwargs)

def create_student_subscription(*args, **kwargs):
    return _billing_service_call("create_student_subscription", *args, **kwargs)

def subscription_usage_summary(*args, **kwargs):
    return _billing_service_call("subscription_usage_summary", *args, **kwargs)

def _attach_subscription_usage(*args, **kwargs):
    return _billing_service_call("_attach_subscription_usage", *args, **kwargs)

def list_student_subscriptions(*args, **kwargs):
    return _billing_service_call("list_student_subscriptions", *args, **kwargs)

def set_subscription_auto_renew(*args, **kwargs):
    return _billing_service_call("set_subscription_auto_renew", *args, **kwargs)

def pause_subscription(*args, **kwargs):
    return _billing_service_call("pause_subscription", *args, **kwargs)

def _finish_subscription_pause(*args, **kwargs):
    return _billing_service_call("_finish_subscription_pause", *args, **kwargs)

def resume_subscription(*args, **kwargs):
    return _billing_service_call("resume_subscription", *args, **kwargs)

def _resume_due_pauses(*args, **kwargs):
    return _billing_service_call("_resume_due_pauses", *args, **kwargs)

def run_billing_renewals(*args, **kwargs):
    return _billing_service_call("run_billing_renewals", *args, **kwargs)

def create_subscription_charge(*args, **kwargs):
    return _billing_service_call("create_subscription_charge", *args, **kwargs)

def change_subscription_plan_now(*args, **kwargs):
    return _billing_service_call("change_subscription_plan_now", *args, **kwargs)

def create_payment(*args, **kwargs):
    return _billing_service_call("create_payment", *args, **kwargs)

def list_payments(*args, **kwargs):
    return _billing_service_call("list_payments", *args, **kwargs)

def add_payment_receipt(*args, **kwargs):
    return _billing_service_call("add_payment_receipt", *args, **kwargs)

def mark_payment_paid(*args, **kwargs):
    return _billing_service_call("mark_payment_paid", *args, **kwargs)

def add_payment_adjustment(*args, **kwargs):
    return _billing_service_call("add_payment_adjustment", *args, **kwargs)

def refund_payment(*args, **kwargs):
    return _billing_service_call("refund_payment", *args, **kwargs)

def list_payment_transactions(*args, **kwargs):
    return _billing_service_call("list_payment_transactions", *args, **kwargs)

def payment_summary(*args, **kwargs):
    return _billing_service_call("payment_summary", *args, **kwargs)

def cancel_payment(*args, **kwargs):
    return _billing_service_call("cancel_payment", *args, **kwargs)

def _payment_reminder_stage(*args, **kwargs):
    return _billing_service_call("_payment_reminder_stage", *args, **kwargs)

def payment_reminder_queue(*args, **kwargs):
    return _billing_service_call("payment_reminder_queue", *args, **kwargs)

def mark_payment_reminder_sent(*args, **kwargs):
    return _billing_service_call("mark_payment_reminder_sent", *args, **kwargs)

def create_staff(db: Session, org_id: UUID, data) -> Staff:
    from app.services import staff_service
    return staff_service.create_staff(db, org_id, data)


def list_staff(db: Session, org_id: UUID, active_only: bool = True) -> list[Staff]:
    from app.services import staff_service
    return staff_service.list_staff(db, org_id, active_only)


def update_staff(db: Session, org_id: UUID, staff_id: UUID, data) -> Staff:
    from app.services import staff_service
    return staff_service.update_staff(db, org_id, staff_id, data)


def set_staff_locations(db: Session, org_id: UUID, staff_id: UUID, location_ids: list[UUID]) -> Staff:
    from app.services import staff_service
    return staff_service.set_staff_locations(db, org_id, staff_id, location_ids)


def assign_staff_to_group(db: Session, org_id: UUID, staff_id: UUID, group_id: UUID, is_primary: bool = False) -> GroupStaff:
    from app.services import staff_service
    return staff_service.assign_staff_to_group(db, org_id, staff_id, group_id, is_primary)


def staff_profile(db: Session, org_id: UUID, staff_id: UUID):
    from app.services import staff_service
    return staff_service.staff_profile(db, org_id, staff_id)


def create_membership(db: Session, org_id: UUID, data):
    from app.services import staff_service
    return staff_service.create_membership(db, org_id, data)

def update_location(db: Session, org_id: UUID, location_id: UUID, data) -> Location:
    from app.services import location_service
    return location_service.update_location(db, org_id, location_id, data)


def overview_report(db: Session, org_id: UUID) -> dict:
    from app.services import reporting_service
    return reporting_service.overview_report(db, org_id)

def _primary_contact_for_student(db: Session, org_id: UUID, student_id: UUID) -> Contact | None:
    return db.scalar(
        select(Contact)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student_id,
            Contact.organization_id == org_id,
        )
        .order_by(StudentContact.is_primary.desc(), Contact.created_at)
        .limit(1)
    )


def student_preferences(db: Session, org_id: UUID, student_id: UUID) -> dict:
    student = scoped_get(db, Student, org_id, student_id)
    location = scoped_get(db, Location, org_id, student.preferred_location_id) if student.preferred_location_id else None
    availability = list(db.scalars(
        select(StudentAvailability)
        .where(
            StudentAvailability.organization_id == org_id,
            StudentAvailability.student_id == student_id,
        )
        .order_by(StudentAvailability.weekday, StudentAvailability.start_time)
    ))
    return {
        "preferred_location_id": student.preferred_location_id,
        "preferred_location_name": location.name if location else None,
        "availability": [{
            "weekday": item.weekday,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "preference": item.preference,
            "note": item.note,
        } for item in availability],
    }


def replace_student_preferences(db: Session, org_id: UUID, student_id: UUID, data, actor_user_id: UUID | None = None) -> dict:
    student = scoped_get(db, Student, org_id, student_id)
    if data.preferred_location_id is not None:
        scoped_get(db, Location, org_id, data.preferred_location_id)

    seen: set[tuple[int, time, time]] = set()
    for slot in data.availability:
        key = (slot.weekday, slot.start_time, slot.end_time)
        if key in seen:
            raise HTTPException(status_code=422, detail="Duplicate availability slots are not allowed")
        seen.add(key)

    student.preferred_location_id = data.preferred_location_id
    db.execute(delete(StudentAvailability).where(
        StudentAvailability.organization_id == org_id,
        StudentAvailability.student_id == student_id,
    ))
    for slot in data.availability:
        db.add(StudentAvailability(
            organization_id=org_id,
            student_id=student_id,
            weekday=slot.weekday,
            start_time=slot.start_time,
            end_time=slot.end_time,
            preference=slot.preference,
            note=slot.note,
        ))

    record_audit(db, org_id, "student", student.id, "student.preferences_updated", {
        "preferred_location_id": str(data.preferred_location_id) if data.preferred_location_id else None,
        "availability_count": len(data.availability),
    }, actor_user_id=actor_user_id)
    db.commit()
    return student_preferences(db, org_id, student_id)


def preview_group_matches(db: Session, org_id: UUID, data) -> list[dict]:
    if data.location_id is not None:
        scoped_get(db, Location, org_id, data.location_id)
    results = []
    for student_id in data.student_ids:
        student = scoped_get(db, Student, org_id, student_id)
        windows = list(db.scalars(select(StudentAvailability).where(
            StudentAvailability.organization_id == org_id,
            StudentAvailability.student_id == student.id,
        )))
        match = evaluate_schedule_match(data.schedule_slots, windows, data.location_id, student.preferred_location_id)
        results.append({
            "student_id": student.id,
            "status": match.status,
            "summary": match.summary,
            "matching_slots": [vars(item) for item in match.matching_slots],
            "partial_slots": [vars(item) for item in match.partial_slots],
            "conflicting_slots": [vars(item) for item in match.conflicting_slots],
        })
    return results


def list_lead_overview(db: Session, org_id: UUID) -> list[dict]:
    students = list(db.scalars(
        select(Student)
        .where(Student.organization_id == org_id, Student.student_status == StudentStatus.PROSPECT)
        .order_by(Student.created_at.desc())
    ))
    result = []
    for student in students:
        contact = _primary_contact_for_student(db, org_id, student.id)
        trial = db.scalar(
            select(TrialLesson)
            .where(TrialLesson.organization_id == org_id, TrialLesson.student_id == student.id)
            .order_by(TrialLesson.starts_at.desc())
            .limit(1)
        )
        trial_location = scoped_get(db, Location, org_id, trial.location_id) if trial and trial.location_id else None
        preferences = student_preferences(db, org_id, student.id)
        result.append({
            "student_id": student.id,
            "created_at": student.created_at,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_phone": student.phone,
            "age": student.age_at_inquiry,
            "source": student.source,
            "comment": student.notes,
            "preferred_location_id": preferences["preferred_location_id"],
            "preferred_location_name": preferences["preferred_location_name"],
            "availability": preferences["availability"],
            "crm_status": student.crm_status,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "latest_trial_id": trial.id if trial else None,
            "latest_trial_at": trial.starts_at if trial else None,
            "latest_trial_status": trial.status if trial else None,
            "trial_location_id": trial.location_id if trial else None,
            "trial_location_name": trial_location.name if trial_location else None,
            "recommended_level": trial.recommended_level if trial else None,
            "teacher_notes": trial.teacher_notes if trial else None,
            "next_contact_at": student.next_contact_at,
            "deferred_until": student.deferred_until,
            "deferred_reason": student.deferred_reason,
            "deferred_note": student.deferred_note,
            "close_reason": student.lead_close_reason,
            "close_note": student.lead_close_note,
        })
    return result


def list_student_overview(db: Session, org_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[dict]:
    allowed_groups = None if role == StaffRole.ACCOUNTANT else assigned_group_ids_for_user(db, org_id, user_id, role)
    students = list(db.scalars(
        select(Student)
        .where(Student.organization_id == org_id, Student.student_status != StudentStatus.PROSPECT)
        .order_by(Student.first_name, Student.last_name)
    ))
    result = []
    for student in students:
        contact = _primary_contact_for_student(db, org_id, student.id)
        row = db.execute(
            select(Enrollment, Group)
            .join(Group, Group.id == Enrollment.group_id)
            .where(
                Enrollment.organization_id == org_id,
                Enrollment.student_id == student.id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
                Group.organization_id == org_id,
            )
            .limit(1)
        ).first()
        enrollment, group = row if row else (None, None)
        if allowed_groups is not None and (group is None or group.id not in allowed_groups):
            continue
        result.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_phone": student.phone,
            "age": student.age_at_inquiry,
            "source": student.source,
            "student_status": student.student_status,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "group_id": group.id if group else None,
            "group_name": group.name if group else None,
        })
    return result


def list_group_overview(db: Session, org_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[dict]:
    allowed_groups = assigned_group_ids_for_user(db, org_id, user_id, role)
    groups = list(db.scalars(
        select(Group)
        .where(Group.organization_id == org_id, Group.is_active.is_(True))
        .order_by(Group.name)
    ))
    if allowed_groups is not None:
        groups = [group for group in groups if group.id in allowed_groups]
    result = []
    for group in groups:
        enrolled_count = db.scalar(select(func.count(Enrollment.id)).where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id == group.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )) or 0
        location = scoped_get(db, Location, org_id, group.location_id) if group.location_id else None
        primary_assignment = db.execute(
            select(GroupStaff, Staff)
            .join(Staff, Staff.id == GroupStaff.staff_id)
            .where(
                GroupStaff.organization_id == org_id,
                GroupStaff.group_id == group.id,
                Staff.organization_id == org_id,
                Staff.is_active.is_(True),
            )
            .order_by(GroupStaff.is_primary.desc(), Staff.full_name)
            .limit(1)
        ).first()
        primary_staff = primary_assignment[1] if primary_assignment else None
        result.append({
            "group_id": group.id,
            "name": group.name,
            "location_id": group.location_id,
            "location_name": location.name if location else None,
            "capacity": group.capacity,
            "enrolled_count": int(enrolled_count),
            "min_age": group.min_age,
            "max_age": group.max_age,
            "primary_teacher_id": primary_staff.id if primary_staff else None,
            "primary_teacher_name": primary_staff.full_name if primary_staff else None,
        })
    return result


def assigned_group_ids_for_user(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole) -> set[UUID] | None:
    if role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.TEACHER}:
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
    group = scoped_get(db, Group, org_id, group_id)
    allowed = assigned_group_ids_for_user(db, org_id, user_id, role)
    if allowed is not None and group_id not in allowed:
        raise HTTPException(status_code=403, detail="No access to this group")
    return group


def remove_staff_from_group(db: Session, org_id: UUID, staff_id: UUID, group_id: UUID) -> None:
    scoped_get(db, Staff, org_id, staff_id)
    scoped_get(db, Group, org_id, group_id)
    item = db.scalar(select(GroupStaff).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff_id,
        GroupStaff.group_id == group_id,
    ))
    if item is None:
        return
    db.delete(item)
    db.commit()
