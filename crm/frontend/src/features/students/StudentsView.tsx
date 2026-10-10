import { AuditHistory } from "../../components/AuditHistory";
import type { ApiAuditEvent } from "../../api";
import type { EntityId, Lead } from "../leads/model";
import type { GroupItem } from "../groups/types";

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
  onOpenStudent: (studentId: EntityId, currentGroupId: EntityId | null) => void;
};

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
        <div className="studentRow studentHead"><span>Учень</span><span>Група</span><span>Контакт</span><span>Статус</span></div>
        {loading && students.length === 0 && <div className="emptyState">Завантаження учнів…</div>}
        {!loading && students.length === 0 && <div className="emptyState">За цим фільтром учнів немає.</div>}
        {students.map((student) => {
          const group = groupForStudent(student.id);
          const groupName = student.groupName ?? group?.name;
          const groupId = student.groupId ?? group?.id ?? null;
          const state = studentStates[student.id] ?? "Активний";
          return <button className="studentRow studentButton" key={student.id} onClick={() => onOpenStudent(student.id, groupId)}>
            <span className="studentIdentity"><i>{student.child[0]}</i><b>{student.child}<small>{student.age} років</small></b></span>
            <span>{groupName ?? "Без групи"}</span>
            <span>{student.parent}<small>{student.phone}</small></span>
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

type StudentDrawerProps = {
  student: Lead | null;
  currentGroup: GroupItem | undefined;
  studentState: StudentLifecycleLabel;
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
        <div><h2>{student.child}</h2><p>{student.age} років · {studentState}</p></div>
      </div>
      <div className="studentInfoGrid">
        <div><span>Група</span><b>{currentGroup?.name ?? "Без групи"}</b><small>{currentGroup?.schedule ?? "Розклад не задано"}</small></div>
        <div><span>Локація</span><b>{currentGroup?.location ?? "Без локації"}</b></div>
      </div>
      <div className="contactCard"><span>Контакт</span><b>{student.parent}</b><a href={"tel:" + student.phone.replace(/\s/g, "")}>{student.phone}</a></div>

      {canManageStudents && <>
        <div className="studentSection">
          <h3>Статус учня</h3>
          <select
            className="transferSelect"
            aria-label="Статус учня"
            value={studentState}
            disabled={returningToWaiting}
            onChange={(event) => {
              const value = event.target.value;
              if (value === "return_to_work") {
                onReturnToWaiting();
                return;
              }
              onLifecycleChange(value as StudentLifecycleLabel);
            }}
          >
            <option value="Активний">Активний</option>
            <option value="Пауза">Пауза</option>
            <option value="Архів">Архів</option>
            <option value="return_to_work">Повернути в роботу</option>
          </select>
          <small>«Повернути в роботу» переведе учня в «Очікує групу».</small>
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
