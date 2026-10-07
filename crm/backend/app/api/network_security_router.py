from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.auth import service as auth_service
from app.auth.schemas import AuthTokenResponse, LoginCreate
from app.core.config import settings
from app.models.core import Organization
from app.schemas import IntakeCreate, IntakeResult
from app.services import crm


router = APIRouter()


def trusted_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # A trusted reverse proxy appends the address it observed. Taking the
        # right-most value avoids trusting a client-supplied first hop.
        values = [part.strip() for part in forwarded.split(",") if part.strip()]
        if values:
            return values[-1]
    return request.client.host if request.client else "unknown"


@router.post("/auth/login", response_model=AuthTokenResponse)
def auth_login(data: LoginCreate, request: Request, db: Session = Depends(get_db)):
    client_ip = trusted_client_ip(request)
    auth_service.enforce_login_rate_limit(
        db,
        "ip",
        client_ip,
        settings.auth_login_ip_limit,
        settings.auth_login_window_minutes,
    )
    auth_service.enforce_login_rate_limit(
        db,
        "email",
        auth_service.normalize_email(data.email),
        settings.auth_login_email_limit,
        settings.auth_login_window_minutes,
    )
    token, user_info = auth_service.issue_login_token(db, data.email, data.password)
    return AuthTokenResponse(access_token=token, user=user_info)


@router.post("/public/intake/{organization_slug}", response_model=IntakeResult, status_code=201)
def public_intake(
    organization_slug: str,
    data: IntakeCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    organization = db.scalar(select(Organization).where(Organization.slug == organization_slug))
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if data.website:
        raise HTTPException(status_code=422, detail="Invalid form submission")

    client_ip = trusted_client_ip(request)
    normalized_phone = crm.normalize_phone(data.phone)
    crm.enforce_public_intake_rate_limit(
        db,
        organization.id,
        "ip",
        f"{organization.id}:{client_ip}",
        settings.public_intake_ip_limit,
        settings.public_intake_window_minutes,
    )
    crm.enforce_public_intake_rate_limit(
        db,
        organization.id,
        "phone",
        f"{organization.id}:{normalized_phone}",
        settings.public_intake_phone_limit,
        settings.public_intake_window_minutes,
    )
    student, contact = crm.create_intake(db, organization, data, record_repeat=True)
    return IntakeResult(student_id=student.id, contact_id=contact.id, crm_status=student.crm_status)
