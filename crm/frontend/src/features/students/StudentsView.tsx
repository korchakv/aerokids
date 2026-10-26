import { useState } from "react";
import { cleanSpaces, personNameError, uaPhoneError, normalizeUaPhone, formatUaPhone } from "../../utils/contact";
import { AuditHistory } from "../../components/AuditHistory";
import type { ApiAuditEvent } from "../../api";
import type { EntityId, Lead } from "../leads/model";
import type { GroupItem } from "../groups/types";
import type { WorkspaceStudent } from "../../api";

export type StudentLifecycleLabel = "Активний" | "Пауза" | "Архів";
export type StudentFilter = "all" | "active" | "paused" | "archived";

type StudentsViewProps = {
  students: Lead[];
  totalStudents: number;
  groupedStudents: number;
  pausedStudents: number;
  groupCount: number;
  studentFilter: StudentFilter;
  onFilterChange: (filter: StudentFilter) => void;
  query: string;
  onQueryChange: (value: string) => void;
  pageTotal: number;
  pageLimit: number;
  pageOffset: number;
  loading: boolean;
  error: string;
  onPreviousPage: () => void;
  onNextPage: () => void;
  studentStates: Record<EntityId, StudentLifecycleLabel>;
  groupForStudent: (studentId: EntityId) => GroupItem | undefined;
  studentBilling: Record<EntityId, WorkspaceStudent["billing"]>;
  showBilling: boolean;
  onOpenStudent: (studentId: EntityId, currentGroupId: EntityId | null) => void;
};

function formatBillingDate(value: string | null | undefined) {
  if (!value) return "Не заплановано";
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "Не заплановано";
  return new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "short", year: "numeric" })
    .format(new Date(year, month - 1, day));
}

export function StudentsView({
  students,
  totalStudents,
  groupedStudents,
  pausedStudents,
  groupCount,
  studentFilter,
  onFilterChange,
  query,
  onQueryChange,
  pageTotal,
  pageLimit,
  pageOffset,
  loading,
  error,
  onPreviousPage,
  onNextPage,
  studentStates,
  groupForStudent,
  studentBilling,
  showBilling,
  onOpenStudent,
}: StudentsViewProps) {
  return <section className="studentsLayout" data-testid="students-workspace">
    <article className="panel studentsPanel">
      <div className="panelHead">
        <div><p className="eyebrow">База учнів</p><h2>Активні учні</h2></div>
        <div className="registryToolbar">
          <label className="registrySearch"><span>Пошук</span><input value={query} onChange={(e) => onQueryChange(e.target.value)} placeholder="Ім’я або телефон" /></label>
          <div className="filters">
          <button className={"chip " + (studentFilter === "all" ? "active" : "")} onClick={() => onFilterChange("all")}>Усі</button>
          <button className={"chip " + (studentFilter === "active" ? "active" : "")} onClick={() => onFilterChange("active")}>Активні</button>
          <button className={"chip " + (studentFilter === "paused" ? "active" : "")} onClick={() => onFilterChange("paused")}>Пауза</button>
          <button className={"chip " + (studentFilter === "archived" ? "active" : "")} onClick={() => onFilterChange("archived")}>Архів</button>
          </div>
        </div>
      </div>
      {error && <div className="registryError" role="alert">{error}</div>}
      <div className={"studentTable " + (loading ? "registryLoading" : "")}>
        <div className={"studentRow studentHead " + (showBilling ? "hasBilling" : "")}><span>Учень</span><span>Група</span><span>Контакт</span>{showBilling && <span>Заняття й оплата</span>}<span>Статус</span></div>
        {loading && students.length === 0 && <div className="emptyState">Завантаження учнів…</div>}
        {!loading && students.length === 0 && <div className="emptyState">За цим фільтром учнів немає.</div>}
        {students.map((student) => {
          const group = groupForStudent(student.id);
          const groupName = student.groupName ?? group?.name;
          const groupId = student.groupId ?? group?.id ?? null;
          const state = studentStates[student.id] ?? "Активний";
          const billing = studentBilling[student.id];
          const lessonsLabel = billing?.lessons_included == null ? "Абонемент не задано" : `Абонемент: ${billing.lessons_included} занять`;
          const paidLabel = billing?.paid_lessons == null
            ? "Оплачено: немає даних"
            : `Оплачено: ${billing.paid_lessons} із ${billing.lessons_included ?? billing.paid_lessons}`;
          const usedLabel = billing?.lessons_used == null ? "Відвідано: —" : `Відвідано: ${billing.lessons_used}`;
          return <button className={"studentRow studentButton " + (showBilling ? "hasBilling" : "")} key={student.id} onClick={() => onOpenStudent(student.id, groupId)}>
            <span className="studentIdentity"><i>{student.child[0]}</i><b>{student.child}<small>{student.age} років</small></b></span>
            <span>{groupName ?? "Без групи"}</span>
            <span>{student.parent}<small>{student.phone}</small></span>
            {showBilling && <span className="studentBillingCell"><b>{paidLabel}</b><small>{usedLabel} · {lessonsLabel}</small><small>Наступна оплата: {formatBillingDate(billing?.next_due_date)}</small></span>}
            <span className={"studentState " + state.toLowerCase()}>{state}</span>
          </button>;
        })}
      </div>
      <div className="registryPager" aria-label="Сторінки учнів">
        <span>{pageTotal === 0 ? "0" : `${pageOffset + 1}–${Math.min(pageOffset + pageLimit, pageTotal)}`} з {pageTotal}</span>
        <div><button disabled={loading || pageOffset === 0} onClick={onPreviousPage}>← Назад</button><button disabled={loading || pageOffset + pageLimit >= pageTotal} onClick={onNextPage}>Далі →</button></div>
      </div>
    </article>
    <aside className="studentSummary panel">
      <p className="eyebrow">Огляд</p><h2>{totalStudents} учнів</h2>
      <div className="summaryMetric"><span>У групах</span><strong>{groupedStudents}</strong></div>
      <div className="summaryMetric"><span>На паузі</span><strong>{pausedStudents}</strong></div>
      <div className="summaryMetric"><span>Груп</span><strong>{groupCount}</strong></div>
    </aside>
  </section>;
}

