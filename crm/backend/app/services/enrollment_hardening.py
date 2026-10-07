from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.core import CrmStatus, Enrollment, EnrollmentStatus, Group, Student, StudentStatus
from app.models.hardening import EnrollmentHistory
from app.services import crm, hardening


def _lock_group_with_capacity(db: Session, org_id: UUID, group_id: UUID, student_id: UUID | None = None) -> Group:
    group = db.scalar(select(Group).where(
        Group.organization_id == org_id,
        Group.id == group_id,
        Group.is_active.is_(True),
    ).with_for_update())
    if group is None:
        raise HTTPException(status_code=404, detail="Активну групу не знайдено")
    if group.capacity is None:
        return group
    if student_id is not None:
        existing_seat = db.scalar(select(Enrollment.id).where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student_id,
            Enrollment.group_id == group.id,
            Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
        ))
        if existing_seat is not None:
            return group
    occupied = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    )) or 0
    if occupied >= group.capacity:
        raise HTTPException(status_code=409, detail="У групі немає вільних місць; учні на паузі також зберігають місце")
    return group


def _archive_episode(db: Session, org_id: UUID, enrollment: Enrollment) -> None:
    db.add(EnrollmentHistory(
        organization_id=org_id,
        enrollment_id=enrollment.id,
        student_id=enrollment.student_id,
        group_id=enrollment.group_id,
        started_at=enrollment.started_at,
        ended_at=enrollment.ended_at,
        status=enrollment.status.value,
    ))


def enroll(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    group_id: UUID,
    started_at: date | None,
    actor_user_id: UUID | None,
) -> Enrollment:
    student = db.scalar(select(Student).where(
        Student.organization_id == org_id,
        Student.id == student_id,
    ).with_for_update())
    if student is None:
        raise HTTPException(status_code=404, detail="Учня не знайдено")
    group = _lock_group_with_capacity(db, org_id, group_id, student.id)
    current = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.group_id == group.id,
    ).with_for_update())
    if current is not None and current.status in {EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED}:
        return current

    start = started_at or hardening.organization_today(db, org_id)
    match, note = hardening._schedule_match_for(db, org_id, student, group)
    if current is None:
        current = Enrollment(
            organization_id=org_id,
            student_id=student.id,
            group_id=group.id,
        )
        db.add(current)
    else:
        _archive_episode(db, org_id, current)
    current.status = EnrollmentStatus.ACTIVE
    current.started_at = start
    current.ended_at = None
    current.schedule_match = match
    current.schedule_note = note
    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    crm.record_audit(db, org_id, "student", student.id, "student.enrolled_capacity_safe", {
        "group_id": str(group.id),
        "started_at": start.isoformat(),
        "schedule_match": match,
    }, actor_user_id)
    db.commit()
    db.refresh(current)
    return current


def transfer(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    to_group_id: UUID,
    started_at: date | None,
    actor_user_id: UUID | None,
) -> Enrollment:
    student = db.scalar(select(Student).where(
        Student.organization_id == org_id,
        Student.id == student_id,
    ).with_for_update())
    if student is None:
        raise HTTPException(status_code=404, detail="Учня не знайдено")
    target = _lock_group_with_capacity(db, org_id, to_group_id, student.id)
    start = started_at or hardening.organization_today(db, org_id)
    active_rows = list(db.scalars(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    ).with_for_update()))
    for row in active_rows:
        if row.group_id == target.id:
            if row.status == EnrollmentStatus.PAUSED:
                row.status = EnrollmentStatus.ACTIVE
                student.student_status = StudentStatus.ACTIVE
                db.commit()
                db.refresh(row)
            return row
        row.status = EnrollmentStatus.FINISHED
        # Enrollment intervals are date-based and inclusive. Ending on the
        # same date the target enrollment starts would put the student in
        # both historical rosters for that day.
        row.ended_at = start - timedelta(days=1)

    target_row = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.group_id == target.id,
    ).with_for_update())
    match, note = hardening._schedule_match_for(db, org_id, student, target)
    if target_row is None:
        target_row = Enrollment(
            organization_id=org_id,
            student_id=student.id,
            group_id=target.id,
        )
        db.add(target_row)
    else:
        _archive_episode(db, org_id, target_row)
    target_row.status = EnrollmentStatus.ACTIVE
    target_row.started_at = start
    target_row.ended_at = None
    target_row.schedule_match = match
    target_row.schedule_note = note
    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    crm.record_audit(db, org_id, "student", student.id, "student.transferred_capacity_safe", {
        "to_group_id": str(target.id),
        "started_at": start.isoformat(),
    }, actor_user_id)
    db.commit()
    db.refresh(target_row)
    return target_row
