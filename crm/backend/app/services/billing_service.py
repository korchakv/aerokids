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

# Lazy-loaded by the legacy crm facade after crm.py has initialized. These
# aliases preserve the exact legacy behavior while the billing domain lives
# in its own module.
scoped_get = crm.scoped_get
record_audit = crm.record_audit
require_organization = crm.require_organization
_primary_contact_for_student = crm._primary_contact_for_student
_comparable_dt = crm._comparable_dt
materialize_recurring_lesson_sessions = crm.materialize_recurring_lesson_sessions

def _payment_transactions(db: Session, org_id: UUID, payment_id: UUID) -> list[PaymentTransaction]:
    return list(db.scalars(
        select(PaymentTransaction)
        .where(
            PaymentTransaction.organization_id == org_id,
            PaymentTransaction.payment_id == payment_id,
        )
        .order_by(PaymentTransaction.occurred_at, PaymentTransaction.id)
    ))


def _materialize_legacy_settlement(db: Session, org_id: UUID, payment: Payment) -> None:
    transactions = _payment_transactions(db, org_id, payment.id)
    if transactions or payment.status != PaymentStatus.PAID:
        return
    db.add(PaymentTransaction(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        kind="payment",
        amount_minor=payment.amount_minor,
        method=payment.method.value if payment.method else None,
        note="Legacy full payment migrated to ledger",
        occurred_at=payment.paid_at or payment.created_at,
    ))
    db.flush()


def payment_financials(db: Session, org_id: UUID, payment: Payment) -> dict:
    transactions = _payment_transactions(db, org_id, payment.id)
    increases = sum(item.amount_minor for item in transactions if item.kind == "adjustment_increase")
    decreases = sum(item.amount_minor for item in transactions if item.kind == "adjustment_decrease")
    adjusted_amount = max(0, payment.amount_minor + increases - decreases)
    paid_minor = sum(item.amount_minor for item in transactions if item.kind == "payment")
    refunded_minor = sum(item.amount_minor for item in transactions if item.kind == "refund")

    # Backward compatibility for charges that were fully paid before ledger transactions existed.
    if not transactions and payment.status == PaymentStatus.PAID:
        paid_minor = adjusted_amount

    net_paid = max(0, paid_minor - refunded_minor)
    balance = max(0, adjusted_amount - net_paid)
    credit = max(0, net_paid - adjusted_amount)
    return {
        "adjusted_amount_minor": adjusted_amount,
        "paid_minor": paid_minor,
        "refunded_minor": refunded_minor,
        "net_paid_minor": net_paid,
        "balance_minor": balance,
        "credit_minor": credit,
        "transactions": transactions,
    }


def _sync_payment_state(db: Session, org_id: UUID, payment: Payment) -> dict:
    finance = payment_financials(db, org_id, payment)
    if payment.status != PaymentStatus.CANCELLED:
        if finance["adjusted_amount_minor"] == 0 and finance["net_paid_minor"] == 0 and finance["refunded_minor"] > 0:
            payment.status = PaymentStatus.REFUNDED
        elif finance["balance_minor"] == 0 and (finance["adjusted_amount_minor"] > 0 or finance["net_paid_minor"] > 0):
            payment.status = PaymentStatus.PAID
        else:
            payment.status = PaymentStatus.PENDING
    payment.adjusted_amount_minor = finance["adjusted_amount_minor"]
    payment.paid_minor = finance["paid_minor"]
    payment.refunded_minor = finance["refunded_minor"]
    payment.balance_minor = finance["balance_minor"]
    payment.credit_minor = finance["credit_minor"]
    return finance


def _attach_payment_financials(db: Session, org_id: UUID, payment: Payment) -> Payment:
    finance = payment_financials(db, org_id, payment)
    payment.adjusted_amount_minor = finance["adjusted_amount_minor"]
    payment.paid_minor = finance["paid_minor"]
    payment.refunded_minor = finance["refunded_minor"]
    payment.balance_minor = finance["balance_minor"]
    payment.credit_minor = finance["credit_minor"]
    return payment


def _subscription_end_date(starts_on: date, period_days: int | None) -> date | None:
    return starts_on + timedelta(days=period_days - 1) if period_days is not None else None


def _lesson_unit_price(price_minor: int, lessons_included: int | None) -> int | None:
    if lessons_included is None or lessons_included <= 0:
        return None
    return int(round(price_minor / lessons_included))


def _first_planned_lesson_date(
    db: Session,
    org_id: UUID,
    group_id: UUID | None,
    not_before: date,
) -> date:
    if group_id is None:
        return not_before
    materialize_recurring_lesson_sessions(db, org_id)
    organization = require_organization(db, org_id)
    try:
        tz = ZoneInfo(organization.timezone)
    except Exception:
        tz = timezone.utc
    candidates = list(db.scalars(
        select(LessonSession).where(
            LessonSession.organization_id == org_id,
            LessonSession.group_id == group_id,
            LessonSession.status != LessonStatus.CANCELLED,
        ).order_by(LessonSession.starts_at)
    ))
    for lesson in candidates:
        local_date = _comparable_dt(lesson.starts_at, organization.timezone).date()
        if local_date >= not_before:
            return local_date
    return not_before


