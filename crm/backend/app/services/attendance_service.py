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
    AuditEvent,
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
    PaymentMethod,
    PaymentReminder,
    PaymentStatus,
    PaymentTransaction,
    PublicIntakeThrottle,
    Staff,
    StaffLocation,
    StaffRole,
    Student,
    StudentAvailability,
    StudentContact,
    StudentStatus,
    StudentSubscription,
    SubscriptionPause,
    SubscriptionPlan,
    SubscriptionStatus,
    SubscriptionUsage,
    TrialLesson,
    TrialStatus,
    User,
)
from app.services import crm

scoped_get = crm.scoped_get
require_organization = crm.require_organization
_comparable_dt = crm._comparable_dt
subscription_usage_summary = crm.subscription_usage_summary
_subscription_end_date = crm._subscription_end_date
_lesson_unit_price = crm._lesson_unit_price
record_audit = crm.record_audit
ensure_group_access = crm.ensure_group_access
assigned_group_ids_for_user = crm.assigned_group_ids_for_user

def _eligible_subscription_for_session(db: Session, org_id: UUID, student_id: UUID, session: LessonSession) -> tuple[StudentSubscription, SubscriptionPlan] | None:
    organization = require_organization(db, org_id)
    lesson_date = _comparable_dt(session.starts_at, organization.timezone).date()
    rows = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student_id,
        StudentSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED]),
    ).order_by(StudentSubscription.starts_on, StudentSubscription.created_at)))
    for subscription in rows:
        if subscription.group_id is not None and subscription.group_id != session.group_id:
            continue
        if lesson_date < subscription.starts_on:
            continue
        plan = scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
        summary = subscription_usage_summary(db, org_id, subscription)
        if subscription.ends_on is not None and plan.end_rule in {"date", "whichever_first"} and lesson_date > subscription.ends_on:
            continue
        included = subscription.lessons_included
        if included is None and subscription.period_days is None:
            included = plan.lessons_included
        if included is not None and summary["remaining_lessons"] == 0:
            continue
        return subscription, plan
    return None


def _attendance_should_consume(plan: SubscriptionPlan, status: AttendanceStatus, explicit: bool | None) -> bool:
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


def _sync_makeup_credit(db: Session, org_id: UUID, session: LessonSession, student_id: UUID, plan: SubscriptionPlan | None, status: AttendanceStatus) -> None:
    existing = db.scalar(select(MakeupCredit).where(
        MakeupCredit.organization_id == org_id,
        MakeupCredit.original_session_id == session.id,
        MakeupCredit.student_id == student_id,
    ))
    if status == AttendanceStatus.EXCUSED and plan is not None and plan.excused_rule == "makeup":
        expires_on = None
        if plan.makeup_expiry_days:
            organization = require_organization(db, org_id)
            expires_on = _comparable_dt(session.starts_at, organization.timezone).date() + timedelta(days=plan.makeup_expiry_days)
        if existing is None:
            db.add(MakeupCredit(organization_id=org_id, student_id=student_id, original_session_id=session.id, status="pending", expires_on=expires_on))
        elif existing.status == "cancelled":
            existing.status = "pending"
            existing.expires_on = expires_on
    elif existing is not None and existing.status == "pending":
        existing.status = "cancelled"


def _complete_oldest_makeup(db: Session, org_id: UUID, student_id: UUID, target_session_id: UUID) -> bool:
    today = date.today()
    credits = list(db.scalars(select(MakeupCredit).where(
        MakeupCredit.organization_id == org_id,
        MakeupCredit.student_id == student_id,
        MakeupCredit.status == "pending",
        MakeupCredit.original_session_id != target_session_id,
    ).order_by(MakeupCredit.created_at)))
    credit = next((item for item in credits if item.expires_on is None or item.expires_on >= today), None)
    if credit is None:
        return False
    credit.status = "completed"
    credit.target_session_id = target_session_id
    credit.completed_at = datetime.now(timezone.utc)
    return True


def _renew_after_last_lesson(db: Session, org_id: UUID, subscription: StudentSubscription, plan: SubscriptionPlan, session: LessonSession, actor_user_id: UUID | None) -> None:
    included = subscription.lessons_included
    if included is None and subscription.period_days is None:
        included = plan.lessons_included
    if not subscription.auto_renew or plan.renewal_trigger != "last_lesson" or included is None:
        return
    if subscription_usage_summary(db, org_id, subscription)["remaining_lessons"] != 0:
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
    organization = require_organization(db, org_id)
    after_date = _comparable_dt(session.starts_at, organization.timezone).date() + timedelta(days=1)
    next_start = _first_planned_lesson_date(db, org_id, subscription.group_id, after_date)
    available_credit = max(0, subscription.credit_minor)
    applied_credit = min(available_credit, plan.price_minor)
    carry_credit = max(0, available_credit - applied_credit)
    amount_due = max(0, plan.price_minor - applied_credit)
    next_subscription = StudentSubscription(
        organization_id=org_id, student_id=subscription.student_id, plan_id=plan.id, group_id=subscription.group_id,
        status=SubscriptionStatus.ACTIVE, starts_on=next_start, ends_on=_subscription_end_date(next_start, plan.period_days),
        price_minor=plan.price_minor, period_days=plan.period_days, lessons_included=plan.lessons_included,
        lesson_unit_price_minor=_lesson_unit_price(plan.price_minor, plan.lessons_included),
        credit_minor=carry_credit, discount_minor=0, discount_label=None, auto_renew=True, renewal_of_id=subscription.id,
    )
    db.add(next_subscription)
    db.flush()
    payment = Payment(
        organization_id=org_id, student_id=subscription.student_id, subscription_id=next_subscription.id,
        amount_minor=amount_due, currency=organization.currency, due_date=next_start,
        note=f"{plan.name} · продовження після останнього заняття",
        status=PaymentStatus.PAID if amount_due == 0 else PaymentStatus.PENDING,
        paid_at=datetime.now(timezone.utc) if amount_due == 0 else None,
    )
    db.add(payment)
    subscription.credit_minor = 0
    subscription.status = SubscriptionStatus.EXPIRED
    record_audit(db, org_id, "student", subscription.student_id, "subscription.renewed_after_last_lesson", {
        "previous_subscription_id": str(subscription.id), "subscription_id": str(next_subscription.id),
        "payment_id": str(payment.id), "session_id": str(session.id),
        "tariff_price_minor": plan.price_minor, "credit_applied_minor": applied_credit,
        "amount_due_minor": amount_due, "credit_carried_minor": carry_credit,
    }, actor_user_id=actor_user_id)


