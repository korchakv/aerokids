from datetime import datetime, timedelta, timezone
from uuid import UUID
import hashlib
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import AuthMembershipInfo, AuthUserInfo, BootstrapOwnerCreate
from app.core.security import create_access_token, hash_password, verify_password
from app.models.core import AuthLoginThrottle, Organization, OrganizationInvitation, OrganizationMembership, PasswordResetToken, Staff, StaffRole, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def enforce_login_rate_limit(
    db: Session,
    scope: str,
    fingerprint: str,
    limit: int,
    window_minutes: int,
) -> None:
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    row = db.scalar(
        select(AuthLoginThrottle)
        .where(
            AuthLoginThrottle.scope == scope,
            AuthLoginThrottle.fingerprint_hash == digest,
        )
        .with_for_update()
    )

    if row is None:
        db.add(AuthLoginThrottle(
            scope=scope,
            fingerprint_hash=digest,
            window_started_at=now,
            request_count=1,
            updated_at=now,
        ))
        db.commit()
        return

    window_started = row.window_started_at
    if window_started.tzinfo is None:
        window_started = window_started.replace(tzinfo=timezone.utc)

    if now - window_started >= timedelta(minutes=window_minutes):
        row.window_started_at = now
        row.request_count = 1
    else:
        if row.request_count >= limit:
            raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")
        row.request_count += 1

    row.updated_at = now
    db.commit()


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
            organization_timezone=organization.timezone,
            organization_currency=organization.currency,
            organization_locale=organization.locale,
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


def create_invitation(db: Session, org_id: UUID, invited_by_user_id: UUID, email: str, role: StaffRole):
    normalized = normalize_email(email)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invitation = OrganizationInvitation(
        organization_id=org_id,
        email=normalized,
        role=role,
        token_hash=token_hash,
        invited_by_user_id=invited_by_user_id,
        expires_at=expires_at,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation, raw_token


def invitation_status(db: Session, raw_token: str) -> str:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invitation = db.scalar(select(OrganizationInvitation).where(
        OrganizationInvitation.token_hash == token_hash,
    ))
    if invitation is None:
        return "invalid"
    if invitation.accepted_at is not None:
        return "accepted"

    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return "expired"
    return "valid"


def accept_invitation(db: Session, raw_token: str, full_name: str, password: str):
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.token_hash == token_hash)
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if invitation is None:
        raise HTTPException(status_code=400, detail="Invitation is invalid")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="This invitation has already been accepted")

    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise HTTPException(status_code=400, detail="Invitation has expired")

    user = db.scalar(select(User).where(User.email == invitation.email))
    if user is None:
        user = User(
            email=invitation.email,
            full_name=full_name,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
    else:
        if user.password_hash:
            if not verify_password(password, user.password_hash):
                raise HTTPException(status_code=409, detail="This email already has an account; use its existing password")
        else:
            user.password_hash = hash_password(password)
        if not user.full_name:
            user.full_name = full_name

    membership = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == invitation.organization_id,
        OrganizationMembership.user_id == user.id,
    ))
    if membership is None:
        membership = OrganizationMembership(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
        )
        db.add(membership)
    else:
        membership.role = invitation.role
        membership.is_active = True

    staff = db.scalar(select(Staff).where(
        Staff.organization_id == invitation.organization_id,
        Staff.email == invitation.email,
    ))
    if staff is None:
        staff = Staff(
            organization_id=invitation.organization_id,
            user_id=user.id,
            full_name=full_name,
            email=invitation.email,
            role=invitation.role,
        )
        db.add(staff)
    else:
        staff.user_id = user.id
        staff.role = invitation.role
        staff.is_active = True

    # Once this person joins the organization, every outstanding invitation
    # for the same organization/email becomes unusable as well.
    outstanding = list(db.scalars(select(OrganizationInvitation).where(
        OrganizationInvitation.organization_id == invitation.organization_id,
        OrganizationInvitation.email == invitation.email,
        OrganizationInvitation.accepted_at.is_(None),
    )))
    for item in outstanding:
        item.accepted_at = now

    db.commit()
    db.refresh(user)
    return user, create_access_token(user.id), auth_user_info(db, user)


def create_password_reset_link(
    db: Session,
    org_id: UUID,
    requested_by_user_id: UUID,
    requester_role: StaffRole,
    email: str,
):
    normalized = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    membership = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.user_id == user.id,
        OrganizationMembership.is_active.is_(True),
    ))
    if membership is None:
        raise HTTPException(status_code=404, detail="User is not a member of this organization")
    if membership.role == StaffRole.OWNER and requester_role != StaffRole.OWNER:
        raise HTTPException(status_code=403, detail="Only an owner can reset another owner's password")

    now = datetime.now(timezone.utc)
    active_tokens = list(db.scalars(select(PasswordResetToken).where(
        PasswordResetToken.organization_id == org_id,
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    )))
    for item in active_tokens:
        item.used_at = now

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = now + timedelta(hours=1)
    reset = PasswordResetToken(
        user_id=user.id,
        organization_id=org_id,
        token_hash=token_hash,
        created_by_user_id=requested_by_user_id,
        expires_at=expires_at,
    )
    db.add(reset)
    db.commit()
    db.refresh(reset)
    return user, reset, raw_token


def complete_password_reset(db: Session, raw_token: str, password: str):
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    reset = db.scalar(select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used_at.is_(None),
    ))
    now = datetime.now(timezone.utc)
    if reset is None:
        raise HTTPException(status_code=400, detail="Reset link is invalid or already used")

    expires_at = reset.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")

    user = get_user(db, reset.user_id)
    user.password_hash = hash_password(password)
    reset.used_at = now

    other_tokens = list(db.scalars(select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.id != reset.id,
    )))
    for item in other_tokens:
        item.used_at = now

    db.commit()
    db.refresh(user)
    return user, create_access_token(user.id), auth_user_info(db, user)
