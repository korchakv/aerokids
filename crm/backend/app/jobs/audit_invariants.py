from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import timedelta

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.core import (
    Attendance,
    Contact,
    Enrollment,
    EnrollmentStatus,
    Group,
    GroupSchedule,
    GroupStaff,
    LessonSession,
    LessonStatus,
    Location,
    Organization,
    OrganizationMembership,
    Payment,
    PaymentStatus,
    Staff,
    Student,
    StudentContact,
    StudentStatus,
    StudentSubscription,
    SubscriptionPlan,
    TrialLesson,
    TrialStatus,
)
from app.models.hardening import (
    EnrollmentHistory,
    GroupRoomAssignment,
    IndividualAttendance,
    IndividualLessonSession,
    LessonResourceAssignment,
    Room,
    StaffCapability,
    TrialResourceAssignment,
)
from app.models.hardening_extensions import SubscriptionRuleSnapshot
from app.services import crm


@dataclass
class Finding:
    severity: str
    code: str
    count: int
    detail: str


def _count(db, stmt) -> int:
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _count_resource_conflicts(db, org: Organization) -> int:
    group_rooms = {
        row.group_id: row.room_id
        for row in db.scalars(select(GroupRoomAssignment).where(
            GroupRoomAssignment.organization_id == org.id,
        ))
    }
    primary_staff = {
        row.group_id: row.staff_id
        for row in db.scalars(select(GroupStaff).where(
            GroupStaff.organization_id == org.id,
            GroupStaff.is_primary.is_(True),
        ))
    }
    lesson_resources = {
        row.session_id: row
        for row in db.scalars(select(LessonResourceAssignment).where(
            LessonResourceAssignment.organization_id == org.id,
        ))
    }
    trial_resources = {
        row.trial_id: row
        for row in db.scalars(select(TrialResourceAssignment).where(
            TrialResourceAssignment.organization_id == org.id,
        ))
    }

    events: list[dict] = []
    for row in db.scalars(select(LessonSession).where(
        LessonSession.organization_id == org.id,
        LessonSession.status != LessonStatus.CANCELLED,
    )):
        resources = lesson_resources.get(row.id)
        events.append({
            "kind": "group",
            "start": crm._comparable_dt(row.starts_at, org.timezone),
            "duration": row.duration_minutes,
            "group_id": row.group_id,
            "location_id": row.location_id,
            "room_id": resources.room_id if resources else group_rooms.get(row.group_id),
            "staff_id": resources.staff_id if resources else primary_staff.get(row.group_id),
        })

    for row in db.scalars(select(TrialLesson).where(
        TrialLesson.organization_id == org.id,
        TrialLesson.status == TrialStatus.SCHEDULED,
    )):
        resources = trial_resources.get(row.id)
        events.append({
            "kind": "trial",
            "start": crm._comparable_dt(row.starts_at, org.timezone),
            "duration": resources.duration_minutes if resources else 60,
            "group_id": None,
            "location_id": row.location_id,
            "room_id": resources.room_id if resources else None,
            "staff_id": resources.staff_id if resources else None,
        })

    for row in db.scalars(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org.id,
        IndividualLessonSession.status != "cancelled",
    )):
        events.append({
            "kind": "individual",
            "start": crm._comparable_dt(row.starts_at, org.timezone),
            "duration": row.duration_minutes,
            "group_id": None,
            "location_id": row.location_id,
            "room_id": row.room_id,
            "staff_id": row.staff_id,
        })

    conflicts = 0
    for index, left in enumerate(events):
        left_end = left["start"] + timedelta(minutes=left["duration"])
        for right in events[index + 1:]:
            right_end = right["start"] + timedelta(minutes=right["duration"])
            if not (left["start"] < right_end and right["start"] < left_end):
                continue
            same_group = bool(
                left["group_id"] is not None
                and right["group_id"] is not None
                and left["group_id"] == right["group_id"]
            )
            same_staff = bool(
                left["staff_id"] is not None
                and right["staff_id"] is not None
                and left["staff_id"] == right["staff_id"]
            )
            same_room = bool(
                left["room_id"] is not None
                and right["room_id"] is not None
                and left["room_id"] == right["room_id"]
            )
            same_location_without_room = bool(
                left["location_id"] is not None
                and right["location_id"] is not None
                and left["location_id"] == right["location_id"]
                and (left["room_id"] is None or right["room_id"] is None)
            )
            if same_group or same_staff or same_room or same_location_without_room:
                conflicts += 1
    return conflicts


