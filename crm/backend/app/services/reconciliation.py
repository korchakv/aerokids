from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    AttendanceStatus,
    LessonSession,
    LessonStatus,
    MakeupCredit,
    Payment,
    PaymentStatus,
    PaymentTransaction,
    Student,
    StudentStatus,
    StudentSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
    SubscriptionUsage,
)
from app.models.hardening import (
    IndividualAttendance,
    IndividualLessonSession,
    IndividualSubscriptionUsage,
    LessonDerivedBilling,
    LessonFinalization,
    MakeupCompletionLink,
)
from app.models.hardening_extensions import AttendanceDecision, IndividualDerivedBilling
from app.services import crm, hardening


def _upsert_decision(
    db: Session,
    org_id: UUID,
    session_id: UUID,
    student_id: UUID,
    consume_lesson: bool | None,
    actor_user_id: UUID | None,
) -> AttendanceDecision:
    row = db.scalar(select(AttendanceDecision).where(
        AttendanceDecision.organization_id == org_id,
        AttendanceDecision.session_id == session_id,
        AttendanceDecision.student_id == student_id,
    ))
    if row is None:
        row = AttendanceDecision(
            organization_id=org_id,
            session_id=session_id,
            student_id=student_id,
            consume_lesson=consume_lesson,
            updated_by_user_id=actor_user_id,
        )
        db.add(row)
    else:
        row.consume_lesson = consume_lesson
        row.updated_by_user_id = actor_user_id
        row.updated_at = datetime.now(timezone.utc)
    return row


def _decision_map(db: Session, org_id: UUID, session_id: UUID) -> dict[UUID, bool | None]:
    return {
        row.student_id: row.consume_lesson
        for row in db.scalars(select(AttendanceDecision).where(
            AttendanceDecision.organization_id == org_id,
            AttendanceDecision.session_id == session_id,
        ))
    }


def _first_future_group_lesson_date(db: Session, org_id: UUID, group_id: UUID | None, after_date):
    if group_id is None:
        return after_date
    rows = list(db.scalars(select(LessonSession).where(
        LessonSession.organization_id == org_id,
        LessonSession.group_id == group_id,
        LessonSession.status != LessonStatus.CANCELLED,
    ).order_by(LessonSession.starts_at)))
    for row in rows:
        local_date = hardening._local_date(db, org_id, row.starts_at)
        if local_date >= after_date:
            return local_date
    return after_date


