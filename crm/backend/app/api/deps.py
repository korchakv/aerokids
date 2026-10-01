from collections.abc import Generator
from uuid import UUID

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_org_id(x_organization_id: str = Header(..., alias="X-Organization-Id")) -> UUID:
    try:
        return UUID(x_organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid X-Organization-Id") from exc