function StudentDetailsEditor({ student, onSave }: { student: Lead; onSave: (student: Lead) => Promise<void> }) {
  const [draft, setDraft] = useState<Lead | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const begin = () => {
    const parts = student.child.trim().split(/\s+/);
    setDraft({ ...student, firstName: student.firstName ?? parts[0], lastName: student.lastName ?? parts.slice(1).join(" "), parent: student.parent === "Контакт не вказано" ? "" : student.parent });
    setError(""); setSaved(false);
  };
  if (!draft) return <div className="studentSection">
    <button className="search full" type="button" onClick={begin}>Редагувати дані</button>
    {saved && <p role="status">Дані дитини та батьків збережено.</p>}
  </div>;
  const change = (value: Partial<Lead>) => setDraft({ ...draft, ...value });
  return <form className="leadEditPanel" aria-label="Редагування даних учня" onSubmit={async (event) => {
    event.preventDefault();
    if (saving) return;
    const validation = personNameError(draft.firstName ?? "", "Ім’я дитини")
      || (draft.lastName?.trim() ? personNameError(draft.lastName, "Прізвище дитини") : "")
      || personNameError(draft.parent, "Ім’я одного з батьків")
      || uaPhoneError(draft.phone) || uaPhoneError(draft.childPhone ?? "", false)
      || (!Number.isInteger(draft.age) || draft.age < 3 || draft.age > 25 ? "Вік дитини має бути від 3 до 25 років." : "");
    if (validation) { setError(validation); return; }
    const firstName = cleanSpaces(draft.firstName ?? "");
    const lastName = cleanSpaces(draft.lastName ?? "");
    setSaving(true); setError("");
    try {
      await onSave({ ...draft, firstName, lastName, child: [firstName, lastName].filter(Boolean).join(" "), parent: cleanSpaces(draft.parent), phone: formatUaPhone(normalizeUaPhone(draft.phone)!), childPhone: draft.childPhone?.trim() ? formatUaPhone(normalizeUaPhone(draft.childPhone)!) : undefined });
      setDraft(null); setSaved(true);
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося зберегти дані. Спробуйте ще раз."); }
    finally { setSaving(false); }
  }}>
    <h3>Дані дитини та батьків</h3>
    <fieldset disabled={saving} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <div className="formTwo">
        <label>Ім’я дитини<input autoFocus required maxLength={120} value={draft.firstName ?? ""} onChange={e => change({ firstName: e.target.value })} /></label>
        <label>Прізвище дитини<input maxLength={120} value={draft.lastName ?? ""} onChange={e => change({ lastName: e.target.value })} /></label>
      </div>
      <div className="formTwo">
        <label>Вік<input required type="number" min={3} max={25} step={1} value={draft.age || ""} onChange={e => change({ age: Number(e.target.value) })} /></label>
        <label>Телефон дитини (необов’язково)<input type="tel" value={draft.childPhone ?? ""} onChange={e => change({ childPhone: e.target.value })} /></label>
      </div>
      <label>Ім’я одного з батьків / опікуна<input required maxLength={160} value={draft.parent} onChange={e => change({ parent: e.target.value })} /></label>
      <label>Телефон батьків<input required type="tel" value={draft.phone} onChange={e => change({ phone: e.target.value })} /></label>
      {error && <p role="alert">{error}</p>}
      <button className="primary full" type="submit">{saving ? "Зберігаємо…" : "Зберегти зміни"}</button>
      <button className="search full" type="button" onClick={() => setDraft(null)}>Скасувати</button>
    </fieldset>
  </form>;
}

type StudentDrawerProps = {
  student: Lead | null;
  currentGroup: GroupItem | undefined;
  studentState: StudentLifecycleLabel;
  onSaveDetails: (student: Lead) => Promise<void>;
  canManageStudents: boolean;
  canDeleteStudents: boolean;
  transferGroupId: EntityId | null;
  groups: GroupItem[];
  deleting: boolean;
  apiEnabled: boolean;
  auditEvents: ApiAuditEvent[];
  historyLoading: boolean;
  onClose: () => void;
  onLifecycleChange: (state: StudentLifecycleLabel) => void;
  onTransferGroupChange: (groupId: EntityId | null) => void;
  onTransfer: () => void;
  onReturnToWaiting: () => void;
  returningToWaiting: boolean;
  onDelete: () => void;
  auditEventLabel: (type: string) => string;
  auditEventDetail: (event: ApiAuditEvent) => string;
};

export function StudentDrawer({
  student,
  currentGroup,
  studentState,
  canManageStudents,
  onSaveDetails,
  canDeleteStudents,
  transferGroupId,
  groups,
  deleting,
  apiEnabled,
  auditEvents,
  historyLoading,
  onClose,
  onLifecycleChange,
  onTransferGroupChange,
  onTransfer,
  onReturnToWaiting,
  returningToWaiting,
  onDelete,
  auditEventLabel,
  auditEventDetail,
}: StudentDrawerProps) {
  if (!student) return null;

  return <div className="drawerBackdrop" onClick={onClose}>
    <aside className="drawer studentDrawer" onClick={(e) => e.stopPropagation()} data-testid="student-drawer">
      <button className="drawerClose" onClick={onClose}>×</button>
      <p className="eyebrow">Картка учня</p>
      <div className="studentHero">
        <span>{student.child[0]}</span>
        <div><h2>{student.child}</h2><p>{student.age} років · {student.status === "Очікує групу" ? "Очікує групу" : studentState}</p></div>
      </div>
      <div className="studentInfoGrid">
        <div><span>Група</span><b>{currentGroup?.name ?? "Без групи"}</b><small>{currentGroup?.schedule ?? "Розклад не задано"}</small></div>
        <div><span>Локація</span><b>{currentGroup?.location ?? "Без локації"}</b></div>
      </div>
      <div className="contactCard"><span>Контакт</span><b>{student.parent}</b><a href={"tel:" + student.phone.replace(/\s/g, "")}>{student.phone}</a></div>

      {canManageStudents && <StudentDetailsEditor key={student.id} student={student} onSave={onSaveDetails} />}

      {canManageStudents && <>
        <div className="studentSection">
          <h3>Статус учня</h3>
          <select
            className="transferSelect"
            aria-label="Статус учня"
            value={student.status === "Очікує групу" ? "waiting_for_group" : studentState}
            disabled={returningToWaiting}
            onChange={(event) => {
              const value = event.target.value;
              if (value === "return_to_work") {
                onReturnToWaiting();
                return;
              }
              if (value === "waiting_for_group") return;
              onLifecycleChange(value as StudentLifecycleLabel);
            }}
          >
            <option value="Активний">Активний</option>
            <option value="Пауза">Пауза</option>
            <option value="Архів">Архів</option>
            {student.status === "Очікує групу" && <option value="waiting_for_group">Очікує групу</option>}
            <option value="return_to_work">Повернути в роботу</option>
          </select>
          <small>«Повернути в роботу» переводить учня в очікування групи та прибирає з бази зарахованих.</small>
        </div>

        <div className="studentSection">
          <h3>{currentGroup ? "Перевести в іншу групу" : "Додати до групи"}</h3>
          <select className="transferSelect" value={transferGroupId ?? ""} onChange={(e) => onTransferGroupChange(e.target.value || null)}>
            <option value="">Оберіть групу</option>
            {groups.map((group) => <option value={group.id} key={group.id}>{group.name} · {group.members.length}/{group.capacity}</option>)}
          </select>
          <button className="primary full" disabled={transferGroupId === null || transferGroupId === currentGroup?.id} onClick={onTransfer}>{currentGroup ? "Перевести учня" : "Додати учня до групи"}</button>
        </div>
      </>}

      {canDeleteStudents && <div className="recordDangerZone">
        <span>Службова дія</span>
        <button className="subtleDangerAction" type="button" disabled={deleting} onClick={onDelete}>{deleting ? "Видаляємо…" : "Видалити учня"}</button>
      </div>}

      {apiEnabled
        ? <AuditHistory title="Історія учня" events={auditEvents} loading={historyLoading} labelForEvent={auditEventLabel} detailForEvent={auditEventDetail} />
        : <div className="history">
          <h3>Історія учня</h3>
          <div><i></i><p><b>Пробне заняття</b><span>{student.recommendedLevel ?? "Рівень не вказано"}</span></p></div>
          <div><i></i><p><b>Зараховано</b><span>{currentGroup?.name ?? "Групу не вказано"}</span></p></div>
        </div>}
    </aside>
  </div>;
}
