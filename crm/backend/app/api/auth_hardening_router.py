from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_current_user, get_db, get_org_access
from app.auth import service as auth_service
from app.auth.schemas import (
    OrganizationInvitationCreate,
    OrganizationInvitationResult,
    PasswordResetLinkCreate,
    PasswordResetLinkResult,
)
from app.models.core import StaffRole, User
from app.services import crm, hardening, notifications


router = APIRouter()


def _require_staff_management(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
    if not hardening.has_capability(db, access.organization_id, access.user_id, access.role, "staff.manage"):
        raise HTTPException(status_code=403, detail="Недостатньо прав для керування доступом працівників")
    return access


@router.post("/organization-invitations", response_model=OrganizationInvitationResult, status_code=201)
def create_invitation(
    data: OrganizationInvitationCreate,
    access: OrgAccess = Depends(_require_staff_management),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.role == StaffRole.OWNER and access.role != StaffRole.OWNER:
        raise HTTPException(status_code=403, detail="Лише власник може запросити іншого власника")
    invitation, raw_token = auth_service.create_invitation(
        db,
        access.organization_id,
        user.id,
        data.email,
        data.role,
        data.can_teach,
    )
    organization = crm.require_organization(db, access.organization_id)
    notifications.enqueue_invitation(db, organization.id, invitation.email, raw_token, organization.name)
    crm.record_audit(db, organization.id, "organization_invitation", invitation.id, "staff.invitation_created", {
        "email": invitation.email,
        "role": invitation.role.value,
        "can_teach": invitation.can_teach,
    }, access.user_id)
    db.commit()
    return OrganizationInvitationResult(
        invitation_id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        can_teach=invitation.can_teach,
        invite_token=raw_token,
        expires_at=invitation.expires_at.isoformat(),
    )


@router.post("/password-reset-links", response_model=PasswordResetLinkResult, status_code=201)
def create_password_reset_link(
    data: PasswordResetLinkCreate,
    access: OrgAccess = Depends(_require_staff_management),
    db: Session = Depends(get_db),
):
    user, reset, raw_token = auth_service.create_password_reset_link(
        db,
        access.organization_id,
        access.user_id,
        access.role,
        data.email,
    )
    organization = crm.require_organization(db, access.organization_id)
    notifications.enqueue_password_reset(db, organization.id, user.email, raw_token, organization.name)
    crm.record_audit(db, organization.id, "user", user.id, "auth.password_reset_link_created", {
        "email": user.email,
        "reset_id": str(reset.id),
    }, access.user_id)
    db.commit()
    return PasswordResetLinkResult(
        email=user.email,
        reset_token=raw_token,
        expires_at=reset.expires_at.isoformat(),
    )
