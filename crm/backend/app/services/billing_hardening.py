from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import (
    Enrollment,
    EnrollmentStatus,
    Payment,
    PaymentStatus,
    PaymentTransaction,
    Student,
    StudentStatus,
    StudentSubscription,
    SubscriptionPause,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.models.hardening import IndividualLessonSession
from app.services import crm, hardening


def _payment_balance(db: Session, org_id: UUID, payment: Payment) -> int:
    return int(crm.payment_financials(db, org_id, payment)["balance_minor"])


def eligible_subscription(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    lesson_date: date,
    group_id: UUID | None,
):
    rows = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student_id,
        StudentSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED]),
        StudentSubscription.starts_on <= lesson_date,
    ).order_by(StudentSubscription.starts_on, StudentSubscription.created_at)))
    for subscription in rows:
        if group_id is None and subscription.group_id is not None:
            continue
        if group_id is not None and subscription.group_id is not None and subscription.group_id != group_id:
            continue
        plan = crm.scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
        if subscription.ends_on is not None and plan.end_rule in {"date", "whichever_first"} and lesson_date > subscription.ends_on:
            continue
        included = subscription.lessons_included if subscription.lessons_included is not None else plan.lessons_included
        if included is not None and hardening._subscription_used_units(db, org_id, subscription.id) >= included:
            continue
        if not plan.allow_debt:
            payment = db.scalar(select(Payment).where(
                Payment.organization_id == org_id,
                Payment.subscription_id == subscription.id,
                Payment.status != PaymentStatus.CANCELLED,
            ).order_by(Payment.created_at.desc()))
            if payment is None or _payment_balance(db, org_id, payment) > 0:
                continue
        return subscription, plan
    return None


def _next_start(db: Session, org_id: UUID, subscription: StudentSubscription, not_before: date) -> date:
    if subscription.group_id is not None:
        sessions = list(db.scalars(select(crm.LessonSession).where(
            crm.LessonSession.organization_id == org_id,
            crm.LessonSession.group_id == subscription.group_id,
            crm.LessonSession.status != crm.LessonStatus.CANCELLED,
        ).order_by(crm.LessonSession.starts_at)))
        for lesson in sessions:
            local_date = hardening._local_date(db, org_id, lesson.starts_at)
            if local_date >= not_before:
                return local_date
        return not_before

    sessions = list(db.scalars(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org_id,
        IndividualLessonSession.student_id == subscription.student_id,
        IndividualLessonSession.status != "cancelled",
    ).order_by(IndividualLessonSession.starts_at)))
    for lesson in sessions:
        local_date = hardening._local_date(db, org_id, lesson.starts_at)
        if local_date >= not_before:
            return local_date
    return not_before


def _has_learning_relationship(db: Session, org_id: UUID, subscription: StudentSubscription) -> bool:
    if subscription.group_id is None:
        return True
    return db.scalar(select(Enrollment.id).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == subscription.student_id,
        Enrollment.group_id == subscription.group_id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    )) is not None


def _open_pause(db: Session, org_id: UUID, subscription_id: UUID):
    return db.scalar(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.subscription_id == subscription_id,
        SubscriptionPause.resumed_at.is_(None),
    ).order_by(SubscriptionPause.created_at.desc()))


def _resume_due_pauses(db: Session, org_id: UUID, today: date, actor_user_id: UUID | None) -> int:
    rows = list(db.scalars(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.resumed_at.is_(None),
        SubscriptionPause.ends_on.is_not(None),
        SubscriptionPause.ends_on < today,
    )))
    resumed = 0
    for pause in rows:
        subscription = crm.scoped_get(db, StudentSubscription, org_id, pause.subscription_id)
        resume_on = pause.ends_on + timedelta(days=1)
        crm._finish_subscription_pause(db, org_id, subscription, pause, resume_on, actor_user_id, automatic=True)
        resumed += 1
    if resumed:
        db.flush()
    return resumed


