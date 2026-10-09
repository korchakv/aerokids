from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_org_roles
from app.models.core import StaffRole
from app.schemas import AuditEventRead
from app.services import audit_service


router = APIRouter()


class AuditEventPage(BaseModel):
    items: list[AuditEventRead]
    total: int
    limit: int
    offset: int


@router.get("/audit-events/page", response_model=AuditEventPage)
def audit_events_page(
    q: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    event_type: str | None = None,
    actor_user_id: UUID | None = None,
    sort: str = Query(default="newest", pattern="^(newest|oldest)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return audit_service.paginate_audit_events(
        db,
        org_id,
        q=q,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )
