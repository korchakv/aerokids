from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.jobs.daily_maintenance import run_daily_maintenance


router = APIRouter(prefix="/internal/operations", tags=["internal-operations"])
logger = logging.getLogger("schoolcrm.operations")


def _require_maintenance_secret(provided: str | None) -> None:
    expected = settings.maintenance_secret
    if not expected:
        raise HTTPException(status_code=503, detail="Scheduled maintenance is not configured")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid maintenance credential")


@router.post("/daily-maintenance")
def daily_maintenance(
    x_maintenance_secret: str | None = Header(default=None, alias="X-Maintenance-Secret"),
):
    if settings.read_only_mode:
        raise HTTPException(status_code=503, detail="CRM is in read-only maintenance mode")
    _require_maintenance_secret(x_maintenance_secret)

    logger.info("daily_maintenance_requested")
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
