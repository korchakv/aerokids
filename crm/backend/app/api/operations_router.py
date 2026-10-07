from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.jobs.daily_maintenance import run_daily_maintenance
from app.services.operations_auth import MaintenanceIdentityError, verify_github_actions_token


router = APIRouter(prefix="/internal/operations", tags=["internal-operations"])
logger = logging.getLogger("schoolcrm.operations")


def _authorize_maintenance(authorization: str | None, provided_secret: str | None) -> str:
    expected = settings.maintenance_secret
    if expected and provided_secret and hmac.compare_digest(provided_secret, expected):
        return "shared_secret"

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Maintenance identity required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Maintenance identity required")
    try:
        verify_github_actions_token(token)
    except MaintenanceIdentityError as exc:
        raise HTTPException(status_code=401, detail="Invalid maintenance identity") from exc
    return "github_oidc"


@router.post("/daily-maintenance")
def daily_maintenance(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_maintenance_secret: str | None = Header(default=None, alias="X-Maintenance-Secret"),
):
    if settings.read_only_mode:
        raise HTTPException(status_code=503, detail="CRM is in read-only maintenance mode")
    auth_method = _authorize_maintenance(authorization, x_maintenance_secret)

    logger.info("daily_maintenance_requested", extra={"auth_method": auth_method})
    result = run_daily_maintenance()
    organization_errors = [
        {
            "organization_id": row.get("organization_id"),
            "errors": row.get("errors", []),
        }
        for row in result.get("organizations", [])
        if row.get("errors")
    ]
    email_result = result.get("transactional_email") or {}
    if organization_errors or int(email_result.get("failed", 0) or 0) > 0:
        logger.error(
            "daily_maintenance_degraded organization_error_count=%s email_failed=%s",
            len(organization_errors),
            email_result.get("failed", 0),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "status": "degraded",
                "organization_errors": organization_errors,
                "transactional_email": email_result,
            },
        )

    logger.info(
        "daily_maintenance_complete organization_count=%s",
        len(result.get("organizations", [])),
    )
    return {"status": "ok", **result}
