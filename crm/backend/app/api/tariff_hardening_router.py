from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_db, get_org_access
from app.models.core import StudentSubscription, SubscriptionPlan
from app.models.hardening_extensions import SubscriptionRuleSnapshot
from app.schemas import (
    BillingRenewalResult,
    BillingRenewalRun,
    StudentSubscriptionCreate,
    StudentSubscriptionRead,
    SubscriptionChargeCreate,
    SubscriptionChargeResult,
    SubscriptionPlanChangeCreate,
    SubscriptionPlanChangeResult,
    SubscriptionPlanRead,
)
from app.services import billing_hardening, crm, hardening, tariff_hardening


router = APIRouter()


class HardenedPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    price_minor: int | None = Field(default=None, ge=0)
    period_days: int | None = Field(default=None, ge=1, le=366)
    lessons_included: int | None = Field(default=None, ge=1, le=365)
    usage_mode: Literal["attendance", "scheduled", "period"] | None = None
    absent_rule: Literal["consume", "dont_consume", "choice"] | None = None
    excused_rule: Literal["consume", "dont_consume", "makeup"] | None = None
    late_rule: Literal["consume", "dont_consume"] | None = None
    end_rule: Literal["lessons", "date", "whichever_first"] | None = None
    renewal_trigger: Literal["last_lesson", "date", "manual"] | None = None
    allow_debt: bool | None = None
    max_lates: int | None = Field(default=None, ge=1, le=100)
    makeup_expiry_days: int | None = Field(default=None, ge=1, le=366)
    is_active: bool | None = None


def _require_finance(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
    if not hardening.has_capability(db, access.organization_id, access.user_id, access.role, "finance.manage"):
        raise HTTPException(status_code=403, detail="Недостатньо прав для тарифів і нарахувань")
    return access


@router.put("/subscription-plans/{plan_id}", response_model=SubscriptionPlanRead)
def update_subscription_plan(
    plan_id: UUID,
    data: HardenedPlanUpdate,
    access: OrgAccess = Depends(_require_finance),
    db: Session = Depends(get_db),
):
    return tariff_hardening.update_plan(db, access.organization_id, plan_id, data, access.user_id)


@router.post("/student-subscriptions", response_model=StudentSubscriptionRead, status_code=201)
def create_student_subscription(
    data: StudentSubscriptionCreate,
    access: OrgAccess = Depends(_require_finance),
    db: Session = Depends(get_db),
):
    subscription = hardening.create_student_subscription_hardened(db, access.organization_id, data)
    plan = crm.scoped_get(db, SubscriptionPlan, access.organization_id, subscription.plan_id)
    tariff_hardening.create_snapshot(db, access.organization_id, subscription, plan)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.post("/billing/charges", response_model=SubscriptionChargeResult, status_code=201)
def create_subscription_charge(
    data: SubscriptionChargeCreate,
    access: OrgAccess = Depends(_require_finance),
    db: Session = Depends(get_db),
):
    subscription, payment = hardening.create_subscription_charge_hardened(
        db, access.organization_id, data, access.user_id,
    )
    plan = crm.scoped_get(db, SubscriptionPlan, access.organization_id, subscription.plan_id)
    tariff_hardening.create_snapshot(db, access.organization_id, subscription, plan)
    db.commit()
    db.refresh(subscription)
    db.refresh(payment)
    return SubscriptionChargeResult(subscription=subscription, payment=payment)


@router.post("/billing/renewals/run", response_model=BillingRenewalResult)
def run_renewals(
    data: BillingRenewalRun,
    access: OrgAccess = Depends(_require_finance),
    db: Session = Depends(get_db),
):
    result = billing_hardening.run_renewals(db, access.organization_id, data.through_date, access.user_id)
    tariff_hardening.ensure_missing_snapshots(db, access.organization_id)
    db.commit()
    return result


@router.post("/student-subscriptions/{subscription_id}/change-plan", response_model=SubscriptionPlanChangeResult)
def change_plan_now(
    subscription_id: UUID,
    data: SubscriptionPlanChangeCreate,
    access: OrgAccess = Depends(_require_finance),
    db: Session = Depends(get_db),
):
    result = crm.change_subscription_plan_now(
        db,
        access.organization_id,
        subscription_id,
        data.plan_id,
        data.reason,
        access.user_id,
    )
    subscription = crm.scoped_get(db, StudentSubscription, access.organization_id, subscription_id)
    plan = crm.scoped_get(db, SubscriptionPlan, access.organization_id, subscription.plan_id)
    snapshot = db.scalar(select(SubscriptionRuleSnapshot).where(
        SubscriptionRuleSnapshot.organization_id == access.organization_id,
        SubscriptionRuleSnapshot.subscription_id == subscription.id,
    ))
    if snapshot is None:
        snapshot = tariff_hardening.create_snapshot(db, access.organization_id, subscription, plan)
    else:
        for field in tariff_hardening.RULE_FIELDS:
            setattr(snapshot, field, getattr(plan, field))
    db.commit()
    return result
