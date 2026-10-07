import type { ApiAuditEvent, Session } from "./types";
import { apiGet } from "./client";

export function loadAuditEvents(entityType: string, entityId: string, session: Session) {
  const query = new URLSearchParams({ entity_type: entityType, entity_id: entityId, limit: "100" });
  return apiGet<ApiAuditEvent[]>(`/audit-events?${query.toString()}`, session);
}
