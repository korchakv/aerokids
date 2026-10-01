from fastapi import FastAPI

from app.db.base import Base
from app.db.session import engine
from app.models import core  # noqa: F401


app = FastAPI(title="School CRM API", version="0.1.0")


@app.on_event("startup")
def create_tables() -> None:
    # Temporary bootstrap for the first runnable slice.
    # Replace with Alembic migrations before the first shared environment.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