def create_subscription_plan(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> SubscriptionPlan:
    require_organization(db, org_id)
    item = SubscriptionPlan(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.flush()
    record_audit(
        db,
        org_id,
        "subscription_plan",
        item.id,
        "subscription_plan.created",
        {
            "name": item.name,
            "price_minor": item.price_minor,
            "period_days": item.period_days,
            "lessons_included": item.lessons_included,
            "is_active": item.is_active,
        },
        actor_user_id=actor_user_id,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Тариф із такою назвою вже існує") from exc
    db.refresh(item)
    return item


def update_subscription_plan(
    db: Session,
    org_id: UUID,
    plan_id: UUID,
    data,
    actor_user_id: UUID | None = None,
) -> SubscriptionPlan:
    plan = scoped_get(db, SubscriptionPlan, org_id, plan_id)
    before = {
        "name": plan.name,
        "price_minor": plan.price_minor,
        "period_days": plan.period_days,
        "lessons_included": plan.lessons_included,
        "is_active": plan.is_active,
    }
    plan.name = data.name
    plan.price_minor = data.price_minor
    plan.period_days = data.period_days
    plan.lessons_included = data.lessons_included
    plan.is_active = data.is_active
    after = {
        "name": plan.name,
        "price_minor": plan.price_minor,
        "period_days": plan.period_days,
        "lessons_included": plan.lessons_included,
        "is_active": plan.is_active,
    }
    changed_fields = [key for key in after if before[key] != after[key]]
    if changed_fields:
        record_audit(
            db,
            org_id,
            "subscription_plan",
            plan.id,
            "subscription_plan.updated",
            {"before": before, "after": after, "changed_fields": changed_fields},
            actor_user_id=actor_user_id,
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Тариф із такою назвою вже існує") from exc
    db.refresh(plan)
    return plan


def list_subscription_plans(db: Session, org_id: UUID) -> list[SubscriptionPlan]:
    return list(db.scalars(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.organization_id == org_id)
        .order_by(SubscriptionPlan.is_active.desc(), SubscriptionPlan.name)
    ))


def create_student_subscription(db: Session, org_id: UUID, data) -> StudentSubscription:
    student = scoped_get(db, Student, org_id, data.student_id)
    plan = scoped_get(db, SubscriptionPlan, org_id, data.plan_id)
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="Неактивний тариф не можна призначити новому абонементу")
    price_minor = data.price_minor if data.price_minor is not None else plan.price_minor
    if data.discount_minor > price_minor:
        raise HTTPException(status_code=422, detail="Знижка не може бути більшою за вартість тарифу")
    group_id = getattr(data, "group_id", None)
    starts_on = _first_planned_lesson_date(db, org_id, group_id, data.starts_on)
    item = StudentSubscription(
        organization_id=org_id,
        student_id=student.id,
        plan_id=plan.id,
        group_id=group_id,
        starts_on=starts_on,
        ends_on=_subscription_end_date(starts_on, plan.period_days),
        price_minor=price_minor,
        period_days=plan.period_days,
        lessons_included=plan.lessons_included,
        lesson_unit_price_minor=_lesson_unit_price(max(0, price_minor - data.discount_minor), plan.lessons_included),
        credit_minor=0,
        discount_minor=data.discount_minor,
        discount_label=data.discount_label,
        auto_renew=getattr(data, "auto_renew", False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def subscription_usage_summary(db: Session, org_id: UUID, subscription: StudentSubscription) -> dict:
    plan = scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
    included = subscription.lessons_included
    if included is None and subscription.period_days is None:
        # Legacy row created before tariff snapshots existed.
        included = plan.lessons_included
    used = db.scalar(select(func.coalesce(func.sum(SubscriptionUsage.units), 0)).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.subscription_id == subscription.id,
    )) or 0
    remaining = max(0, included - int(used)) if included is not None else None
    return {"used_lessons": int(used), "remaining_lessons": remaining, "needs_renewal": remaining == 1 if remaining is not None else False}


def _attach_subscription_usage(db: Session, org_id: UUID, subscription: StudentSubscription) -> StudentSubscription:
    summary = subscription_usage_summary(db, org_id, subscription)
    subscription.used_lessons = summary["used_lessons"]
    subscription.remaining_lessons = summary["remaining_lessons"]
    subscription.needs_renewal = summary["needs_renewal"]
    return subscription


def list_student_subscriptions(db: Session, org_id: UUID, student_id: UUID | None = None) -> list[StudentSubscription]:
    stmt = select(StudentSubscription).where(StudentSubscription.organization_id == org_id)
    if student_id is not None:
        scoped_get(db, Student, org_id, student_id)
        stmt = stmt.where(StudentSubscription.student_id == student_id)
    rows = list(db.scalars(stmt.order_by(StudentSubscription.starts_on.desc())))
    return [_attach_subscription_usage(db, org_id, row) for row in rows]


def set_subscription_auto_renew(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    auto_renew: bool,
    actor_user_id: UUID | None = None,
) -> StudentSubscription:
    subscription = scoped_get(db, StudentSubscription, org_id, subscription_id)
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cancelled subscription cannot be renewed")
    subscription.auto_renew = auto_renew
    record_audit(
        db,
        org_id,
        "student",
        subscription.student_id,
        "subscription.auto_renew_changed",
        {"subscription_id": str(subscription.id), "auto_renew": auto_renew},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(subscription)
    return subscription


def pause_subscription(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    starts_on: date,
    resume_on: date | None = None,
    note: str | None = None,
    actor_user_id: UUID | None = None,
) -> SubscriptionPause:
    subscription = scoped_get(db, StudentSubscription, org_id, subscription_id)
    if subscription.status in {SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED}:
        raise HTTPException(status_code=409, detail="Subscription cannot be paused")
    if starts_on < subscription.starts_on or (subscription.ends_on is not None and starts_on > subscription.ends_on):
        raise HTTPException(status_code=422, detail="Пауза має починатися в межах поточного абонемента")

    existing = db.scalar(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.subscription_id == subscription.id,
        SubscriptionPause.resumed_at.is_(None),
    ))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Subscription already has an active or scheduled pause")

    ends_on = resume_on - timedelta(days=1) if resume_on else None
    pause = SubscriptionPause(
        organization_id=org_id,
        subscription_id=subscription.id,
        student_id=subscription.student_id,
        starts_on=starts_on,
        ends_on=ends_on,
        note=note,
    )
    db.add(pause)
    today = date.today()
    if starts_on <= today and (ends_on is None or today <= ends_on):
        subscription.status = SubscriptionStatus.PAUSED
    record_audit(
        db,
        org_id,
        "student",
        subscription.student_id,
        "subscription.paused",
        {
            "subscription_id": str(subscription.id),
            "starts_on": starts_on.isoformat(),
            "resume_on": resume_on.isoformat() if resume_on else None,
            "note": note,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(pause)
    return pause


def _finish_subscription_pause(
    db: Session,
    org_id: UUID,
    subscription: StudentSubscription,
    pause: SubscriptionPause,
    resumes_on: date,
    actor_user_id: UUID | None = None,
    automatic: bool = False,
) -> None:
    if resumes_on <= pause.starts_on:
        raise HTTPException(status_code=422, detail="Resume date must be after pause start")
    pause_end = resumes_on - timedelta(days=1)
    if pause.ends_on is not None and pause_end > pause.ends_on:
        pause_end = pause.ends_on
        resumes_on = pause_end + timedelta(days=1)
    pause.ends_on = pause_end
    pause.resumed_at = datetime.now(timezone.utc)
    paused_days = (pause_end - pause.starts_on).days + 1
    if subscription.ends_on is not None:
        subscription.ends_on = subscription.ends_on + timedelta(days=paused_days)
        subscription.status = SubscriptionStatus.ACTIVE if subscription.ends_on >= resumes_on else SubscriptionStatus.EXPIRED
    else:
        subscription.status = SubscriptionStatus.ACTIVE
    record_audit(
        db,
        org_id,
        "student",
        subscription.student_id,
        "subscription.resumed",
        {
            "subscription_id": str(subscription.id),
            "resumes_on": resumes_on.isoformat(),
            "paused_days": paused_days,
            "automatic": automatic,
        },
        actor_user_id=actor_user_id,
    )


def resume_subscription(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    resumes_on: date | None = None,
    actor_user_id: UUID | None = None,
) -> StudentSubscription:
    subscription = scoped_get(db, StudentSubscription, org_id, subscription_id)
    pause = db.scalar(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.subscription_id == subscription.id,
        SubscriptionPause.resumed_at.is_(None),
    ).order_by(SubscriptionPause.created_at.desc()))
    if pause is None:
        raise HTTPException(status_code=409, detail="Subscription has no active pause")

    resume_date = resumes_on or date.today()
    _finish_subscription_pause(db, org_id, subscription, pause, resume_date, actor_user_id)
    db.commit()
    db.refresh(subscription)
    return subscription


def _resume_due_pauses(db: Session, org_id: UUID, today: date, actor_user_id: UUID | None = None) -> int:
    rows = list(db.scalars(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.resumed_at.is_(None),
        SubscriptionPause.ends_on.is_not(None),
        SubscriptionPause.ends_on < today,
    )))
    count = 0
    for pause in rows:
        subscription = scoped_get(db, StudentSubscription, org_id, pause.subscription_id)
        _finish_subscription_pause(
            db,
            org_id,
            subscription,
            pause,
            pause.ends_on + timedelta(days=1),
            actor_user_id,
            automatic=True,
        )
        count += 1
    if count:
        db.commit()
    return count


def run_billing_renewals(
    db: Session,
    org_id: UUID,
    through_date: date | None = None,
    actor_user_id: UUID | None = None,
) -> dict:
    organization = require_organization(db, org_id)
    today = date.today()
    horizon = through_date or (today + timedelta(days=7))
    if horizon < today:
        raise HTTPException(status_code=422, detail="Дата перевірки не може бути в минулому")

    resumed = _resume_due_pauses(db, org_id, today, actor_user_id)
    expired_rows = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.status == SubscriptionStatus.ACTIVE,
        StudentSubscription.ends_on.is_not(None),
        StudentSubscription.ends_on < today,
    )))
    for expired in expired_rows:
        open_pause = db.scalar(select(SubscriptionPause.id).where(
            SubscriptionPause.organization_id == org_id,
            SubscriptionPause.subscription_id == expired.id,
            SubscriptionPause.resumed_at.is_(None),
        ))
        if open_pause is None:
            expired.status = SubscriptionStatus.EXPIRED
    if expired_rows:
        db.flush()

    created_payment_ids: list[UUID] = []
    created_subscriptions = 0
    skipped_stale_subscriptions = 0

    candidates = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.auto_renew.is_(True),
        StudentSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED]),
        StudentSubscription.ends_on.is_not(None),
        StudentSubscription.ends_on <= horizon,
    ).order_by(StudentSubscription.ends_on, StudentSubscription.created_at)))

    for original in candidates:
        current = original
        while (
            current.auto_renew
            and current.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED}
            and current.ends_on is not None
            and current.ends_on <= horizon
        ):
            open_pause = db.scalar(select(SubscriptionPause.id).where(
                SubscriptionPause.organization_id == org_id,
                SubscriptionPause.subscription_id == current.id,
                SubscriptionPause.resumed_at.is_(None),
            ))
            if open_pause is not None:
                break

            existing_child = db.scalar(select(StudentSubscription).where(
                StudentSubscription.organization_id == org_id,
                StudentSubscription.renewal_of_id == current.id,
                StudentSubscription.status != SubscriptionStatus.CANCELLED,
            ))
            if existing_child is not None:
                current = existing_child
                continue

            student = scoped_get(db, Student, org_id, current.student_id)
            if student.student_status != StudentStatus.ACTIVE:
                break
            active_enrollment = db.scalar(select(Enrollment.id).where(
                Enrollment.organization_id == org_id,
                Enrollment.student_id == student.id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
            ))
            if active_enrollment is None:
                break

            plan = scoped_get(db, SubscriptionPlan, org_id, current.plan_id)
            # An inactive tariff remains valid for the already-paid/current
            # period, but it must not be sold again automatically.
            if not plan.is_active:
                break

            current_period_days = current.period_days or plan.period_days or 30
            if current.ends_on < today - timedelta(days=current_period_days):
                skipped_stale_subscriptions += 1
                break

            next_start = _first_planned_lesson_date(
                db,
                org_id,
                current.group_id,
                current.ends_on + timedelta(days=1),
            )
            available_credit = max(0, current.credit_minor)
            applied_credit = min(available_credit, plan.price_minor)
            carry_credit = max(0, available_credit - applied_credit)
            amount_due = max(0, plan.price_minor - applied_credit)

            next_subscription = StudentSubscription(
                organization_id=org_id,
                student_id=student.id,
                plan_id=plan.id,
                group_id=current.group_id,
                status=SubscriptionStatus.ACTIVE,
                starts_on=next_start,
                ends_on=_subscription_end_date(next_start, plan.period_days),
                price_minor=plan.price_minor,
                period_days=plan.period_days,
                lessons_included=plan.lessons_included,
                lesson_unit_price_minor=_lesson_unit_price(plan.price_minor, plan.lessons_included),
                credit_minor=carry_credit,
                discount_minor=0,
                discount_label=None,
                auto_renew=True,
                renewal_of_id=current.id,
            )
            db.add(next_subscription)
            db.flush()
            payment = Payment(
                organization_id=org_id,
                student_id=student.id,
                subscription_id=next_subscription.id,
                amount_minor=amount_due,
                currency=organization.currency,
                due_date=next_start,
                note=f"{plan.name} · автоматичне продовження",
                status=PaymentStatus.PAID if amount_due == 0 else PaymentStatus.PENDING,
                paid_at=datetime.now(timezone.utc) if amount_due == 0 else None,
            )
            db.add(payment)
            db.flush()
            current.credit_minor = 0
            if current.ends_on < today:
                current.status = SubscriptionStatus.EXPIRED
            record_audit(
                db,
                org_id,
                "student",
                student.id,
                "subscription.renewed",
                {
                    "previous_subscription_id": str(current.id),
                    "subscription_id": str(next_subscription.id),
                    "payment_id": str(payment.id),
                    "starts_on": next_start.isoformat(),
                    "tariff_price_minor": plan.price_minor,
                    "credit_applied_minor": applied_credit,
                    "amount_due_minor": amount_due,
                    "credit_carried_minor": carry_credit,
                },
                actor_user_id=actor_user_id,
            )
            created_payment_ids.append(payment.id)
            created_subscriptions += 1
            current = next_subscription

    if created_subscriptions or expired_rows:
        db.commit()
    return {
        "resumed_subscriptions": resumed,
        "created_subscriptions": created_subscriptions,
        "skipped_stale_subscriptions": skipped_stale_subscriptions,
        "created_payment_ids": created_payment_ids,
    }

