from uuid import UUID
import re

from pydantic import BaseModel, Field, field_validator

from app.models.core import StaffRole


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", value):
        raise ValueError("Некоректна email-адреса")
    return value


def normalize_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    if len(value) < 2 or not re.fullmatch(r"[A-Za-zА-Яа-яІіЇїЄєҐґ'’\- ]+", value):
        raise ValueError("Ім’я може містити лише літери, пробіл, апостроф і дефіс")
    return value



class BootstrapOwnerCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    organization_slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=2, max_length=100)
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=10, max_length=200)

    _full_name = field_validator("full_name")(normalize_name)
    _email = field_validator("email")(normalize_email)


class LoginCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=200)

    _email = field_validator("email")(normalize_email)


class AuthMembershipInfo(BaseModel):
    organization_id: UUID
    organization_name: str
    organization_slug: str
    organization_timezone: str
    organization_currency: str
    organization_locale: str
    role: StaffRole


class AuthUserInfo(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    memberships: list[AuthMembershipInfo]


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserInfo


class BootstrapOwnerResult(BaseModel):
    organization_id: UUID
    user_id: UUID
    access_token: str
    token_type: str = "bearer"


class OrganizationInvitationCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    role: StaffRole

    _email = field_validator("email")(normalize_email)


class OrganizationInvitationResult(BaseModel):
    invitation_id: UUID
    email: str
    role: StaffRole
    invite_token: str
    expires_at: str


class AcceptInvitationCreate(BaseModel):
    invite_token: str = Field(min_length=20, max_length=300)
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=10, max_length=200)

    _full_name = field_validator("full_name")(normalize_name)


class BootstrapStatus(BaseModel):
    available: bool


class PasswordResetLinkCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)

    _email = field_validator("email")(normalize_email)


class PasswordResetLinkResult(BaseModel):
    email: str
    reset_token: str
    expires_at: str


class PasswordResetComplete(BaseModel):
    reset_token: str = Field(min_length=20, max_length=300)
    password: str = Field(min_length=10, max_length=200)
