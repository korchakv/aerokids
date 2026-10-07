import { useState } from "react";
import { formatUaPhone } from "../../utils/contact";
import { dateValue } from "../../utils/date";
import { leadActionMeta, leadDisplayStatus, leadKanbanColumn, leadKanbanColumns, leadMissingDetails, leadNextAction, leadSourceLabel, leadUrgency, type EntityId, type Lead, type LeadKanbanColumnId } from "./model";

export function LeadKanban({
  leads,
  onOpen,
  onMove,
  movingId,
}: {
  leads: Lead[];
  onOpen: (id: EntityId) => void;
  onMove: (lead: Lead, target: LeadKanbanColumnId) => void;
  movingId: EntityId | null;
}) {
  const [draggedId, setDraggedId] = useState<EntityId | null>(null);
  const [overColumn, setOverColumn] = useState<LeadKanbanColumnId | null>(null);
  const [deferredExpanded, setDeferredExpanded] = useState(false);
  const [closedExpanded, setClosedExpanded] = useState(false);
  const activeColumns = leadKanbanColumns.filter((column) => column.id !== "closed" && column.id !== "deferred");
  const deferredColumn = leadKanbanColumns.find((column) => column.id === "deferred")!;
  const closedColumn = leadKanbanColumns.find((column) => column.id === "closed")!;
  const deferredItems = leads.filter((lead) => leadKanbanColumn(lead) === "deferred").sort((a, b) => dateValue(a.deferredUntil) - dateValue(b.deferredUntil));
  const closedItems = leads.filter((lead) => leadKanbanColumn(lead) === "closed");

  const renderColumn = (column: (typeof leadKanbanColumns)[number], items: Lead[], compact = false) => <section
    className={"kanbanColumn column-" + column.id + (compact ? " closedKanbanColumn" : "") + (overColumn === column.id ? " dragOver" : "")}
    key={column.id}
    onDragOver={(event) => { event.preventDefault(); setOverColumn(column.id); }}
    onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOverColumn(null); }}
    onDrop={(event) => {
      event.preventDefault();
      const id = event.dataTransfer.getData("text/lead-id") || draggedId;
      const lead = leads.find((item) => item.id === id);
      setDraggedId(null);
      setOverColumn(null);
      if (lead) void onMove(lead, column.id);
    }}
  >
    <header className="kanbanColumnHead">
      <div><i></i><b>{column.title}</b><span>{column.hint}</span></div>
      <strong>{items.length}</strong>
    </header>
    <div className="kanbanCards">
      {items.length === 0 && <div className="kanbanEmpty">Перетягніть сюди заявку</div>}
      {items.map((lead) => {
        const urgency = leadUrgency(lead);
        const missingDetails = leadMissingDetails(lead);
        return <article
          key={lead.id}
          draggable={movingId !== lead.id}
          className={"leadKanbanCard urgency-" + urgency + (movingId === lead.id ? " saving" : "")}
          onDragStart={(event) => {
            setDraggedId(lead.id);
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/lead-id", lead.id);
          }}
          onDragEnd={() => { setDraggedId(null); setOverColumn(null); }}
          onClick={() => onOpen(lead.id)}
        >
          <div className="kanbanCardTop">
            <span className="leadMiniAvatar">{lead.child.slice(0, 1)}</span>
            <div><b>{lead.child}</b><small>{lead.age ? lead.age + " років" : "Вік не вказано"}</small></div>
            <button className="kanbanMore" aria-label="Відкрити заявку" onClick={(event) => { event.stopPropagation(); onOpen(lead.id); }}>•••</button>
          </div>
          <div className="kanbanMeta">
            <span className="sourceBadge">{leadSourceLabel(lead.source)}</span>
            {lead.preferredLocationName && <span className="locationBadge">{lead.preferredLocationName}</span>}
            {lead.recommendedLevel && <span className="levelBadge">{lead.recommendedLevel}</span>}
            {missingDetails.length > 0 && <span className="incompleteDataBadge" title={"Не заповнено: " + missingDetails.join(", ")}>! Доповнити дані</span>}
          </div>
          {(() => { const action = leadActionMeta(lead); return <div className={"kanbanNextAction action-" + action.type + " " + urgency}><i>{urgency === "overdue" ? "!" : action.icon}</i><span><b>{urgency === "overdue" ? "Прострочено" : action.label}</b><small>{leadNextAction(lead)}</small></span></div>; })()}
          {(lead.parent || lead.phone) && <div className="kanbanContact">
            {lead.parent && <b>{lead.parent}</b>}
            {lead.phone && <small>{formatUaPhone(lead.phone)}</small>}
          </div>}
          {movingId === lead.id && <div className="kanbanSaving">Оновлюємо…</div>}
        </article>;
      })}
    </div>
  </section>;

  return <div className="kanbanBoard">
    <div className="leadKanban">{activeColumns.map((column) => renderColumn(column, leads.filter((lead) => leadKanbanColumn(lead) === column.id)))}</div>
    <div
      className={"closedKanbanDock deferredKanbanDock " + (deferredExpanded ? "expanded " : "") + (overColumn === "deferred" ? "dragOver" : "")}
      onDragOver={(event) => { event.preventDefault(); setOverColumn("deferred"); }}
      onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOverColumn(null); }}
      onDrop={(event) => {
        event.preventDefault();
        const id = event.dataTransfer.getData("text/lead-id") || draggedId;
        const lead = leads.find((item) => item.id === id);
        setDraggedId(null);
        setOverColumn(null);
        if (lead) void onMove(lead, "deferred");
      }}
    >
      <button className="closedKanbanToggle" onClick={() => setDeferredExpanded((value) => !value)}>
        <span><i></i><b>{deferredColumn.title}</b><small>{deferredColumn.hint}</small></span>
        <span><strong>{deferredItems.length}</strong><em>{deferredExpanded ? "Згорнути ↑" : "Розгорнути ↓"}</em></span>
      </button>
      {deferredExpanded && <div className="closedKanbanContent">{renderColumn(deferredColumn, deferredItems, true)}</div>}
    </div>
    <div
      className={"closedKanbanDock " + (closedExpanded ? "expanded " : "") + (overColumn === "closed" ? "dragOver" : "")}
      onDragOver={(event) => { event.preventDefault(); setOverColumn("closed"); }}
      onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOverColumn(null); }}
      onDrop={(event) => {
        event.preventDefault();
        const id = event.dataTransfer.getData("text/lead-id") || draggedId;
        const lead = leads.find((item) => item.id === id);
        setDraggedId(null);
        setOverColumn(null);
        if (lead) void onMove(lead, "closed");
      }}
    >
      <button className="closedKanbanToggle" onClick={() => setClosedExpanded((value) => !value)}>
        <span><i></i><b>{closedColumn.title}</b><small>{closedColumn.hint}</small></span>
        <span><strong>{closedItems.length}</strong><em>{closedExpanded ? "Згорнути ↑" : "Розгорнути ↓"}</em></span>
      </button>
      {closedExpanded && <div className="closedKanbanContent">{renderColumn(closedColumn, closedItems, true)}</div>}
    </div>
  </div>;
}

export function LeadTable({ leads, onOpen }: { leads: Lead[]; onOpen: (id: EntityId) => void }) {
  return <div className="table leadTable">
    <div className="row tableHead"><span>Дитина</span><span>Вік</span><span>Батьки</span><span>Джерело</span><span>Статус</span><span>Наступна дія</span></div>
    {leads.length === 0 && <div className="emptyState">За цим фільтром заявок немає.</div>}
    {leads.map((lead) => <button className="row rowButton" key={lead.id} onClick={() => onOpen(lead.id)}>
      <b>{lead.child}</b><span>{lead.age}</span><span>{lead.parent}</span><span>{leadSourceLabel(lead.source)}</span><span className="pill">{leadDisplayStatus(lead)}</span>{(() => { const action = leadActionMeta(lead); const overdue = Boolean(lead.nextContactAt && dateValue(lead.nextContactAt) < Date.now()); return <span className={"nextAction actionTag action-" + action.type + (overdue ? " overdue" : "")}><i>{overdue ? "!" : action.icon}</i><span>{leadNextAction(lead)}</span></span>; })()}
    </button>)}
  </div>;
}

