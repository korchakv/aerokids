from collections.abc import Callable, Generator
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.core.security import auth_is_required, decode_access_token
from app.db.session import SessionLocal
from app.models.core import OrganizationMembership, StaffRole, User


bearer_scheme = HTTPBearer(auto_error=False)


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
    return auth_service.get_user(db, user_id)


def _membership_for_token(
    db: Session,
    org_id: UUID,
    credentials: HTTPAuthorizationCredentials,
) -> OrganizationMembership:
    user_id = decode_access_token(credentials.credentials)
    auth_service.get_user(db, user_id)
    membership = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.is_active.is_(True),
    ))
    if membership is None:
        raise HTTPException(status_code=403, detail="No access to this organization")
    return membership


def get_org_id(
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UUID:
    org_id = parse_org_id(x_organization_id)
    if credentials is None:
        if auth_is_required():
            raise HTTPException(status_code=401, detail="Authentication required")
        return org_id
    _membership_for_token(db, org_id, credentials)
    return org_id


def require_org_roles(*roles: StaffRole) -> Callable:
    def dependency(
        x_organization_id: str = Header(..., alias="X-Organization-Id"),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        db: Session = Depends(get_db),
    ) -> UUID:
        org_id = parse_org_id(x_organization_id)
        if credentials is None:
            if auth_is_required():
                raise HTTPException(status_code=401, detail="Authentication required")
            return org_id

        membership = _membership_for_token(db, org_id, credentials)
        if membership.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role for this action")
        return org_id

    return dependency
