import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.hardening_router import router as hardening_router
from app.api.router import router
from app.core.config import settings


logger = logging.getLogger("schoolcrm.http")
is_production = settings.environment.lower() == "production"


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

    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
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
        "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


# Hardened routes are registered first so they become the canonical handlers
# for legacy paths while older endpoints remain available for non-overridden
# compatibility routes.
app.include_router(hardening_router)
app.include_router(router)
