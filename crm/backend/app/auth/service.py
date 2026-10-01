from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import AuthMembershipInfo, AuthUserInfo, BootstrapOwnerCreate
from app.core.security import create_access_token, hash_password, verify_password
from app.models.core import Organization, OrganizationMembership, Staff, StaffRole, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def bootstrap_owner(db: Session, data: BootstrapOwnerCreate) -> tuple[Organization, User, str]:
    existing_org = db.scalar(select(Organization.id).limit(1))
    if existing_org is not None:
        raise HTTPException(status_code=409, detail="Bootstrap is only available for an empty CRM database")

    email = normalize_email(data.email)
    organization = Organization(name=data.organization_name, slug=data.organization_slug)
    user = User(
        email=email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
    )
    db.add_all([organization, user])
    db.flush()

    db.add(OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role=StaffRole.OWNER,
    ))
    db.add(Staff(
        organization_id=organization.id,
        user_id=user.id,
        full_name=data.full_name,
        email=email,
        role=StaffRole.OWNER,
    ))
    db.commit()
    db.refresh(organization)
    db.refresh(user)
    return organization, user, create_access_token(user.id)


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive or unavailable")
    return user


def auth_user_info(db: Session, user: User) -> AuthUserInfo:
    rows = db.execute(
        select(OrganizationMembership, Organization)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active.is_(True),
        )
        .order_by(Organization.name)
    ).all()
    memberships = [
        AuthMembershipInfo(
            organization_id=organization.id,
            organization_name=organization.name,
            organization_slug=organization.slug,
            role=membership.role,
        )
        for membership, organization in rows
    ]
    return AuthUserInfo(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        memberships=memberships,
    )


def issue_login_token(db: Session, email: str, password: str) -> tuple[str, AuthUserInfo]:
    user = authenticate_user(db, email, password)
    return create_access_token(user.id), auth_user_info(db, user)
