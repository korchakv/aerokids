import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.audit_pagination_router import router as audit_pagination_router
from app.api.network_security_router import router as network_security_router
from app.api.operations_router import router as operations_router
from app.api.auth_hardening_router import router as auth_hardening_router
from app.api.tariff_hardening_router import router as tariff_hardening_router
from app.api.billing_hardening_router import router as billing_hardening_router
from app.api.enrollment_hardening_router import router as enrollment_hardening_router
from app.api.privacy_router import router as privacy_router
from app.api.reconciliation_router import router as reconciliation_router
from app.api.hardening_router import router as hardening_router
from app.api.router import router
from app.core.config import settings
from app.core.logging import configure_app_logging
from app.services import hardening, tariff_hardening


configure_app_logging()
logger = logging.getLogger("schoolcrm.http")
is_production = settings.environment.lower() == "production"

# One canonical subscription policy is shared by group and individual
# attendance. Existing subscriptions use frozen tariff-rule snapshots.
hardening._eligible_subscription = tariff_hardening.eligible_subscription
hardening._should_consume = tariff_hardening.should_consume


app = FastAPI(
    title="School CRM API",
    version="0.5.0",
    description="Multi-tenant CRM core for schools and clubs.",
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Organization-Id",
        "X-Bootstrap-Secret",
        "X-Request-Id",
    ],
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    if settings.read_only_mode and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        return JSONResponse(
            status_code=503,
            content={"detail": "CRM is temporarily read-only during a database maintenance window."},
            headers={"Retry-After": "60", "Cache-Control": "no-store"},
        )

    supplied_request_id = (request.headers.get("X-Request-Id") or "").strip()
    request_id = supplied_request_id[:128] if supplied_request_id else str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"request_id": request_id, "method": request.method, "path": request.url.path})
        raise

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": elapsed_ms,
        },
    )
    return response


# Most specific handlers go first, followed by the compatibility hardening
# overlay and then all untouched legacy routes.
app.include_router(operations_router)
app.include_router(audit_pagination_router)
app.include_router(network_security_router)
app.include_router(auth_hardening_router)
app.include_router(tariff_hardening_router)
app.include_router(billing_hardening_router)
app.include_router(enrollment_hardening_router)
app.include_router(privacy_router)
app.include_router(reconciliation_router)
app.include_router(hardening_router)
app.include_router(router)
