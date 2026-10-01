from fastapi import FastAPI

from app.api.router import router


app = FastAPI(
    title="School CRM API",
    version="0.2.0",
    description="Multi-tenant CRM core for schools and clubs.",
)
app.include_router(router)
