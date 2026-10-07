from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_db, get_org_access
from app.models.core import StaffRole, StudentSubscription
from app.schemas import (
    BillingRenewalResult,
    BillingRenewalRun,
    PaymentReminderCandidate,
    SubscriptionPauseCreate,
    SubscriptionPauseRead,
    SubscriptionResumeCreate,
    StudentSubscriptionRead,
)
from app.services import billing_hardening, crm, hardening


router = APIRouter()


def _require_finance(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
    if not hardening.has_capability(db, access.organization_id, access.user_id, access.role, "finance.manage"):
        raise HTTPException(status_code=403, detail="Недостатньо прав для фінансової дії")
    return access


def _require_finance_view(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
    if not hardening.has_capability(db, access.organization_id, access.user_id, access.role, "finance.view"):
        raise HTTPException(status_code=403, detail="Недостатньо прав для перегляду фінансів")
    return access


@router.post("/billing/renewals/run", response_model=BillingRenewalResult)
def run_billing_renewals(
    data: BillingRenewalRun,
    access: OrgAccess = Depends(_require_finance),
    db: Session = Depends(get_db),
):
    return billing_hardening.run_renewals(
        db,
        access.organization_id,
        data.through_date,
        access.user_id,
    )


@router.get("/payment-reminders", response_model=list[PaymentReminderCandidate])
def payment_reminders(
    access: OrgAccess = Depends(_require_finance_view),
    db: Session = Depends(get_db),
):
    return billing_hardening.reminder_queue(db, access.organization_id)


@router.post(
    "/student-subscriptions/{subscription_id}/pause",
    response_model=SubscriptionPauseRead,
    status_code=201,
)
def pause_subscription(
    subscription_id: UUID,
    data: SubscriptionPauseCreate,
    access: OrgAccess = Depends(_require_finance),
    db: Session = Depends(get_db),
):
    return billing_hardening.pause_subscription(
        db,
        access.organization_id,
        subscription_id,
        data.starts_on,
        data.resume_on,
        data.note,
        access.user_id,
    )


@router.post("/student-subscriptions/{subscription_id}/resume", response_model=StudentSubscriptionRead)
def resume_subscription(
    subscription_id: UUID,
    data: SubscriptionResumeCreate,
    access: OrgAccess = Depends(_require_finance),
    db: Session = Depends(get_db),
):
    subscription = crm.scoped_get(db, StudentSubscription, access.organization_id, subscription_id)
    resume_on = data.resumes_on or hardening.organization_today(db, access.organization_id)
    return crm.resume_subscription(
        db,
        access.organization_id,
        subscription.id,
        resume_on,
        access.user_id,
    )
