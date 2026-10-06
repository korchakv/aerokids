import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.core.config import settings
from app.db.migrate_database import run_migration_from_environment


logger = logging.getLogger("uvicorn.error")
is_production = settings.environment.lower() == "production"

migration_result = run_migration_from_environment(settings.database_url)
if migration_result is not None:
    total_rows = sum(item["rows"] for item in migration_result.values())
    logger.info(
        "Database migration verified: %s tables, %s rows",
        len(migration_result),
        total_rows,
    )

app = FastAPI(
    title="School CRM API",
    version="0.4.0",
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
    ],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    if settings.read_only_mode and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        return JSONResponse(
            status_code=503,
            content={"detail": "CRM is temporarily read-only during a database maintenance window."},
            headers={"Retry-After": "60", "Cache-Control": "no-store"},
        )

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


app.include_router(router)
