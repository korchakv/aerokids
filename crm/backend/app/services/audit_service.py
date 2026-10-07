from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
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
