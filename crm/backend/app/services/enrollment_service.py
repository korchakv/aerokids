from __future__ import annotations

from datetime import date, time
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import (
    CrmStatus,
    Enrollment,
    EnrollmentStatus,
    Group,
    GroupSchedule,
    Location,
    Student,
    StudentAvailability,
    StudentStatus,
    TrialLesson,
)
from app.schemas import EnrollmentCreate
from app.services import crm
from app.services.schedule_matching import enrollment_schedule_note, evaluate_schedule_match

# Lazy-loaded by the legacy crm facade after crm.py has initialized.
scoped_get = crm.scoped_get
record_audit = crm.record_audit
require_organization = crm.require_organization
student_detail = crm.student_detail

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

