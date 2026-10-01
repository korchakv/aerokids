from uuid import UUID

from pydantic import BaseModel, Field

from app.models.core import StaffRole


class BootstrapOwnerCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    organization_slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=2, max_length=100)
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=10, max_length=200)


class LoginCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class AuthMembershipInfo(BaseModel):
    organization_id: UUID
    organization_name: str
    organization_slug: str
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