def _create_group_renewal(
    db: Session,
    org_id: UUID,
    subscription: StudentSubscription,
    plan: SubscriptionPlan,
    session: LessonSession,
    actor_user_id: UUID | None,
) -> None:
    included = subscription.lessons_included if subscription.lessons_included is not None else plan.lessons_included
    if not subscription.auto_renew or plan.renewal_trigger != "last_lesson" or included is None or not plan.is_active:
        return
    if hardening._subscription_used_units(db, org_id, subscription.id) < included:
        return
    existing = db.scalar(select(StudentSubscription.id).where(
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
    next_start = _first_future_group_lesson_date(
        db,
        org_id,
        subscription.group_id,
        hardening._local_date(db, org_id, session.starts_at) + timedelta(days=1),
    )
    credit_before = max(0, subscription.credit_minor)
    applied_credit = min(credit_before, plan.price_minor)
    carry_credit = max(0, credit_before - applied_credit)
    amount_due = max(0, plan.price_minor - applied_credit)
    child = StudentSubscription(
        organization_id=org_id,
        student_id=subscription.student_id,
        plan_id=plan.id,
        group_id=subscription.group_id,
        status=SubscriptionStatus.ACTIVE,
        starts_on=next_start,
        ends_on=crm._subscription_end_date(next_start, plan.period_days),
        price_minor=plan.price_minor,
        period_days=plan.period_days,
        lessons_included=plan.lessons_included,
        lesson_unit_price_minor=crm._lesson_unit_price(plan.price_minor, plan.lessons_included),
        credit_minor=carry_credit,
        discount_minor=0,
        discount_label=None,
        auto_renew=True,
        renewal_of_id=subscription.id,
    )
    db.add(child)
    db.flush()
    payment = Payment(
        organization_id=org_id,
        student_id=subscription.student_id,
        subscription_id=child.id,
        amount_minor=amount_due,
        currency=organization.currency,
        due_date=next_start,
        note=f"{plan.name} · продовження після фіналізації заняття",
        status=PaymentStatus.PAID if amount_due == 0 else PaymentStatus.PENDING,
        paid_at=datetime.now(timezone.utc) if amount_due == 0 else None,
    )
    db.add(payment)
    db.flush()
    db.add(LessonDerivedBilling(
        organization_id=org_id,
        session_id=session.id,
        parent_subscription_id=subscription.id,
        renewal_subscription_id=child.id,
        payment_id=payment.id,
        parent_credit_before_minor=credit_before,
    ))
    subscription.credit_minor = 0
    subscription.status = SubscriptionStatus.EXPIRED
    crm.record_audit(db, org_id, "student", subscription.student_id, "subscription.renewed_after_finalized_lesson", {
        "session_id": str(session.id),
        "previous_subscription_id": str(subscription.id),
        "subscription_id": str(child.id),
        "payment_id": str(payment.id),
        "amount_due_minor": amount_due,
    }, actor_user_id)


def finalize_group_lesson(db: Session, org_id: UUID, session: LessonSession, actor_user_id: UUID | None) -> None:
    finalization = db.scalar(select(LessonFinalization).where(
        LessonFinalization.organization_id == org_id,
        LessonFinalization.session_id == session.id,
    ))
    if finalization is not None:
        return

    lesson_date = hardening._local_date(db, org_id, session.starts_at)
    roster = hardening.historical_roster_ids(db, org_id, session.group_id, lesson_date)
    marks = list(db.scalars(select(Attendance).where(
        Attendance.organization_id == org_id,
        Attendance.session_id == session.id,
    )))
    if roster and not roster.issubset({row.student_id for row in marks}):
        raise HTTPException(status_code=409, detail="Перед завершенням відмітьте всіх учнів цього заняття")

    decisions = _decision_map(db, org_id, session.id)
    db.execute(delete(SubscriptionUsage).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.session_id == session.id,
    ))
    touched: dict[UUID, tuple[StudentSubscription, SubscriptionPlan]] = {}
    for mark in marks:
        eligible = hardening._eligible_subscription(db, org_id, mark.student_id, lesson_date, session.group_id)
        plan = eligible[1] if eligible else None
        hardening._sync_excused_makeup(db, org_id, session, mark.student_id, plan, mark.status)
        used_makeup = False
        if mark.status in {AttendanceStatus.PRESENT, AttendanceStatus.LATE}:
            used_makeup = hardening._consume_oldest_makeup(db, org_id, mark.student_id, session.id, lesson_date)
        explicit = decisions.get(mark.student_id)
        if eligible is not None and not used_makeup and hardening._should_consume(plan, mark.status, explicit):
            subscription, plan = eligible
            db.add(SubscriptionUsage(
                organization_id=org_id,
                subscription_id=subscription.id,
                student_id=mark.student_id,
                session_id=session.id,
                attendance_id=mark.id,
                units=1,
                source_status=mark.status.value,
            ))
            touched[subscription.id] = (subscription, plan)
    db.flush()
    for subscription, plan in touched.values():
        _create_group_renewal(db, org_id, subscription, plan, session, actor_user_id)
    session.status = LessonStatus.COMPLETED
    db.add(LessonFinalization(
        organization_id=org_id,
        session_id=session.id,
        finalized_by_user_id=actor_user_id,
        revision=1,
    ))
    crm.record_audit(db, org_id, "lesson_session", session.id, "lesson.finalized", {
        "marked_count": len(marks),
        "lesson_date": lesson_date.isoformat(),
    }, actor_user_id)


def save_group_attendance(
    db: Session,
    org_id: UUID,
    session_id: UUID,
    items,
    actor_user_id: UUID | None,
    role,
) -> list[Attendance]:
    session = crm.scoped_get(db, LessonSession, org_id, session_id)
    hardening.ensure_group_access(db, org_id, actor_user_id, role, session.group_id)
    existing_finalization = db.scalar(select(LessonFinalization.id).where(
        LessonFinalization.organization_id == org_id,
        LessonFinalization.session_id == session.id,
    ))
    if existing_finalization is not None:
        hardening._reopen_group_lesson_no_commit(db, org_id, session, actor_user_id)
        db.flush()

    lesson_date = hardening._local_date(db, org_id, session.starts_at)
    roster = hardening.historical_roster_ids(db, org_id, session.group_id, lesson_date)
    submitted_ids = [item.student_id for item in items]
    if len(set(submitted_ids)) != len(submitted_ids):
        raise HTTPException(status_code=422, detail="Учень переданий двічі")
    if not set(submitted_ids).issubset(roster):
        raise HTTPException(status_code=409, detail="Можна відмічати лише учнів, які були в групі на дату заняття")

    result: list[Attendance] = []
    for mark in items:
        if mark.status == AttendanceStatus.LATE:
            previous = db.scalar(select(Attendance).where(
                Attendance.organization_id == org_id,
                Attendance.session_id == session.id,
                Attendance.student_id == mark.student_id,
            ))
            if previous is None or previous.status != AttendanceStatus.LATE:
                raise HTTPException(status_code=422, detail="Статус «Запізнення» залишено лише для старої історії")
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
        _upsert_decision(db, org_id, session.id, mark.student_id, mark.consume_lesson, actor_user_id)
        result.append(row)
    db.flush()

    marked = set(db.scalars(select(Attendance.student_id).where(
        Attendance.organization_id == org_id,
        Attendance.session_id == session.id,
    )))
    if not roster or roster.issubset(marked):
        finalize_group_lesson(db, org_id, session, actor_user_id)
    crm.record_audit(db, org_id, "lesson_session", session.id, "attendance.saved_reconciled", {
        "marked_count": len(result),
        "historical_roster_count": len(roster),
    }, actor_user_id)
    db.commit()
    for row in result:
        db.refresh(row)
    return result


def reopen_group_lesson(db: Session, org_id: UUID, session_id: UUID, actor_user_id: UUID | None, role) -> LessonSession:
    session = crm.scoped_get(db, LessonSession, org_id, session_id)
    hardening.ensure_group_access(db, org_id, actor_user_id, role, session.group_id)
    hardening._reopen_group_lesson_no_commit(db, org_id, session, actor_user_id)
    db.commit()
    db.refresh(session)
    return session


def _individual_next_start(db: Session, org_id: UUID, session: IndividualLessonSession):
    lesson_date = hardening._local_date(db, org_id, session.starts_at)
    rows = list(db.scalars(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org_id,
        IndividualLessonSession.student_id == session.student_id,
        IndividualLessonSession.id != session.id,
        IndividualLessonSession.status != "cancelled",
    ).order_by(IndividualLessonSession.starts_at)))
    for row in rows:
        candidate = hardening._local_date(db, org_id, row.starts_at)
        if candidate > lesson_date:
            return candidate
    return lesson_date + timedelta(days=1)


