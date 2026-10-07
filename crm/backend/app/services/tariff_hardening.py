from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Payment, PaymentStatus, StudentSubscription, SubscriptionPlan, SubscriptionStatus
from app.models.hardening_extensions import SubscriptionRuleSnapshot
from app.services import crm, hardening


RULE_FIELDS = (
    "usage_mode",
    "absent_rule",
    "excused_rule",
    "late_rule",
    "end_rule",
    "renewal_trigger",
    "allow_debt",
    "max_lates",
    "makeup_expiry_days",
)


def create_snapshot(db: Session, org_id: UUID, subscription: StudentSubscription, plan: SubscriptionPlan) -> SubscriptionRuleSnapshot:
    existing = db.scalar(select(SubscriptionRuleSnapshot).where(
        SubscriptionRuleSnapshot.organization_id == org_id,
        SubscriptionRuleSnapshot.subscription_id == subscription.id,
    ))
    if existing is not None:
        return existing
    row = SubscriptionRuleSnapshot(
        organization_id=org_id,
        subscription_id=subscription.id,
        **{field: getattr(plan, field) for field in RULE_FIELDS},
    )
    db.add(row)
    db.flush()
    return row


def ensure_missing_snapshots(db: Session, org_id: UUID, plan_id: UUID | None = None) -> int:
    stmt = select(StudentSubscription).where(StudentSubscription.organization_id == org_id)
    if plan_id is not None:
        stmt = stmt.where(StudentSubscription.plan_id == plan_id)
    subscriptions = list(db.scalars(stmt))
    created = 0
    for subscription in subscriptions:
        exists = db.scalar(select(SubscriptionRuleSnapshot.id).where(
            SubscriptionRuleSnapshot.organization_id == org_id,
            SubscriptionRuleSnapshot.subscription_id == subscription.id,
        ))
        if exists is not None:
            continue
        plan = crm.scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
        create_snapshot(db, org_id, subscription, plan)
        created += 1
    return created


def effective_plan(db: Session, org_id: UUID, subscription: StudentSubscription, plan: SubscriptionPlan | None = None):
    plan = plan or crm.scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
    snapshot = db.scalar(select(SubscriptionRuleSnapshot).where(
        SubscriptionRuleSnapshot.organization_id == org_id,
        SubscriptionRuleSnapshot.subscription_id == subscription.id,
    ))
    if snapshot is None:
        snapshot = create_snapshot(db, org_id, subscription, plan)
    values = {
        "id": plan.id,
        "organization_id": plan.organization_id,
        "name": plan.name,
        "price_minor": plan.price_minor,
        "period_days": plan.period_days,
        "lessons_included": plan.lessons_included,
        "is_active": plan.is_active,
    }
    values.update({field: getattr(snapshot, field) for field in RULE_FIELDS})
    return SimpleNamespace(**values)


def eligible_subscription(db: Session, org_id: UUID, student_id: UUID, lesson_date, group_id: UUID | None):
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
        template = crm.scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
        plan = effective_plan(db, org_id, subscription, template)
        if subscription.ends_on is not None and plan.end_rule in {"date", "whichever_first"} and lesson_date > subscription.ends_on:
            continue
        included = subscription.lessons_included if subscription.lessons_included is not None else template.lessons_included
        if included is not None and hardening._subscription_used_units(db, org_id, subscription.id) >= included:
            continue
        if not plan.allow_debt:
            payment = db.scalar(select(Payment).where(
                Payment.organization_id == org_id,
                Payment.subscription_id == subscription.id,
                Payment.status != PaymentStatus.CANCELLED,
            ).order_by(Payment.created_at.desc()))
            if payment is None or crm.payment_financials(db, org_id, payment)["balance_minor"] > 0:
                continue
        return subscription, plan
    return None


def should_consume(plan, status, explicit: bool | None) -> bool:
    from app.models.core import AttendanceStatus

    if plan.usage_mode == "period":
        return False
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


def update_plan(db: Session, org_id: UUID, plan_id: UUID, data, actor_user_id: UUID | None) -> SubscriptionPlan:
    plan = db.scalar(select(SubscriptionPlan).where(
        SubscriptionPlan.organization_id == org_id,
        SubscriptionPlan.id == plan_id,
    ).with_for_update())
    if plan is None:
        raise HTTPException(status_code=404, detail="Тариф не знайдено")

    # Freeze old rules before the template changes. Existing subscriptions must
    # never silently inherit a new absence/makeup/debt policy.
    ensure_missing_snapshots(db, org_id, plan.id)
    before = {field: getattr(plan, field) for field in (
        "name", "price_minor", "period_days", "lessons_included", *RULE_FIELDS, "is_active",
    )}
    payload = data.model_dump(exclude_unset=True)
    period_days = payload.get("period_days", plan.period_days)
    lessons_included = payload.get("lessons_included", plan.lessons_included)
    if period_days is None and lessons_included is None:
        raise HTTPException(status_code=422, detail="Вкажіть кількість днів, відвідувань або обидва значення")
    for key, value in payload.items():
        setattr(plan, key, value)
    after = {field: getattr(plan, field) for field in (
        "name", "price_minor", "period_days", "lessons_included", *RULE_FIELDS, "is_active",
    )}
    changed_fields = [key for key in before if before[key] != after[key]]
    crm.record_audit(db, org_id, "subscription_plan", plan.id, "subscription_plan.updated", {
        "changed_fields": changed_fields,
        "before": before,
        "after": after,
    }, actor_user_id)
    db.commit()
    db.refresh(plan)
    return plan
