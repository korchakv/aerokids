import type { ApiAuditEvent } from "../api";

type AuditHistoryProps = {
  title: string;
  events: ApiAuditEvent[];
  loading: boolean;
  labelForEvent: (eventType: string) => string;
  detailForEvent: (event: ApiAuditEvent) => string;
};

export function AuditHistory({ title, events, loading, labelForEvent, detailForEvent }: AuditHistoryProps) {
  return <div className="history">
    <h3>{title}</h3>
    {loading && <div className="historyEmpty">Завантажуємо історію…</div>}
    {!loading && events.length === 0 && <div className="historyEmpty">Подій поки немає.</div>}
    {!loading && events.map((event) => <div key={event.id}>
      <i></i>
      <p>
        <b>{labelForEvent(event.event_type)}</b>
        <span>{detailForEvent(event)} · {new Date(event.created_at).toLocaleString("uk-UA")}{event.actor_name ? " · " + event.actor_name : ""}</span>
      </p>
    </div>)}
  </div>;
}
