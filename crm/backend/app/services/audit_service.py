from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.core import AuditEvent, User


def record_audit(
    db: Session,
    org_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    event_type: str,
    payload: dict | None = None,
    actor_user_id: UUID | None = None,
) -> AuditEvent:
    item = AuditEvent(
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(item)
    return item


def list_audit_events(
    db: Session,
    org_id: UUID,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: int = 100,
) -> list[dict]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == org_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)

    events = list(db.scalars(stmt.order_by(AuditEvent.created_at.desc()).limit(limit)))
    users: dict[UUID, User] = {}
    user_ids = {event.actor_user_id for event in events if event.actor_user_id is not None}
    if user_ids:
        users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids)))}

    return [{
        "id": event.id,
        "organization_id": event.organization_id,
        "actor_user_id": event.actor_user_id,
        "actor_name": users.get(event.actor_user_id).full_name if event.actor_user_id in users else None,
        "actor_email": users.get(event.actor_user_id).email if event.actor_user_id in users else None,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": event.created_at,
    } for event in events]

def paginate_audit_events(
    db: Session,
    org_id: UUID,
    *,
    q: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    event_type: str | None = None,
    actor_user_id: UUID | None = None,
    sort: str = "newest",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return a tenant-scoped, database-backed audit page.

    The legacy list endpoint remains available for bounded entity history in
    detail drawers. This page endpoint is intended for organization-wide audit
    browsing without loading the full audit table into application memory.
    """
    filters = [AuditEvent.organization_id == org_id]
    if entity_type:
        filters.append(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        filters.append(AuditEvent.entity_id == entity_id)
    if event_type:
        filters.append(AuditEvent.event_type == event_type)
    if actor_user_id is not None:
        filters.append(AuditEvent.actor_user_id == actor_user_id)

    needle = (q or "").strip()
    if needle:
        pattern = f"%{needle}%"
        filters.append(or_(
            AuditEvent.entity_type.ilike(pattern),
            AuditEvent.event_type.ilike(pattern),
            User.full_name.ilike(pattern),
            User.email.ilike(pattern),
        ))

    joined = (
        select(
            AuditEvent,
            User.full_name.label("actor_name"),
            User.email.label("actor_email"),
        )
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(*filters)
    )
    total = int(db.scalar(
        select(func.count(AuditEvent.id))
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(*filters)
    ) or 0)

    if sort == "oldest":
        joined = joined.order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    else:
        joined = joined.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())

    rows = db.execute(joined.offset(offset).limit(limit)).all()
    items = [{
        "id": row[0].id,
        "organization_id": row[0].organization_id,
        "actor_user_id": row[0].actor_user_id,
        "actor_name": row.actor_name,
        "actor_email": row.actor_email,
        "entity_type": row[0].entity_type,
        "entity_id": row[0].entity_id,
        "event_type": row[0].event_type,
        "payload": row[0].payload,
        "created_at": row[0].created_at,
    } for row in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}

