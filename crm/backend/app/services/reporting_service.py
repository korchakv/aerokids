from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    AttendanceStatus,
    CrmStatus,
    Enrollment,
    EnrollmentStatus,
    Group,
    Location,
    Staff,
    Student,
    StudentStatus,
)
from app.services import crm


def overview_report(db: Session, org_id: UUID) -> dict:
    crm.require_organization(db, org_id)

    funnel_rows = db.execute(
        select(Student.crm_status, func.count(Student.id))
        .where(Student.organization_id == org_id)
        .group_by(Student.crm_status)
    ).all()
    funnel_map = {status: count for status, count in funnel_rows}
    funnel = [
        {"status": status, "count": int(funnel_map.get(status, 0))}
        for status in CrmStatus
    ]

    active_students = db.scalar(select(func.count(Student.id)).where(
        Student.organization_id == org_id,
        Student.student_status == StudentStatus.ACTIVE,
    )) or 0

    active_groups = db.scalar(select(func.count(Group.id)).where(
        Group.organization_id == org_id,
        Group.is_active.is_(True),
    )) or 0

    enrolled_students = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.organization_id == org_id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    )) or 0

    capacities = list(db.scalars(select(Group.capacity).where(
        Group.organization_id == org_id,
        Group.is_active.is_(True),
    )))
    group_capacity = sum(capacity or 0 for capacity in capacities)

    active_staff = db.scalar(select(func.count(Staff.id)).where(
        Staff.organization_id == org_id,
        Staff.is_active.is_(True),
    )) or 0

    active_locations = db.scalar(select(func.count(Location.id)).where(
        Location.organization_id == org_id,
        Location.is_active.is_(True),
    )) or 0

    attendance_rows = db.execute(
        select(Attendance.status, func.count(Attendance.id))
        .where(Attendance.organization_id == org_id)
        .group_by(Attendance.status)
    ).all()
    attendance_map = {status: int(count) for status, count in attendance_rows}
    present = attendance_map.get(AttendanceStatus.PRESENT, 0)
    absent = attendance_map.get(AttendanceStatus.ABSENT, 0)
    late = attendance_map.get(AttendanceStatus.LATE, 0)
    excused = attendance_map.get(AttendanceStatus.EXCUSED, 0)
    total = present + absent + late + excused
    rate = round(((present + late) / total * 100), 1) if total else 0.0

    return {
        "funnel": funnel,
        "active_students": int(active_students),
        "active_groups": int(active_groups),
        "enrolled_students": int(enrolled_students),
        "group_capacity": int(group_capacity),
        "active_staff": int(active_staff),
        "active_locations": int(active_locations),
        "attendance": {
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "total": total,
            "attendance_rate": rate,
        },
        "payments": crm.payment_summary(db, org_id),
    }
