from collections.abc import Callable, Generator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.core.config import settings
from app.core.security import auth_is_required, decode_access_token, validate_access_token_credential
from app.db.session import SessionLocal
from app.models.core import OrganizationMembership, StaffRole, User


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class OrgAccess:
    organization_id: UUID
    user_id: UUID | None
    role: StaffRole


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_org_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid X-Organization-Id") from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = decode_access_token(credentials.credentials)
    user = auth_service.get_user(db, user_id)
    validate_access_token_credential(credentials.credentials, user.password_hash)
    return user


def _membership_for_token(
    db: Session,
    org_id: UUID,
    credentials: HTTPAuthorizationCredentials,
) -> tuple[OrganizationMembership, UUID]:
    user_id = decode_access_token(credentials.credentials)
    user = auth_service.get_user(db, user_id)
    validate_access_token_credential(credentials.credentials, user.password_hash)
    membership = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.is_active.is_(True),
    ))
    if membership is None:
        raise HTTPException(status_code=403, detail="No access to this organization")
    return membership, user_id


def get_org_access(
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> OrgAccess:
    org_id = parse_org_id(x_organization_id)
    if credentials is None:
        if auth_is_required():
            raise HTTPException(status_code=401, detail="Authentication required")
        return OrgAccess(organization_id=org_id, user_id=None, role=StaffRole.OWNER)

    membership, user_id = _membership_for_token(db, org_id, credentials)
    return OrgAccess(organization_id=org_id, user_id=user_id, role=membership.role)


def get_org_id(access: OrgAccess = Depends(get_org_access)) -> UUID:
    return access.organization_id


def role_is_allowed(actual_role: StaffRole, allowed_roles: tuple[StaffRole, ...]) -> bool:
    if actual_role in allowed_roles:
        return True
    # Backward-compatible only for local development. Production forces strict
    # RBAC in Settings.validate_production_settings().
    if not settings.strict_rbac and actual_role in {StaffRole.MANAGER, StaffRole.TEACHER} and StaffRole.ADMIN in allowed_roles:
        return True
    return False


def require_org_roles(*roles: StaffRole) -> Callable:
    def dependency(access: OrgAccess = Depends(get_org_access)) -> UUID:
        if not role_is_allowed(access.role, roles):
            raise HTTPException(status_code=403, detail="Insufficient role for this action")
        return access.organization_id

    return dependency


def require_org_access_roles(*roles: StaffRole) -> Callable:
    def dependency(access: OrgAccess = Depends(get_org_access)) -> OrgAccess:
        if not role_is_allowed(access.role, roles):
            raise HTTPException(status_code=403, detail="Insufficient role for this action")
        return access

    return dependency