def _sync_attendance_usage(db: Session, org_id: UUID, session: LessonSession, attendance: Attendance, explicit_consume: bool | None, actor_user_id: UUID | None) -> None:
    current = db.scalar(select(SubscriptionUsage).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.session_id == session.id,
        SubscriptionUsage.student_id == attendance.student_id,
    ))
    eligible = _eligible_subscription_for_session(db, org_id, attendance.student_id, session)
    plan = eligible[1] if eligible else None
    _sync_makeup_credit(db, org_id, session, attendance.student_id, plan, attendance.status)

    # A pending excused absence is used before a new subscription lesson. This
    # lets a child work it off even after the original 30-day period ended.
    used_makeup = False
    if attendance.status in {AttendanceStatus.PRESENT, AttendanceStatus.LATE}:
        used_makeup = _complete_oldest_makeup(db, org_id, attendance.student_id, session.id)

    should_consume = bool(plan and not used_makeup and _attendance_should_consume(plan, attendance.status, explicit_consume))
    if should_consume and eligible is not None:
        subscription, plan = eligible
        if current is None:
            current = SubscriptionUsage(
                organization_id=org_id, subscription_id=subscription.id, student_id=attendance.student_id,
                session_id=session.id, attendance_id=attendance.id, units=1, source_status=attendance.status.value,
            )
            db.add(current)
            db.flush()
        else:
            current.subscription_id = subscription.id
            current.attendance_id = attendance.id
            current.source_status = attendance.status.value
        db.flush()
        _renew_after_last_lesson(db, org_id, subscription, plan, session, actor_user_id)
    elif current is not None:
        db.delete(current)
        db.flush()


def mark_attendance_bulk(db: Session, org_id: UUID, session_id: UUID, items, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[Attendance]:
    session = scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, session.group_id)
    roster_ids = {item["student_id"] for item in group_roster(db, org_id, session.group_id, user_id, role)}
    submitted_ids = [item.student_id for item in items]
    if len(set(submitted_ids)) != len(submitted_ids):
        raise HTTPException(status_code=422, detail="Duplicate students in attendance payload")
    if not set(submitted_ids).issubset(roster_ids):
        raise HTTPException(status_code=409, detail="Відвідування можна відмічати лише для активних учнів цієї групи")

    result: list[Attendance] = []
    for mark in items:
        row = db.scalar(select(Attendance).where(
            Attendance.organization_id == org_id,
            Attendance.session_id == session.id,
            Attendance.student_id == mark.student_id,
        ))
        if row is None:
            row = Attendance(
                organization_id=org_id,
                session_id=session.id,
                student_id=mark.student_id,
                status=mark.status,
                note=mark.note,
            )
            db.add(row)
        else:
            row.status = mark.status
            row.note = mark.note
        db.flush()
        _sync_attendance_usage(db, org_id, session, row, getattr(mark, "consume_lesson", None), user_id)
        result.append(row)

    if roster_ids and roster_ids.issubset(set(submitted_ids)):
        session.status = LessonStatus.COMPLETED

    record_audit(db, org_id, "lesson_session", session.id, "attendance.saved", {"marked_count": len(result), "group_id": str(session.group_id)}, actor_user_id=user_id)
    db.commit()
    for row in result:
        db.refresh(row)
    return result


def list_attendance(db: Session, org_id: UUID, session_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[Attendance]:
    session = scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, session.group_id)
    return list(db.scalars(
        select(Attendance)
        .where(Attendance.organization_id == org_id, Attendance.session_id == session_id)
        .order_by(Attendance.student_id)
    ))


def student_attendance_history(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> list[dict]:
    scoped_get(db, Student, org_id, student_id)
    allowed = assigned_group_ids_for_user(db, org_id, user_id, role)
    stmt = (
        select(Attendance, LessonSession, Group)
        .join(LessonSession, LessonSession.id == Attendance.session_id)
        .join(Group, Group.id == LessonSession.group_id)
        .where(
            Attendance.organization_id == org_id,
            Attendance.student_id == student_id,
            LessonSession.organization_id == org_id,
            Group.organization_id == org_id,
        )
    )
    if allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(LessonSession.group_id.in_(allowed))
    rows = db.execute(stmt.order_by(LessonSession.starts_at.desc())).all()
    return [
        {
            "session_id": session.id,
            "group_id": session.group_id,
            "group_name": group.name,
            "starts_at": session.starts_at,
            "duration_minutes": session.duration_minutes,
            "topic": session.topic,
            "lesson_status": session.status,
            "status": attendance.status,
            "note": attendance.note,
        }
        for attendance, session, group in rows
    ]


# Compatibility forwarding for the extracted billing domain.