def run_renewals(
    db: Session,
    org_id: UUID,
    through_date: date | None,
    actor_user_id: UUID | None,
) -> dict:
    organization = crm.require_organization(db, org_id)
    today = hardening.organization_today(db, org_id)
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
    for row in expired_rows:
        if _open_pause(db, org_id, row.id) is None:
            row.status = SubscriptionStatus.EXPIRED

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
            if _open_pause(db, org_id, current.id) is not None:
                break
            existing_child = db.scalar(select(StudentSubscription).where(
                StudentSubscription.organization_id == org_id,
                StudentSubscription.renewal_of_id == current.id,
                StudentSubscription.status != SubscriptionStatus.CANCELLED,
            ))
            if existing_child is not None:
                current = existing_child
                continue
            student = crm.scoped_get(db, Student, org_id, current.student_id)
            if student.student_status != StudentStatus.ACTIVE:
                break
            if not _has_learning_relationship(db, org_id, current):
                break
            plan = crm.scoped_get(db, SubscriptionPlan, org_id, current.plan_id)
            if not plan.is_active:
                break
            current_period_days = current.period_days or plan.period_days or 30
            if current.ends_on < today - timedelta(days=current_period_days):
                skipped_stale_subscriptions += 1
                break

            next_start = _next_start(db, org_id, current, current.ends_on + timedelta(days=1))
            credit_before = max(0, current.credit_minor)
            applied_credit = min(credit_before, plan.price_minor)
            carry_credit = max(0, credit_before - applied_credit)
            amount_due = max(0, plan.price_minor - applied_credit)
            child = StudentSubscription(
                organization_id=org_id,
                student_id=student.id,
                plan_id=plan.id,
                group_id=current.group_id,
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
                renewal_of_id=current.id,
            )
            db.add(child)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                # Another worker created the same renewal. The database unique
                # index is the final idempotency guard; continue from its row.
                existing_child = db.scalar(select(StudentSubscription).where(
                    StudentSubscription.organization_id == org_id,
                    StudentSubscription.renewal_of_id == current.id,
                    StudentSubscription.status != SubscriptionStatus.CANCELLED,
                ))
                if existing_child is None:
                    raise
                current = existing_child
                continue
            payment = Payment(
                organization_id=org_id,
                student_id=student.id,
                subscription_id=child.id,
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
            crm.record_audit(db, org_id, "student", student.id, "subscription.renewed_hardened", {
                "previous_subscription_id": str(current.id),
                "subscription_id": str(child.id),
                "payment_id": str(payment.id),
                "starts_on": next_start.isoformat(),
                "credit_applied_minor": applied_credit,
                "amount_due_minor": amount_due,
            }, actor_user_id)
            created_payment_ids.append(payment.id)
            created_subscriptions += 1
            current = child

    db.commit()
    return {
        "resumed_subscriptions": resumed,
        "created_subscriptions": created_subscriptions,
        "skipped_stale_subscriptions": skipped_stale_subscriptions,
        "created_payment_ids": created_payment_ids,
    }


def reminder_queue(db: Session, org_id: UUID) -> list[dict]:
    today = hardening.organization_today(db, org_id)
    payments = list(db.scalars(select(Payment).where(
        Payment.organization_id == org_id,
        Payment.status == PaymentStatus.PENDING,
        Payment.due_date.is_not(None),
    ).order_by(Payment.due_date, Payment.created_at)))
    result = []
    for payment in payments:
        finance = crm.payment_financials(db, org_id, payment)
        if finance["balance_minor"] <= 0:
            continue
        stage_info = crm._payment_reminder_stage(payment.due_date, today)
        if stage_info is None:
            continue
        stage, label = stage_info
        already_sent = db.scalar(select(crm.PaymentReminder.id).where(
            crm.PaymentReminder.organization_id == org_id,
            crm.PaymentReminder.payment_id == payment.id,
            crm.PaymentReminder.stage == stage,
        ))
        if already_sent is not None:
            continue
        student = crm.scoped_get(db, Student, org_id, payment.student_id)
        contact = crm._primary_contact_for_student(db, org_id, student.id)
        last_reminder_at = db.scalar(select(func.max(crm.PaymentReminder.sent_at)).where(
            crm.PaymentReminder.organization_id == org_id,
            crm.PaymentReminder.payment_id == payment.id,
        )) if False else None
        # Avoid an additional aggregate dependency here; the UI only needs the
        # current actionable stage. Legacy history remains available elsewhere.
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


def pause_subscription(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    starts_on: date,
    resume_on: date | None,
    note: str | None,
    actor_user_id: UUID | None,
):
    subscription = crm.scoped_get(db, StudentSubscription, org_id, subscription_id)
    if subscription.status in {SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED}:
        raise HTTPException(status_code=409, detail="Абонемент не можна поставити на паузу")
    if starts_on < subscription.starts_on or (subscription.ends_on is not None and starts_on > subscription.ends_on):
        raise HTTPException(status_code=422, detail="Пауза має починатися в межах поточного абонемента")
    if resume_on is not None and resume_on <= starts_on:
        raise HTTPException(status_code=422, detail="Дата повернення має бути після початку паузи")
    if _open_pause(db, org_id, subscription.id) is not None:
        raise HTTPException(status_code=409, detail="Абонемент уже має активну або заплановану паузу")
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
    today = hardening.organization_today(db, org_id)
    if starts_on <= today and (ends_on is None or today <= ends_on):
        subscription.status = SubscriptionStatus.PAUSED
    crm.record_audit(db, org_id, "student", subscription.student_id, "subscription.paused_hardened", {
        "subscription_id": str(subscription.id),
        "starts_on": starts_on.isoformat(),
        "resume_on": resume_on.isoformat() if resume_on else None,
    }, actor_user_id)
    db.commit()
    db.refresh(pause)
    return pause