def create_subscription_charge(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> tuple[StudentSubscription, Payment]:
    organization = require_organization(db, org_id)
    student = scoped_get(db, Student, org_id, data.student_id)
    plan = scoped_get(db, SubscriptionPlan, org_id, data.plan_id)
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="Неактивний тариф не можна призначити новому абонементу")
    if data.discount_minor > plan.price_minor:
        raise HTTPException(status_code=422, detail="Знижка не може бути більшою за вартість тарифу")

    amount_minor = plan.price_minor - data.discount_minor
    if amount_minor <= 0:
        raise HTTPException(status_code=422, detail="Сума нарахування має бути більшою за нуль")

    group_id = getattr(data, "group_id", None)
    starts_on = _first_planned_lesson_date(db, org_id, group_id, data.starts_on)

    duplicate_subscription = db.scalar(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student.id,
        StudentSubscription.plan_id == plan.id,
        StudentSubscription.starts_on == starts_on,
        StudentSubscription.status != SubscriptionStatus.CANCELLED,
    ))
    if duplicate_subscription is not None:
        raise HTTPException(status_code=409, detail="На цей період уже є абонемент")

    subscription = StudentSubscription(
        organization_id=org_id,
        student_id=student.id,
        plan_id=plan.id,
        group_id=group_id,
        starts_on=starts_on,
        ends_on=_subscription_end_date(starts_on, plan.period_days),
        price_minor=plan.price_minor,
        period_days=plan.period_days,
        lessons_included=plan.lessons_included,
        lesson_unit_price_minor=_lesson_unit_price(amount_minor, plan.lessons_included),
        credit_minor=0,
        discount_minor=data.discount_minor,
        discount_label=data.discount_label,
        auto_renew=getattr(data, "auto_renew", False),
    )
    db.add(subscription)
    db.flush()

    payment = Payment(
        organization_id=org_id,
        student_id=student.id,
        subscription_id=subscription.id,
        amount_minor=amount_minor,
        currency=organization.currency,
        due_date=data.due_date or starts_on,
        note=data.note or plan.name,
    )
    db.add(payment)
    db.flush()
    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "payment.created",
        {
            "payment_id": str(payment.id),
            "subscription_id": str(subscription.id),
            "plan_id": str(plan.id),
            "amount_minor": amount_minor,
            "starts_on": starts_on.isoformat(),
            "due_date": payment.due_date.isoformat() if payment.due_date else None,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(subscription)
    db.refresh(payment)
    payment.plan_id = plan.id
    _attach_payment_financials(db, org_id, payment)
    return subscription, payment

def change_subscription_plan_now(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    new_plan_id: UUID,
    reason: str,
    actor_user_id: UUID | None = None,
) -> dict:
    subscription = scoped_get(db, StudentSubscription, org_id, subscription_id)
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Скасований абонемент не можна змінити")
    old_plan = scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
    new_plan = scoped_get(db, SubscriptionPlan, org_id, new_plan_id)
    if not new_plan.is_active:
        raise HTTPException(status_code=409, detail="Оберіть активний тариф")
    if old_plan.id == new_plan.id:
        raise HTTPException(status_code=409, detail="Цей тариф уже призначений учню")

    payment = db.scalar(select(Payment).where(
        Payment.organization_id == org_id,
        Payment.subscription_id == subscription.id,
        Payment.status != PaymentStatus.CANCELLED,
    ).order_by(Payment.created_at.desc()))
    if payment is None:
        raise HTTPException(status_code=409, detail="Для цього абонемента немає нарахування, яке можна перерахувати")

    _materialize_legacy_settlement(db, org_id, payment)
    finance_before = payment_financials(db, org_id, payment)
    summary = subscription_usage_summary(db, org_id, subscription)
    used_lessons = summary["used_lessons"]
    current_lessons = subscription.lessons_included
    if current_lessons is None and subscription.period_days is None:
        current_lessons = old_plan.lessons_included

    old_unit = subscription.lesson_unit_price_minor
    if old_unit is None and current_lessons:
        old_unit = _lesson_unit_price(finance_before["adjusted_amount_minor"], current_lessons)

    if used_lessons > 0:
        if current_lessons is None or new_plan.lessons_included is None:
            raise HTTPException(
                status_code=409,
                detail="Після початку періоду тариф можна змінити одразу лише коли обидва тарифи мають кількість занять.",
            )
        if new_plan.lessons_included != current_lessons:
            raise HTTPException(
                status_code=409,
                detail="Посеред періоду кількість занять не змінюємо. Нову кількість застосуйте з наступного періоду.",
            )
        remaining_lessons = max(0, current_lessons - used_lessons)
        old_unit = old_unit or 0
        new_unit = _lesson_unit_price(new_plan.price_minor, new_plan.lessons_included) or 0
        current_future_value = old_unit * remaining_lessons
        new_future_value = new_unit * remaining_lessons
        current_period_charge = max(
            0,
            finance_before["adjusted_amount_minor"] - current_future_value + new_future_value,
        )
    else:
        remaining_lessons = new_plan.lessons_included
        new_unit = _lesson_unit_price(new_plan.price_minor, new_plan.lessons_included)
        current_period_charge = new_plan.price_minor
        subscription.period_days = new_plan.period_days
        subscription.lessons_included = new_plan.lessons_included
        subscription.ends_on = _subscription_end_date(subscription.starts_on, new_plan.period_days)

    difference = current_period_charge - finance_before["adjusted_amount_minor"]
    if difference:
        db.add(PaymentTransaction(
            organization_id=org_id,
            payment_id=payment.id,
            student_id=payment.student_id,
            kind="adjustment_increase" if difference > 0 else "adjustment_decrease",
            amount_minor=abs(difference),
            note=f"Зміна тарифу зараз: {reason}",
            actor_user_id=actor_user_id,
        ))
        db.flush()

    subscription.plan_id = new_plan.id
    subscription.price_minor = current_period_charge
    subscription.lesson_unit_price_minor = new_unit
    subscription.discount_minor = 0
    subscription.discount_label = None

    finance_after = _sync_payment_state(db, org_id, payment)
    subscription.credit_minor = finance_after["credit_minor"]
    if payment.status != PaymentStatus.PAID:
        payment.paid_at = None

    record_audit(
        db,
        org_id,
        "student",
        subscription.student_id,
        "subscription.plan_changed_now",
        {
            "subscription_id": str(subscription.id),
            "payment_id": str(payment.id),
            "old_plan_id": str(old_plan.id),
            "old_plan_name": old_plan.name,
            "new_plan_id": str(new_plan.id),
            "new_plan_name": new_plan.name,
            "used_lessons": used_lessons,
            "remaining_lessons": remaining_lessons,
            "old_unit_price_minor": old_unit,
            "new_unit_price_minor": new_unit,
            "previous_charge_minor": finance_before["adjusted_amount_minor"],
            "current_period_charge_minor": current_period_charge,
            "credit_minor": finance_after["credit_minor"],
            "debt_minor": finance_after["balance_minor"],
            "reason": reason,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(subscription)
    db.refresh(payment)
    payment.plan_id = new_plan.id
    _attach_subscription_usage(db, org_id, subscription)
    _attach_payment_financials(db, org_id, payment)
    return {
        "subscription": subscription,
        "payment": payment,
        "used_lessons": used_lessons,
        "old_plan_id": old_plan.id,
        "new_plan_id": new_plan.id,
        "old_unit_price_minor": old_unit,
        "new_unit_price_minor": new_unit,
        "current_period_charge_minor": current_period_charge,
        "credit_minor": payment.credit_minor,
        "debt_minor": payment.balance_minor,
    }


def create_payment(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> Payment:
    organization = require_organization(db, org_id)
    student = scoped_get(db, Student, org_id, data.student_id)
    if data.subscription_id is not None:
        subscription = scoped_get(db, StudentSubscription, org_id, data.subscription_id)
        if subscription.student_id != student.id:
            raise HTTPException(status_code=409, detail="Subscription belongs to another student")
    item = Payment(
        organization_id=org_id,
        student_id=student.id,
        subscription_id=data.subscription_id,
        amount_minor=data.amount_minor,
        currency=organization.currency,
        due_date=data.due_date,
        note=data.note,
    )
    db.add(item)
    db.flush()
    record_audit(db, org_id, "student", student.id, "payment.created", {"payment_id": str(item.id), "amount_minor": item.amount_minor, "due_date": item.due_date.isoformat() if item.due_date else None}, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(item)
    item.plan_id = subscription.plan_id if data.subscription_id is not None else None
    return _attach_payment_financials(db, org_id, item)


def list_payments(db: Session, org_id: UUID, student_id: UUID | None = None, status: PaymentStatus | None = None) -> list[Payment]:
    stmt = select(Payment).where(Payment.organization_id == org_id)
    if student_id is not None:
        scoped_get(db, Student, org_id, student_id)
        stmt = stmt.where(Payment.student_id == student_id)
    if status is not None:
        stmt = stmt.where(Payment.status == status)
    rows = list(db.scalars(stmt.order_by(Payment.created_at.desc())))
    for row in rows:
        if row.subscription_id is not None:
            subscription = scoped_get(db, StudentSubscription, org_id, row.subscription_id)
            row.plan_id = subscription.plan_id
        else:
            row.plan_id = None
        _attach_payment_financials(db, org_id, row)
    return rows


def add_payment_receipt(
    db: Session,
    org_id: UUID,
    payment_id: UUID,
    amount_minor: int,
    method: PaymentMethod,
    paid_at: datetime | None = None,
    note: str | None = None,
    actor_user_id: UUID | None = None,
) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status in {PaymentStatus.CANCELLED, PaymentStatus.REFUNDED}:
        raise HTTPException(status_code=409, detail="This charge cannot accept payments")

    finance = payment_financials(db, org_id, payment)
    if amount_minor > finance["balance_minor"]:
        raise HTTPException(status_code=422, detail="Payment amount exceeds outstanding balance")

    occurred_at = paid_at or datetime.now(timezone.utc)
    transaction = PaymentTransaction(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        kind="payment",
        amount_minor=amount_minor,
        method=method.value,
        note=note,
        occurred_at=occurred_at,
        actor_user_id=actor_user_id,
    )
    db.add(transaction)
    db.flush()
    finance = _sync_payment_state(db, org_id, payment)
    payment.method = method
    payment.paid_at = occurred_at if finance["balance_minor"] == 0 else None
    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.received",
        {
            "payment_id": str(payment.id),
            "transaction_id": str(transaction.id),
            "amount_minor": amount_minor,
            "balance_minor": finance["balance_minor"],
            "method": method.value,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(payment)
    if payment.subscription_id is not None:
        subscription = scoped_get(db, StudentSubscription, org_id, payment.subscription_id)
        payment.plan_id = subscription.plan_id
    else:
        payment.plan_id = None
    return _attach_payment_financials(db, org_id, payment)


def mark_payment_paid(db: Session, org_id: UUID, payment_id: UUID, method: PaymentMethod, paid_at: datetime | None = None, actor_user_id: UUID | None = None) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    finance = payment_financials(db, org_id, payment)
    if payment.status in {PaymentStatus.CANCELLED, PaymentStatus.REFUNDED}:
        raise HTTPException(status_code=409, detail="This charge cannot be marked as paid")
    if finance["balance_minor"] <= 0:
        raise HTTPException(status_code=409, detail="Payment is already fully settled")
    return add_payment_receipt(
        db,
        org_id,
        payment_id,
        finance["balance_minor"],
        method,
        paid_at,
        "Full settlement",
        actor_user_id,
    )


def add_payment_adjustment(
    db: Session,
    org_id: UUID,
    payment_id: UUID,
    direction: str,
    amount_minor: int,
    reason: str,
    actor_user_id: UUID | None = None,
) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status == PaymentStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cancelled charge cannot be adjusted")
    _materialize_legacy_settlement(db, org_id, payment)
    finance = payment_financials(db, org_id, payment)
    if direction == "decrease" and amount_minor > finance["adjusted_amount_minor"]:
        raise HTTPException(status_code=422, detail="Adjustment exceeds charge amount")
    if direction == "decrease" and finance["adjusted_amount_minor"] - amount_minor < finance["net_paid_minor"]:
        raise HTTPException(status_code=422, detail="Refund the overpaid amount before decreasing the charge")

    kind = "adjustment_increase" if direction == "increase" else "adjustment_decrease"
    db.add(PaymentTransaction(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        kind=kind,
        amount_minor=amount_minor,
        note=reason,
        actor_user_id=actor_user_id,
    ))
    db.flush()
    finance = _sync_payment_state(db, org_id, payment)
    if payment.status != PaymentStatus.PAID:
        payment.paid_at = None
    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.adjusted",
        {
            "payment_id": str(payment.id),
            "direction": direction,
            "amount_minor": amount_minor,
            "balance_minor": finance["balance_minor"],
            "reason": reason,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(payment)
    if payment.subscription_id:
        payment.plan_id = scoped_get(db, StudentSubscription, org_id, payment.subscription_id).plan_id
    else:
        payment.plan_id = None
    return _attach_payment_financials(db, org_id, payment)


def refund_payment(
    db: Session,
    org_id: UUID,
    payment_id: UUID,
    amount_minor: int,
    note: str,
    occurred_at: datetime | None = None,
    reduce_charge: bool = True,
    actor_user_id: UUID | None = None,
) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status == PaymentStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cancelled charge cannot be refunded")
    _materialize_legacy_settlement(db, org_id, payment)
    finance = payment_financials(db, org_id, payment)
    if amount_minor > finance["net_paid_minor"]:
        raise HTTPException(status_code=422, detail="Refund exceeds net amount received")

    db.add(PaymentTransaction(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        kind="refund",
        amount_minor=amount_minor,
        note=note,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        actor_user_id=actor_user_id,
    ))
    if reduce_charge:
        db.add(PaymentTransaction(
            organization_id=org_id,
            payment_id=payment.id,
            student_id=payment.student_id,
            kind="adjustment_decrease",
            amount_minor=amount_minor,
            note=f"Refund adjustment: {note}",
            actor_user_id=actor_user_id,
        ))
    db.flush()
    finance = _sync_payment_state(db, org_id, payment)
    if finance["balance_minor"] > 0:
        payment.paid_at = None
    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.refunded",
        {
            "payment_id": str(payment.id),
            "amount_minor": amount_minor,
            "reduce_charge": reduce_charge,
            "balance_minor": finance["balance_minor"],
            "reason": note,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(payment)
    if payment.subscription_id:
        payment.plan_id = scoped_get(db, StudentSubscription, org_id, payment.subscription_id).plan_id
    else:
        payment.plan_id = None
    return _attach_payment_financials(db, org_id, payment)


def list_payment_transactions(db: Session, org_id: UUID, payment_id: UUID) -> list[PaymentTransaction]:
    scoped_get(db, Payment, org_id, payment_id)
    return _payment_transactions(db, org_id, payment_id)


def payment_summary(db: Session, org_id: UUID) -> dict:
    rows = list(db.scalars(select(Payment).where(Payment.organization_id == org_id)))
    today = date.today()
    paid_minor = 0
    pending_minor = 0
    overdue_minor = 0
    paid_count = 0
    pending_count = 0
    overdue_count = 0
    for row in rows:
        if row.status == PaymentStatus.CANCELLED:
            continue
        finance = payment_financials(db, org_id, row)
        paid_minor += finance["net_paid_minor"]
        if finance["balance_minor"] > 0:
            pending_minor += finance["balance_minor"]
            pending_count += 1
            if row.due_date is not None and row.due_date < today:
                overdue_minor += finance["balance_minor"]
                overdue_count += 1
        elif finance["adjusted_amount_minor"] > 0:
            paid_count += 1
    return {
        "paid_minor": paid_minor,
        "pending_minor": pending_minor,
        "overdue_minor": overdue_minor,
        "paid_count": paid_count,
        "pending_count": pending_count,
        "overdue_count": overdue_count,
    }


def cancel_payment(db: Session, org_id: UUID, payment_id: UUID, reason: str, actor_user_id: UUID | None = None) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    finance = payment_financials(db, org_id, payment)
    if payment.status != PaymentStatus.PENDING or finance["net_paid_minor"] > 0:
        raise HTTPException(status_code=409, detail="Only unpaid pending charges can be cancelled")

    payment.status = PaymentStatus.CANCELLED
    if payment.subscription_id is not None:
        subscription = scoped_get(db, StudentSubscription, org_id, payment.subscription_id)
        subscription.status = SubscriptionStatus.CANCELLED
        payment.plan_id = subscription.plan_id
    else:
        payment.plan_id = None

    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.cancelled",
        {"payment_id": str(payment.id), "reason": reason, "subscription_id": str(payment.subscription_id) if payment.subscription_id else None},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(payment)
    return _attach_payment_financials(db, org_id, payment)


def _payment_reminder_stage(due_date: date, today: date) -> tuple[str, str] | None:
    delta = (today - due_date).days
    if -3 <= delta <= -1:
        return "upcoming_3", "Оплата наближається"
    if delta == 0:
        return "due_today", "Оплата сьогодні"
    if 1 <= delta <= 2:
        return "overdue_1", "Прострочено"
    if 3 <= delta <= 6:
        return "overdue_3", "Прострочено 3+ дні"
    if 7 <= delta <= 13:
        return "overdue_7", "Прострочено 7+ днів"
    if 14 <= delta <= 29:
        return "overdue_14", "Прострочено 14+ днів"
    if delta >= 30:
        return "overdue_30", "Прострочено 30+ днів"
    return None


def payment_reminder_queue(db: Session, org_id: UUID) -> list[dict]:
    today = date.today()
    payments = list(db.scalars(
        select(Payment)
        .where(
            Payment.organization_id == org_id,
            Payment.status == PaymentStatus.PENDING,
            Payment.due_date.is_not(None),
        )
        .order_by(Payment.due_date, Payment.created_at)
    ))
    result = []
    for payment in payments:
        finance = payment_financials(db, org_id, payment)
        if finance["balance_minor"] <= 0:
            continue
        stage_info = _payment_reminder_stage(payment.due_date, today)
        if stage_info is None:
            continue
        stage, label = stage_info
        already_sent = db.scalar(select(PaymentReminder.id).where(
            PaymentReminder.organization_id == org_id,
            PaymentReminder.payment_id == payment.id,
            PaymentReminder.stage == stage,
        ))
        if already_sent is not None:
            continue
        student = scoped_get(db, Student, org_id, payment.student_id)
        contact = _primary_contact_for_student(db, org_id, student.id)
        last_reminder_at = db.scalar(select(func.max(PaymentReminder.sent_at)).where(
            PaymentReminder.organization_id == org_id,
            PaymentReminder.payment_id == payment.id,
        ))
        result.append({
            "payment_id": payment.id,
            "student_id": student.id,
            "student_name": " ".join(filter(None, [student.first_name, student.last_name])),
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "amount_minor": finance["balance_minor"],
            "currency": payment.currency,
            "due_date": payment.due_date,
            "days_from_due": (today - payment.due_date).days,
            "stage": stage,
            "label": label,
            "last_reminder_at": last_reminder_at,
        })
    return result


def mark_payment_reminder_sent(
    db: Session,
    org_id: UUID,
    payment_id: UUID,
    stage: str,
    channel: str,
    actor_user_id: UUID | None = None,
) -> PaymentReminder:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status != PaymentStatus.PENDING or payment.due_date is None:
        raise HTTPException(status_code=409, detail="Payment no longer needs a reminder")

    expected = _payment_reminder_stage(payment.due_date, date.today())
    if expected is None or expected[0] != stage:
        raise HTTPException(status_code=409, detail="Reminder stage is no longer current")

    existing = db.scalar(select(PaymentReminder).where(
        PaymentReminder.organization_id == org_id,
        PaymentReminder.payment_id == payment.id,
        PaymentReminder.stage == stage,
    ))
    if existing is not None:
        raise HTTPException(status_code=409, detail="This reminder stage was already recorded")

    item = PaymentReminder(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        stage=stage,
        channel=channel,
        created_by_user_id=actor_user_id,
    )
    db.add(item)
    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.reminder_sent",
        {"payment_id": str(payment.id), "stage": stage, "channel": channel},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(item)
    return item