def audit_organization(db, org: Organization) -> list[Finding]:
    findings: list[Finding] = []

    cross_enrollment = _count(db, select(Enrollment.id).join(
        Student, Student.id == Enrollment.student_id
    ).join(
        Group, Group.id == Enrollment.group_id
    ).where(
        Enrollment.organization_id == org.id,
        ((Student.organization_id != org.id) | (Group.organization_id != org.id)),
    ))
    if cross_enrollment:
        findings.append(Finding("critical", "cross_tenant_enrollment", cross_enrollment, "Enrollment points outside its organization"))

    cross_schedule = _count(db, select(GroupSchedule.id).join(
        Group, Group.id == GroupSchedule.group_id
    ).where(GroupSchedule.organization_id == org.id, Group.organization_id != org.id))
    if cross_schedule:
        findings.append(Finding("critical", "cross_tenant_group_schedule", cross_schedule, "GroupSchedule points outside its organization"))

    cross_lesson = _count(db, select(LessonSession.id).join(
        Group, Group.id == LessonSession.group_id
    ).where(LessonSession.organization_id == org.id, Group.organization_id != org.id))
    if cross_lesson:
        findings.append(Finding("critical", "cross_tenant_lesson", cross_lesson, "LessonSession points outside its organization"))

    cross_attendance = _count(db, select(Attendance.id).join(
        LessonSession, LessonSession.id == Attendance.session_id
    ).join(
        Student, Student.id == Attendance.student_id
    ).where(
        Attendance.organization_id == org.id,
        ((LessonSession.organization_id != org.id) | (Student.organization_id != org.id)),
    ))
    if cross_attendance:
        findings.append(Finding("critical", "cross_tenant_attendance", cross_attendance, "Attendance points outside its organization"))

    cross_subscription = _count(db, select(StudentSubscription.id).join(
        Student, Student.id == StudentSubscription.student_id
    ).join(
        SubscriptionPlan, SubscriptionPlan.id == StudentSubscription.plan_id
    ).outerjoin(
        Group, Group.id == StudentSubscription.group_id
    ).where(
        StudentSubscription.organization_id == org.id,
        (
            (Student.organization_id != org.id)
            | (SubscriptionPlan.organization_id != org.id)
            | ((StudentSubscription.group_id.is_not(None)) & (Group.organization_id != org.id))
        ),
    ))
    if cross_subscription:
        findings.append(Finding("critical", "cross_tenant_subscription", cross_subscription, "StudentSubscription has a foreign tenant relation"))

    cross_payment = _count(db, select(Payment.id).join(
        Student, Student.id == Payment.student_id
    ).outerjoin(
        StudentSubscription, StudentSubscription.id == Payment.subscription_id
    ).where(
        Payment.organization_id == org.id,
        (
            (Student.organization_id != org.id)
            | ((Payment.subscription_id.is_not(None)) & (StudentSubscription.organization_id != org.id))
        ),
    ))
    if cross_payment:
        findings.append(Finding("critical", "cross_tenant_payment", cross_payment, "Payment has a foreign tenant relation"))

    cross_group_staff = _count(db, select(GroupStaff.id).join(
        Group, Group.id == GroupStaff.group_id
    ).join(
        Staff, Staff.id == GroupStaff.staff_id
    ).where(
        GroupStaff.organization_id == org.id,
        ((Group.organization_id != org.id) | (Staff.organization_id != org.id)),
    ))
    if cross_group_staff:
        findings.append(Finding("critical", "cross_tenant_group_staff", cross_group_staff, "GroupStaff has a foreign tenant relation"))

    cross_room = _count(db, select(Room.id).join(
        Location, Location.id == Room.location_id
    ).where(Room.organization_id == org.id, Location.organization_id != org.id))
    if cross_room:
        findings.append(Finding("critical", "cross_tenant_room", cross_room, "Room points to a foreign location"))

    cross_group_room = _count(db, select(GroupRoomAssignment.id).join(
        Group, Group.id == GroupRoomAssignment.group_id
    ).join(
        Room, Room.id == GroupRoomAssignment.room_id
    ).where(
        GroupRoomAssignment.organization_id == org.id,
        ((Group.organization_id != org.id) | (Room.organization_id != org.id)),
    ))
    if cross_group_room:
        findings.append(Finding("critical", "cross_tenant_group_room", cross_group_room, "Group room assignment crosses organizations"))

    cross_lesson_resource = _count(db, select(LessonResourceAssignment.id).join(
        LessonSession, LessonSession.id == LessonResourceAssignment.session_id
    ).outerjoin(
        Staff, Staff.id == LessonResourceAssignment.staff_id
    ).outerjoin(
        Room, Room.id == LessonResourceAssignment.room_id
    ).where(
        LessonResourceAssignment.organization_id == org.id,
        (
            (LessonSession.organization_id != org.id)
            | ((LessonResourceAssignment.staff_id.is_not(None)) & (Staff.organization_id != org.id))
            | ((LessonResourceAssignment.room_id.is_not(None)) & (Room.organization_id != org.id))
        ),
    ))
    if cross_lesson_resource:
        findings.append(Finding("critical", "cross_tenant_lesson_resource", cross_lesson_resource, "Lesson resource assignment crosses organizations"))

    cross_trial_resource = _count(db, select(TrialResourceAssignment.id).join(
        crm.TrialLesson, crm.TrialLesson.id == TrialResourceAssignment.trial_id
    ).outerjoin(
        Staff, Staff.id == TrialResourceAssignment.staff_id
    ).outerjoin(
        Room, Room.id == TrialResourceAssignment.room_id
    ).where(
        TrialResourceAssignment.organization_id == org.id,
        (
            (crm.TrialLesson.organization_id != org.id)
            | ((TrialResourceAssignment.staff_id.is_not(None)) & (Staff.organization_id != org.id))
            | ((TrialResourceAssignment.room_id.is_not(None)) & (Room.organization_id != org.id))
        ),
    ))
    if cross_trial_resource:
        findings.append(Finding("critical", "cross_tenant_trial_resource", cross_trial_resource, "Trial resource assignment crosses organizations"))

    cross_enrollment_history = _count(db, select(EnrollmentHistory.id).join(
        Student, Student.id == EnrollmentHistory.student_id
    ).join(
        Group, Group.id == EnrollmentHistory.group_id
    ).where(
        EnrollmentHistory.organization_id == org.id,
        ((Student.organization_id != org.id) | (Group.organization_id != org.id)),
    ))
    if cross_enrollment_history:
        findings.append(Finding("critical", "cross_tenant_enrollment_history", cross_enrollment_history, "Enrollment history crosses organizations"))

    cross_individual_lesson = _count(db, select(IndividualLessonSession.id).join(
        Student, Student.id == IndividualLessonSession.student_id
    ).outerjoin(
        Location, Location.id == IndividualLessonSession.location_id
    ).outerjoin(
        Staff, Staff.id == IndividualLessonSession.staff_id
    ).outerjoin(
        Room, Room.id == IndividualLessonSession.room_id
    ).where(
        IndividualLessonSession.organization_id == org.id,
        (
            (Student.organization_id != org.id)
            | ((IndividualLessonSession.location_id.is_not(None)) & (Location.organization_id != org.id))
            | ((IndividualLessonSession.staff_id.is_not(None)) & (Staff.organization_id != org.id))
            | ((IndividualLessonSession.room_id.is_not(None)) & (Room.organization_id != org.id))
        ),
    ))
    if cross_individual_lesson:
        findings.append(Finding("critical", "cross_tenant_individual_lesson", cross_individual_lesson, "Individual lesson crosses organizations"))

    cross_individual_attendance = _count(db, select(IndividualAttendance.id).join(
        IndividualLessonSession, IndividualLessonSession.id == IndividualAttendance.session_id
    ).join(
        Student, Student.id == IndividualAttendance.student_id
    ).where(
        IndividualAttendance.organization_id == org.id,
        ((IndividualLessonSession.organization_id != org.id) | (Student.organization_id != org.id)),
    ))
    if cross_individual_attendance:
        findings.append(Finding("critical", "cross_tenant_individual_attendance", cross_individual_attendance, "Individual attendance crosses organizations"))

    cross_staff_capability = _count(db, select(StaffCapability.id).join(
        Staff, Staff.id == StaffCapability.staff_id
    ).where(StaffCapability.organization_id == org.id, Staff.organization_id != org.id))
    if cross_staff_capability:
        findings.append(Finding("critical", "cross_tenant_staff_capability", cross_staff_capability, "Staff capability points outside its organization"))

    cross_rule_snapshot = _count(db, select(SubscriptionRuleSnapshot.id).join(
        StudentSubscription, StudentSubscription.id == SubscriptionRuleSnapshot.subscription_id
    ).where(
        SubscriptionRuleSnapshot.organization_id == org.id,
        StudentSubscription.organization_id != org.id,
    ))
    if cross_rule_snapshot:
        findings.append(Finding("critical", "cross_tenant_subscription_rule_snapshot", cross_rule_snapshot, "Subscription rule snapshot crosses organizations"))

    capacity_rows = db.execute(
        select(Group.id, Group.name, Group.capacity, func.count(Enrollment.id))
        .outerjoin(
            Enrollment,
            (Enrollment.group_id == Group.id)
            & (Enrollment.organization_id == org.id)
            & (Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED])),
        )
        .where(Group.organization_id == org.id, Group.capacity.is_not(None))
        .group_by(Group.id, Group.name, Group.capacity)
    ).all()
    over_capacity = [row for row in capacity_rows if int(row[3] or 0) > int(row[2])]
    if over_capacity:
        findings.append(Finding(
            "critical",
            "group_over_capacity",
            len(over_capacity),
            "; ".join(f"{name}: {count}/{capacity}" for _, name, capacity, count in over_capacity[:10]),
        ))

    duplicate_primary_rows = db.execute(
        select(StudentContact.student_id, func.count(StudentContact.id))
        .where(StudentContact.organization_id == org.id, StudentContact.is_primary.is_(True))
        .group_by(StudentContact.student_id)
        .having(func.count(StudentContact.id) > 1)
    ).all()
    if duplicate_primary_rows:
        findings.append(Finding(
            "warning",
            "multiple_primary_contacts",
            len(duplicate_primary_rows),
            "One student should have at most one primary responsible contact",
        ))

    inactive_staff_access = _count(db, select(Staff.id).join(
        OrganizationMembership,
        (OrganizationMembership.user_id == Staff.user_id)
        & (OrganizationMembership.organization_id == Staff.organization_id),
    ).where(
        Staff.organization_id == org.id,
        Staff.user_id.is_not(None),
        Staff.is_active.is_(False),
        OrganizationMembership.is_active.is_(True),
    ))
    if inactive_staff_access:
        findings.append(Finding(
            "critical",
            "inactive_staff_active_membership",
            inactive_staff_access,
            "Inactive staff member still has active organization access",
        ))

    role_drift = _count(db, select(Staff.id).join(
        OrganizationMembership,
        (OrganizationMembership.user_id == Staff.user_id)
        & (OrganizationMembership.organization_id == Staff.organization_id),
    ).where(
        Staff.organization_id == org.id,
        Staff.user_id.is_not(None),
        Staff.role != OrganizationMembership.role,
    ))
    if role_drift:
        findings.append(Finding("critical", "staff_membership_role_drift", role_drift, "Staff role and membership role differ"))

    active_enrollment_inactive_student = _count(db, select(Enrollment.id).join(
        Student, Student.id == Enrollment.student_id
    ).where(
        Enrollment.organization_id == org.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
        Student.student_status != StudentStatus.ACTIVE,
    ))
    if active_enrollment_inactive_student:
        findings.append(Finding(
            "warning",
            "active_enrollment_inactive_student",
            active_enrollment_inactive_student,
            "Active enrollment belongs to non-active student",
        ))

    orphan_contacts = _count(db, select(Contact.id).outerjoin(
        StudentContact,
        (StudentContact.contact_id == Contact.id) & (StudentContact.organization_id == org.id),
    ).where(Contact.organization_id == org.id, StudentContact.id.is_(None)))
    if orphan_contacts:
        findings.append(Finding("info", "orphan_contacts", orphan_contacts, "Contacts have no linked student"))

    duplicate_active_renewals = db.execute(
        select(StudentSubscription.renewal_of_id, func.count(StudentSubscription.id))
        .where(
            StudentSubscription.organization_id == org.id,
            StudentSubscription.renewal_of_id.is_not(None),
            StudentSubscription.status != "CANCELLED",
        )
        .group_by(StudentSubscription.renewal_of_id)
        .having(func.count(StudentSubscription.id) > 1)
    ).all()
    if duplicate_active_renewals:
        findings.append(Finding(
            "critical",
            "duplicate_active_renewal",
            len(duplicate_active_renewals),
            "A subscription has multiple non-cancelled renewal children",
        ))

    finance_mismatches = 0
    for payment in db.scalars(select(Payment).where(Payment.organization_id == org.id)):
        financials = crm.payment_financials(db, org.id, payment)
        if payment.status == PaymentStatus.PAID and financials["balance_minor"] > 0:
            finance_mismatches += 1
        if payment.status == PaymentStatus.PENDING and financials["balance_minor"] == 0:
            finance_mismatches += 1
        if financials["adjusted_amount_minor"] < 0 or financials["net_paid_minor"] < 0:
            finance_mismatches += 1
    if finance_mismatches:
        findings.append(Finding(
            "critical",
            "payment_ledger_state_mismatch",
            finance_mismatches,
            "Stored payment status disagrees with immutable ledger balance",
        ))

    resource_conflicts = _count_resource_conflicts(db, org)
    if resource_conflicts:
        findings.append(Finding(
            "warning",
            "scheduled_resource_conflicts",
            resource_conflicts,
            "Scheduled lessons/trials share a group, teacher, room or unpartitioned location",
        ))

    return findings


def run_audit() -> dict:
    db = SessionLocal()
    try:
        organizations = list(db.scalars(select(Organization).order_by(Organization.name)))
        reports = []
        critical = 0
        warning = 0
        for org in organizations:
            findings = audit_organization(db, org)
            critical += sum(item.severity == "critical" for item in findings)
            warning += sum(item.severity == "warning" for item in findings)
            reports.append({
                "organization_id": str(org.id),
                "organization_name": org.name,
                "findings": [asdict(item) for item in findings],
            })
        return {
            "organizations": reports,
            "summary": {
                "organization_count": len(organizations),
                "critical_finding_types": critical,
                "warning_finding_types": warning,
                "ok": critical == 0,
            },
        }
    finally:
        db.close()


if __name__ == "__main__":
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(0 if report["summary"]["ok"] else 2)