def _reopen_individual_no_commit(db: Session, org_id: UUID, session: IndividualLessonSession) -> None:
    links = list(db.scalars(select(IndividualDerivedBilling).where(
        IndividualDerivedBilling.organization_id == org_id,
        IndividualDerivedBilling.session_id == session.id,
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
                detail="Індивідуальне заняття вже створило фінансову операцію. Спочатку зробіть фінансове коригування.",
            )
        child = crm.scoped_get(db, StudentSubscription, org_id, link.renewal_subscription_id)
        parent = crm.scoped_get(db, StudentSubscription, org_id, link.parent_subscription_id)
        payment.status = PaymentStatus.CANCELLED
        child.status = SubscriptionStatus.CANCELLED
        parent.credit_minor = link.parent_credit_before_minor
        parent.status = SubscriptionStatus.ACTIVE
        db.delete(link)
    db.execute(delete(IndividualSubscriptionUsage).where(
        IndividualSubscriptionUsage.organization_id == org_id,
        IndividualSubscriptionUsage.session_id == session.id,
    ))
    session.status = "scheduled"
    session.finalized_at = None


def _renew_individual(
    db: Session,
    org_id: UUID,
    subscription: StudentSubscription,
    plan: SubscriptionPlan,
    session: IndividualLessonSession,
    actor_user_id: UUID | None,
) -> None:
    included = subscription.lessons_included if subscription.lessons_included is not None else plan.lessons_included
    if not subscription.auto_renew or plan.renewal_trigger != "last_lesson" or included is None or not plan.is_active:
        return
    if hardening._subscription_used_units(db, org_id, subscription.id) < included:
        return
    if db.scalar(select(StudentSubscription.id).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.renewal_of_id == subscription.id,
        StudentSubscription.status != SubscriptionStatus.CANCELLED,
    )) is not None:
        return
    student = crm.scoped_get(db, Student, org_id, subscription.student_id)
    if student.student_status != StudentStatus.ACTIVE:
        return
    organization = crm.require_organization(db, org_id)
    next_start = _individual_next_start(db, org_id, session)
    credit_before = max(0, subscription.credit_minor)
    applied_credit = min(credit_before, plan.price_minor)
    carry_credit = max(0, credit_before - applied_credit)
    amount_due = max(0, plan.price_minor - applied_credit)
    child = StudentSubscription(
        organization_id=org_id,
        student_id=student.id,
        plan_id=plan.id,
        group_id=None,
        status=SubscriptionStatus.ACTIVE,
        starts_on=next_start,
        ends_on=crm._subscription_end_date(next_start, plan.period_days),
        price_minor=plan.price_minor,
        period_days=plan.period_days,
        lessons_included=plan.lessons_included,
        lesson_unit_price_minor=crm._lesson_unit_price(plan.price_minor, plan.lessons_included),
        credit_minor=carry_credit,
        discount_minor=0,
        discount_label=None,
        auto_renew=True,
        renewal_of_id=subscription.id,
    )
    db.add(child)
    db.flush()
    payment = Payment(
        organization_id=org_id,
        student_id=student.id,
        subscription_id=child.id,
        amount_minor=amount_due,
        currency=organization.currency,
        due_date=next_start,
        note=f"{plan.name} · індивідуальне продовження",
        status=PaymentStatus.PAID if amount_due == 0 else PaymentStatus.PENDING,
        paid_at=datetime.now(timezone.utc) if amount_due == 0 else None,
    )
    db.add(payment)
    db.flush()
    db.add(IndividualDerivedBilling(
        organization_id=org_id,
        session_id=session.id,
        parent_subscription_id=subscription.id,
        renewal_subscription_id=child.id,
        payment_id=payment.id,
        parent_credit_before_minor=credit_before,
    ))
    subscription.credit_minor = 0
    subscription.status = SubscriptionStatus.EXPIRED
    crm.record_audit(db, org_id, "student", student.id, "subscription.individual_renewal", {
        "session_id": str(session.id),
        "subscription_id": str(child.id),
        "payment_id": str(payment.id),
    }, actor_user_id)


def save_individual_attendance(
    db: Session,
    org_id: UUID,
    session_id: UUID,
    status: AttendanceStatus,
    note: str | None,
    actor_user_id: UUID | None,
) -> IndividualAttendance:
    if status == AttendanceStatus.LATE:
        raise HTTPException(status_code=422, detail="Статус «Запізнення» більше не використовується")
    session = db.scalar(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org_id,
        IndividualLessonSession.id == session_id,
    ).with_for_update())
    if session is None:
        raise HTTPException(status_code=404, detail="Індивідуальне заняття не знайдено")
    if session.status == "cancelled":
        raise HTTPException(status_code=409, detail="Скасоване заняття не можна провести")
    if session.status == "completed":
        _reopen_individual_no_commit(db, org_id, session)
        db.flush()

    mark = db.scalar(select(IndividualAttendance).where(
        IndividualAttendance.organization_id == org_id,
        IndividualAttendance.session_id == session.id,
    ))
    if mark is None:
        mark = IndividualAttendance(
            organization_id=org_id,
            session_id=session.id,
            student_id=session.student_id,
            status=status.value,
            note=note,
        )
        db.add(mark)
    else:
        mark.status = status.value
        mark.note = note
        mark.updated_at = datetime.now(timezone.utc)
    db.flush()

    lesson_date = hardening._local_date(db, org_id, session.starts_at)
    eligible = hardening._eligible_subscription(db, org_id, session.student_id, lesson_date, None)
    if eligible is not None:
        subscription, plan = eligible
        if hardening._should_consume(plan, status, None):
            db.add(IndividualSubscriptionUsage(
                organization_id=org_id,
                session_id=session.id,
                subscription_id=subscription.id,
                student_id=session.student_id,
                units=1,
                source_status=status.value,
            ))
            db.flush()
            _renew_individual(db, org_id, subscription, plan, session, actor_user_id)
    session.status = "completed"
    session.finalized_at = datetime.now(timezone.utc)
    crm.record_audit(db, org_id, "student", session.student_id, "individual_lesson.finalized_reconciled", {
        "session_id": str(session.id),
        "status": status.value,
    }, actor_user_id)
    db.commit()
    db.refresh(mark)
    return mark
