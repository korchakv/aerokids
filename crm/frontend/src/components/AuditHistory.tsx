import type { ApiAuditEvent } from "../api";

type AuditHistoryProps = {
  title: string;
  events: ApiAuditEvent[];
  loading: boolean;
  labelForEvent: (eventType: string) => string;
  detailForEvent: (event: ApiAuditEvent) => string;
};

type ChangeRow = { label: string; value: string };

function formatTrialDate(value: unknown) {
  if (typeof value !== "string") return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("uk-UA", {
    weekday: "long",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).replace(/^./, (character) => character.toLocaleUpperCase("uk-UA"));
}

function changesForEvent(event: ApiAuditEvent): ChangeRow[] {
  if (event.event_type !== "trial.rescheduled") return [];
  const payload = event.payload ?? {};
  const before = payload["before"];
  const after = payload["after"];
  if (!before || typeof before !== "object" || !after || typeof after !== "object") return [];

  const previous = before as Record<string, unknown>;
  const next = after as Record<string, unknown>;
  const fields = Array.isArray(payload["changed_fields"])
    ? payload["changed_fields"].filter((field): field is string => typeof field === "string")
    : ["starts_at", "location_name"].filter((field) => previous[field] !== next[field]);

  const rows: ChangeRow[] = [];
  if (fields.includes("starts_at") && previous["starts_at"] !== next["starts_at"]) {
    rows.push({ label: "Дата і час", value: `${formatTrialDate(previous["starts_at"])} → ${formatTrialDate(next["starts_at"])}` });
  }
  if (fields.includes("location_name") && previous["location_name"] !== next["location_name"]) {
    rows.push({ label: "Локація", value: `${typeof previous["location_name"] === "string" ? previous["location_name"] : "Без локації"} → ${typeof next["location_name"] === "string" ? next["location_name"] : "Без локації"}` });
  }
  return rows;
}

export function AuditHistory({ title, events, loading, labelForEvent, detailForEvent }: AuditHistoryProps) {
  return <div className="history">
    <h3>{title}</h3>
    {loading && <div className="historyEmpty">Завантажуємо історію…</div>}
    {!loading && events.length === 0 && <div className="historyEmpty">Подій поки немає.</div>}
    {!loading && events.map((event) => {
      const changes = changesForEvent(event);
      return <div className="historyItem" key={event.id}>
        <i></i>
        <div className="historyItemContent">
          <b>{labelForEvent(event.event_type)}</b>
          <span>{detailForEvent(event)} · {new Date(event.created_at).toLocaleString("uk-UA")}{event.actor_name ? " · " + event.actor_name : ""}</span>
          {changes.length > 0 && <details className="historyChange">
            <summary>Показати зміни</summary>
            <ul>{changes.map((change) => <li key={change.label}><b>{change.label}:</b> {change.value}</li>)}</ul>
          </details>}
        </div>
      </div>;
    })}
  </div>;
}
