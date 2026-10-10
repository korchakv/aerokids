import type { Dispatch, SetStateAction } from "react";
import { AuditHistory } from "../../components/AuditHistory";
import { AvailabilityWindowEditor, DateTimeEditor, type AvailabilityWindowDraft } from "../../components/ScheduleEditors";
import { UiIcon } from "../../components/UiIcon";
import type { ApiAuditEvent } from "../../api";
import { dateValue } from "../../utils/date";
import { formatUaPhone } from "../../utils/contact";
import { availabilityLabel } from "./availability";
import {
  leadActionMeta,
  leadDisplayStatus,
  leadIsDeferred,
  leadKanbanColumn,
  leadPrimaryActionLabel,
  leadSourceLabel,
  type EntityId,
  type Lead,
  type LeadKanbanColumnId,
  type LeadStatus,
} from "./model";
import type { GroupItem } from "../groups/types";
import type { LocationDemo } from "../locations/types";

type Setter<T> = Dispatch<SetStateAction<T>>;
type MaybePromise = void | Promise<void>;

export type LeadDrawerProps = {
  selected: Lead;
  selectedMissingDetails: string[];
  canManageLeads: boolean;
  canDeleteStudents: boolean;
  apiEnabled: boolean;
  leadEditing: boolean;
  leadEditFirstName: string;
  leadEditLastName: string;
  leadEditAge: number;
  leadEditChildPhone: string;
  leadEditContactName: string;
  leadEditPhone: string;
  leadEditSource: string;
  leadEditComment: string;
  leadEditSaving: boolean;
  preferenceMode: boolean;
  preferenceLocationId: EntityId | "";
  availabilityWindows: AvailabilityWindowDraft[];
  preferenceSaving: boolean;
  activeLocations: LocationDemo[];
  trialMode: "schedule" | "complete" | null;
  trialAt: string;
  trialLocationId: EntityId | "";
  recommendedLevel: string;
  teacherNotes: string;
  leadProcedureTarget: LeadKanbanColumnId | null;
  leadEnrollmentOpen: boolean;
  postTrialMode: "thinking" | "defer" | "close" | null;
  followUpAt: string;
  deferAt: string;
  deferReason: string;
  deferNote: string;
  closeKind: "declined" | "no_response" | "not_relevant";
  closeReason: string;
  closeNote: string;
  leadEnrollmentGroupId: EntityId | "";
  leadEnrollmentSaving: boolean;
  groups: GroupItem[];
  locations: LocationDemo[];
  leadActionsOpen: boolean;
  leadStatusMenuOpen: boolean;
  leadDeleteSaving: boolean;
  entityEvents: ApiAuditEvent[];
  historyLoading: boolean;
  statuses: LeadStatus[];
  setSelectedId: Setter<EntityId | null>;
  setLeadEditing: Setter<boolean>;
  setLeadActionsOpen: Setter<boolean>;
  setLeadStatusMenuOpen: Setter<boolean>;
  setLeadEditFirstName: Setter<string>;
  setLeadEditLastName: Setter<string>;
  setLeadEditAge: Setter<number>;
  setLeadEditChildPhone: Setter<string>;
  setLeadEditContactName: Setter<string>;
  setLeadEditPhone: Setter<string>;
  setLeadEditSource: Setter<string>;
  setLeadEditComment: Setter<string>;
  setPreferenceMode: Setter<boolean>;
  setPreferenceLocationId: Setter<EntityId | "">;
  setAvailabilityWindows: Setter<AvailabilityWindowDraft[]>;
  setTrialMode: Setter<"schedule" | "complete" | null>;
  setTrialAt: Setter<string>;
  setTrialLocationId: Setter<EntityId | "">;
  setTrialLocation: Setter<string>;
  setRecommendedLevel: Setter<string>;
  setTeacherNotes: Setter<string>;
  setLeadProcedureTarget: Setter<LeadKanbanColumnId | null>;
  setLeadEnrollmentOpen: Setter<boolean>;
  setPostTrialMode: Setter<"thinking" | "defer" | "close" | null>;
  setFollowUpAt: Setter<string>;
  setDeferAt: Setter<string>;
  setDeferReason: Setter<string>;
  setDeferNote: Setter<string>;
  setCloseKind: Setter<"declined" | "no_response" | "not_relevant">;
  setCloseReason: Setter<string>;
  setCloseNote: Setter<string>;
  setLeadEnrollmentGroupId: Setter<EntityId | "">;
  setWorkspaceError: Setter<string>;
  beginLeadEdit: () => MaybePromise;
  saveLeadDetails: () => MaybePromise;
  updateStatus: (id: EntityId, status: LeadStatus) => MaybePromise;
  reopenLead: () => MaybePromise;
  saveStudentPreferences: () => MaybePromise;
  scheduleTrial: () => MaybePromise;
  completeTrial: (result: "completed" | "no_show" | "cancelled") => MaybePromise;
  saveLeadOutcome: (crmStatus: "contacted" | "trial_completed" | "waiting_for_group" | "declined" | "no_response" | "not_relevant", options?: { nextContactAt?: string; closeReason?: string; closeNote?: string }) => MaybePromise;
  openGroupCreation: (context: "groups" | "candidates" | "lead") => MaybePromise;
  enrollLeadDirectly: () => MaybePromise;
  enrollLeadWithoutGroup: () => MaybePromise;
  saveThinkingFollowUp: () => MaybePromise;
  setDeferredMonths: (months: number) => MaybePromise;
  saveDeferredLead: () => MaybePromise;
  resumeDeferredLead: () => MaybePromise;
  closeLead: () => MaybePromise;
  beginLeadDefer: () => MaybePromise;
  beginLeadClose: () => MaybePromise;
  handleLeadPrimaryAction: () => MaybePromise;
  beginTrialScheduling: () => MaybePromise;
  beginTrialResult: () => MaybePromise;
  beginLeadFollowUp: () => MaybePromise;
  beginLeadEnrollment: () => MaybePromise;
  setLeadMobileStatus: (status: "Нова" | "Зв'язались" | "Очікує групу") => MaybePromise;
  deleteSelectedLead: () => MaybePromise;
  deferReasonLabel: (reason: string | null | undefined) => string;
  closeReasonLabel: (reason: string | null | undefined) => string;
  auditEventLabel: (type: string) => string;
  auditEventDetail: (event: ApiAuditEvent) => string;
};

export function LeadDrawer(props: LeadDrawerProps) {
  const {
    selected,
    selectedMissingDetails,
    canManageLeads,
    canDeleteStudents,
    apiEnabled,
    leadEditing,
    leadEditFirstName,
    leadEditLastName,
    leadEditAge,
    leadEditChildPhone,
    leadEditContactName,
    leadEditPhone,
    leadEditSource,
    leadEditComment,
    leadEditSaving,
    preferenceMode,
    preferenceLocationId,
    availabilityWindows,
    preferenceSaving,
    activeLocations,
    trialMode,
    trialAt,
    trialLocationId,
    recommendedLevel,
    teacherNotes,
    leadProcedureTarget,
    leadEnrollmentOpen,
    postTrialMode,
    followUpAt,
    deferAt,
    deferReason,
    deferNote,
    closeKind,
    closeReason,
    closeNote,
    leadEnrollmentGroupId,
    leadEnrollmentSaving,
    groups,
    locations,
    leadActionsOpen,
    leadStatusMenuOpen,
    leadDeleteSaving,
    entityEvents,
    historyLoading,
    statuses,
    setSelectedId,
    setLeadEditing,
    setLeadActionsOpen,
    setLeadStatusMenuOpen,
    setLeadEditFirstName,
    setLeadEditLastName,
    setLeadEditAge,
    setLeadEditChildPhone,
    setLeadEditContactName,
    setLeadEditPhone,
    setLeadEditSource,
    setLeadEditComment,
    setPreferenceMode,
    setPreferenceLocationId,
    setAvailabilityWindows,
    setTrialMode,
    setTrialAt,
    setTrialLocationId,
    setTrialLocation,
    setRecommendedLevel,
    setTeacherNotes,
    setLeadProcedureTarget,
    setLeadEnrollmentOpen,
    setPostTrialMode,
    setFollowUpAt,
    setDeferAt,
    setDeferReason,
    setDeferNote,
    setCloseKind,
    setCloseReason,
    setCloseNote,
    setLeadEnrollmentGroupId,
    setWorkspaceError,
    beginLeadEdit,
    saveLeadDetails,
    updateStatus,
    reopenLead,
    saveStudentPreferences,
    scheduleTrial,
    completeTrial,
    saveLeadOutcome,
    openGroupCreation,
    enrollLeadDirectly,
    enrollLeadWithoutGroup,
    saveThinkingFollowUp,
    setDeferredMonths,
    saveDeferredLead,
    resumeDeferredLead,
    closeLead,
    beginLeadDefer,
    beginLeadClose,
    handleLeadPrimaryAction,
    beginTrialScheduling,
    beginTrialResult,
    beginLeadFollowUp,
    beginLeadEnrollment,
    setLeadMobileStatus,
    deleteSelectedLead,
    deferReasonLabel,
    closeReasonLabel,
    auditEventLabel,
    auditEventDetail
  } = props;

  return <div className="drawerBackdrop leadDrawerBackdrop" onClick={() => { setSelectedId(null); setLeadEditing(false); setLeadActionsOpen(false); setLeadStatusMenuOpen(false); setLeadEnrollmentOpen(false); }}>
        <aside className="drawer leadDrawer" data-testid="lead-drawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" aria-label="Закрити картку заявки" onClick={() => { setSelectedId(null); setLeadEditing(false); setLeadActionsOpen(false); setLeadStatusMenuOpen(false); setLeadEnrollmentOpen(false); }}>×</button>
          <p className="eyebrow">Картка заявки</p>
          <div className="leadDrawerTitleRow">
            <div className="leadDrawerIdentity">
              <h2>{selected.child}, {selected.age} років</h2>
              {canManageLeads && <button className="leadEditIcon" type="button" aria-label="Редагувати заявку" title="Редагувати заявку" onClick={beginLeadEdit}><UiIcon name="edit" size={14} /></button>}
            </div>
            <button className={"mobileLeadStatusTrigger stage-" + leadKanbanColumn(selected)} onClick={() => { setLeadActionsOpen(false); setLeadStatusMenuOpen(true); }}>
              <span>{leadDisplayStatus(selected)}</span><i>⌄</i>
            </button>
          </div>
          {leadEditing && <div className="leadEditPanel">
            <div className="leadEditPanelHead">
              <div><b>Редагування заявки</b><small>Основні дані дитини, контакт та коментар.</small></div>
              <button type="button" aria-label="Закрити редагування" onClick={() => setLeadEditing(false)}><UiIcon name="x" size={15} /></button>
            </div>
            <div className="formTwo">
              <label>Ім’я дитини<input autoFocus value={leadEditFirstName} onChange={(e) => setLeadEditFirstName(e.target.value)} /></label>
              <label>Прізвище дитини <small>(необов’язково)</small><input value={leadEditLastName} onChange={(e) => setLeadEditLastName(e.target.value)} /></label>
            </div>
            <div className="formTwo">
              <label>Вік<input type="number" min={3} max={25} value={leadEditAge} onChange={(e) => setLeadEditAge(Number(e.target.value))} /></label>
              <label>Телефон дитини <small>(необов’язково)</small><input inputMode="tel" value={leadEditChildPhone} onChange={(e) => setLeadEditChildPhone(e.target.value)} placeholder="+380…" /></label>
            </div>
            <label>Відповідальна особа<input value={leadEditContactName} onChange={(e) => setLeadEditContactName(e.target.value)} /></label>
            <label>Телефон<input inputMode="tel" value={leadEditPhone} onChange={(e) => setLeadEditPhone(e.target.value)} placeholder="+380…" /></label>
            <label>Джерело<select value={leadEditSource} onChange={(e) => setLeadEditSource(e.target.value)}>
              <option value="phone">Телефон</option>
              <option value="website">Сайт</option>
              <option value="instagram">Instagram</option>
              <option value="recommendation">Рекомендація</option>
              <option value="walk-in">Зайшли особисто</option>
              <option value="facebook">Facebook</option>
              <option value="tiktok">TikTok</option>
              <option value="google">Google</option>
              <option value="maps">Google Maps</option>
              <option value="other">Інше</option>
            </select></label>
            <label>Коментар<textarea value={leadEditComment} onChange={(e) => setLeadEditComment(e.target.value)} placeholder="Додайте примітку про запит, побажання або домовленості…" /></label>
            <div className="leadEditActions">
              <button className="search" type="button" disabled={leadEditSaving} onClick={() => setLeadEditing(false)}>Скасувати</button>
              <button className="primary" type="button" disabled={leadEditSaving || !leadEditFirstName.trim() || !leadEditContactName.trim() || !leadEditPhone.trim()} onClick={saveLeadDetails}>{leadEditSaving ? "Зберігаємо…" : "Зберегти зміни"}</button>
            </div>
          </div>}
          <div className="contactCard"><span>Контакт</span><b>{selected.parent}</b><a href={"tel:" + selected.phone.replace(/\s/g, "")}>{selected.phone}</a></div>
          <div className="desktopLeadStatus">
            {["Пробне заплановано","Після пробного","Відмовились","Не відповідає","Неактуально","Зарахований"].includes(selected.status) || ["no_show","cancelled"].includes(selected.trialResult ?? "")
              ? <div className="statusField statusReadonly">Статус<strong>{leadDisplayStatus(selected)}</strong></div>
              : <label className="statusField">Статус
                  <select value={selected.status} onChange={(e) => updateStatus(selected.id, e.target.value as LeadStatus)}>
                    {statuses.filter((status) => ["Нова","Зв'язались","Очікує групу"].includes(status)).map((status) => <option key={status}>{status}</option>)}
                  </select>
                </label>}
          </div>
          <div className="detailGrid"><span>Джерело<b>{leadSourceLabel(selected.source)}</b></span><span>Вік<b>{selected.age}</b></span></div>
          {selectedMissingDetails.length > 0 && <div className="leadCompletenessNotice">
            <div><span className="leadCompletenessIcon">!</span><p><b>Картку варто доповнити</b><small>Не заповнено: {selectedMissingDetails.join(", ")}.</small></p></div>
            {canManageLeads && <button type="button" onClick={beginLeadEdit}>Доповнити</button>}
          </div>}
          {selected.nextContactAt && (() => { const action = leadActionMeta(selected); const overdue = dateValue(selected.nextContactAt) < Date.now(); return <div className={"noteBox followUpBox actionReminder " + action.type + (overdue ? " overdue" : "")}><span className="actionReminderLabel"><i>{overdue ? "!" : action.icon}</i>{overdue ? "Прострочений контакт" : action.label}</span><p>{new Date(selected.nextContactAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</p>{canManageLeads && <button type="button" className="inlineEditLink" onClick={beginLeadFollowUp}>Змінити нагадування</button>}</div>; })()}
          {["Відмовились","Не відповідає","Неактуально"].includes(selected.status) && <div className="noteBox closedLeadBox"><span>Заявку закрито</span><p><b>{selected.status}</b>{selected.closeReason ? " · " + closeReasonLabel(selected.closeReason) : ""}</p>{selected.closeNote && <p>{selected.closeNote}</p>}{canManageLeads && <button type="button" className="inlineEditLink" onClick={beginLeadClose}>Редагувати причину та коментар</button>}<button className="search reopenLead" onClick={reopenLead}>Повернути в роботу</button></div>}
          <div className={"noteBox leadCommentBox" + (!selected.comment ? " empty" : "")}><span>Коментар</span><p>{selected.comment || "Коментар ще не додано."}</p>{canManageLeads && !leadEditing && <button type="button" className="inlineEditLink" onClick={beginLeadEdit}>{selected.comment ? "Редагувати" : "+ Додати"}</button>}</div>
          {selected.trialAt && <div className="trialSummary"><span>Коли і де</span><b>{new Date(selected.trialAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</b><small>{selected.trialLocation ?? "Локацію не вказано"}</small>{canManageLeads && selected.trialResult === "scheduled" && <button type="button" className="inlineEditLink" aria-label="Змінити дату, час і локацію пробного" onClick={beginTrialScheduling}>Змінити дату й час</button>}</div>}
          <div className="preferenceSummary">
            <div><span>Бажана локація</span><b>{selected.preferredLocationName ?? "Не вказано"}</b></div>
            <div><span>Бажаний час</span><b>{availabilityLabel(selected.availability ?? [])}</b></div>
            <button className="search" onClick={() => setPreferenceMode((value) => !value)}>{preferenceMode ? "Скасувати" : "Змінити"}</button>
          </div>

          {preferenceMode && <div className="workflowBox">
            <div className="workflowHead"><h3>Побажання щодо графіка</h3><button onClick={() => setPreferenceMode(false)}>×</button></div>
            <p className="softPreferenceHint">В одному записі можна вибрати кілька днів і один часовий проміжок, наприклад Пн / Ср / Пт · 17:00–19:00. Для іншого дня або іншого часу додайте ще один запис.</p>
            {activeLocations.length === 1
              ? <label>Бажана локація<div className="singleLocationField">{activeLocations[0].name}</div></label>
              : <label>Бажана локація<select value={preferenceLocationId} onChange={(e) => setPreferenceLocationId(e.target.value)}>
                  <option value="">Не має значення</option>
                  {activeLocations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
                </select></label>}
            <AvailabilityWindowEditor value={availabilityWindows} onChange={setAvailabilityWindows} />
            <button className="primary full" disabled={preferenceSaving || availabilityWindows.some((x) => x.weekdays.length === 0 || x.end_time <= x.start_time)} onClick={saveStudentPreferences}>{preferenceSaving ? "Зберігаємо…" : "Зберегти побажання"}</button>
          </div>}



          {trialMode === "schedule" && <div id="lead-trial-workflow" className="workflowBox leadWorkflowBox">
            <div className="workflowHead"><h3>Запис на пробне</h3><button onClick={() => setTrialMode(null)}>×</button></div>
            <DateTimeEditor label="Дата і час" value={trialAt} onChange={setTrialAt} />
            <label>Локація<select value={trialLocationId} onChange={(e) => { setTrialLocationId(e.target.value); setTrialLocation(locations.find((location) => location.id === e.target.value)?.name ?? ""); }}>
              <option value="" disabled={Boolean(selected.trialLocationId)}>Без локації</option>
              {activeLocations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
            </select></label>
            <button className="primary full" onClick={scheduleTrial}>Підтвердити пробне</button>
          </div>}

          {trialMode === "complete" && <div id="lead-trial-result-workflow" className="workflowBox leadWorkflowBox">
            <div className="workflowHead"><h3>{leadProcedureTarget === "no_show" ? "Зафіксувати пропущене пробне" : "Результат пробного"}</h3><button onClick={() => { setTrialMode(null); setLeadProcedureTarget(null); }}>×</button></div>
            {!selected.trialId && <><DateTimeEditor label="Коли було пробне" value={trialAt} onChange={setTrialAt} />{activeLocations.length === 1 ? <label>Локація<div className="singleLocationField">{activeLocations[0].name}</div></label> : <label>Локація<select value={trialLocationId} onChange={(e) => setTrialLocationId(e.target.value)}><option value="">Без локації</option>{activeLocations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}</select></label>}</>}
            <label>Рекомендований рівень<select value={recommendedLevel} onChange={(e) => setRecommendedLevel(e.target.value)}><option>Початковий</option><option>Середній</option><option>Просунутий</option></select></label>
            <label>Коментар викладача<textarea value={teacherNotes} onChange={(e) => setTeacherNotes(e.target.value)} placeholder="Що сподобалось, як дитина справилась, що рекомендуємо" /></label>
            <div className="resultActions">{leadProcedureTarget !== "no_show" && <button className="primary" onClick={() => completeTrial("completed")}>Пробне пройдено</button>}<button className={leadProcedureTarget === "no_show" ? "primary" : "search"} onClick={() => completeTrial("no_show")}>Не прийшов</button>{leadProcedureTarget !== "no_show" && <button className="search" onClick={() => completeTrial("cancelled")}>Скасували</button>}</div>
          </div>}

          {selected.trialResult === "completed" && <div className="resultCard postTrialCard">
            <span>Пробне пройдено</span>
            <b>{selected.recommendedLevel ?? "Рівень не вказано"}</b>
            {selected.teacherNotes && <p>{selected.teacherNotes}</p>}
            {canManageLeads && <button type="button" className="inlineEditLink" onClick={beginTrialResult}>Редагувати результат пробного</button>}
            {selected.status === "Після пробного" && <>
              <small>Зафіксуйте рішення сім’ї. До «Очікує групу» дитина переходить тільки після підтвердження.</small>
              <div className="postTrialActions">
                <button className="primary" onClick={() => saveLeadOutcome("waiting_for_group")}>Готові навчатися</button>
                <button className="search" onClick={() => { setPostTrialMode("thinking"); setWorkspaceError(""); }}>Ще думають</button>
                <button className="search dangerSoft" onClick={() => { setCloseKind("declined"); setPostTrialMode("close"); setWorkspaceError(""); }}>Не хочуть продовжувати</button>
              </div>
            </>}
            {selected.status === "Очікує групу" && <small>Готові навчатися · можна зарахувати в групу або без групи.</small>}
          </div>}

          {leadEnrollmentOpen && <div id="lead-enrollment-workflow" data-testid="lead-enrollment-workflow" className="workflowBox leadWorkflowBox leadDirectEnrollmentStep">
            <div className="workflowHead"><h3>Зарахувати учня</h3><button onClick={() => { setLeadEnrollmentOpen(false); setLeadEnrollmentGroupId(""); }}>×</button></div>
            <p className="softPreferenceHint">Учень може навчатися в групі або окремо. Група та локація не є обов’язковими.</p>
            <label>Група<select value={leadEnrollmentGroupId} onChange={(e) => setLeadEnrollmentGroupId(e.target.value)}>
              <option value="">Оберіть групу</option>
              {groups.filter((group) => group.members.length < group.capacity).map((group) => <option value={group.id} key={group.id}>{group.name} · {group.schedule} · {group.location} · вільно {group.capacity - group.members.length}</option>)}
            </select></label>
            <button className="search full createGroupInline" onClick={() => openGroupCreation("lead")}>+ Створити нову групу</button>
            {groups.length > 0 && groups.every((group) => group.members.length >= group.capacity) && <div className="emptyState compactEmpty">Немає груп із вільними місцями.</div>}
            <button className="primary full" disabled={!leadEnrollmentGroupId || leadEnrollmentSaving} onClick={enrollLeadDirectly}>{leadEnrollmentSaving ? "Зараховуємо…" : "Зарахувати в групу"}</button>
            <div className="enrollmentOr"><span>або</span></div>
            <button className="search full enrollWithoutGroup" disabled={leadEnrollmentSaving} onClick={enrollLeadWithoutGroup}>
              <b>Зарахувати без групи</b>
              <small>Для індивідуальних або онлайн-занять. Групу й локацію можна додати пізніше.</small>
            </button>
          </div>}

          {selected.trialResult === "no_show" && !["Відмовились","Не відповідає","Неактуально"].includes(selected.status) && <div className="resultCard noShowCard">
            <span>Не прийшли на пробне</span>
            <b>Потрібен повторний контакт</b>
            {selected.teacherNotes && <p>{selected.teacherNotes}</p>}
            <small>Заявка залишається активною. Можна перезаписати пробне або закрити її після контакту.</small>
            {canManageLeads && <button type="button" className="inlineEditLink" onClick={beginTrialResult}>Редагувати результат пробного</button>}
            <div className="postTrialActions">
              <button className="primary" onClick={() => setTrialMode("schedule")}>Перезаписати пробне</button>
              <button className="search" onClick={() => { setPostTrialMode("thinking"); setWorkspaceError(""); }}>Передзвонити пізніше</button>
              <button className="search" onClick={() => { setCloseKind("no_response"); setPostTrialMode("close"); setWorkspaceError(""); }}>Закрити заявку</button>
            </div>
          </div>}

          {selected.trialResult === "cancelled" && !["Відмовились","Не відповідає","Неактуально"].includes(selected.status) && <div className="resultCard cancelledTrialCard">
            <span>Пробне скасовано</span>
            <b>Потрібно узгодити нову дату</b>
            {selected.teacherNotes && <p>{selected.teacherNotes}</p>}
            <small>Заявка залишається в роботі. Можна перезаписати пробне, поставити наступний контакт або закрити заявку.</small>
            {canManageLeads && <button type="button" className="inlineEditLink" onClick={beginTrialResult}>Редагувати результат пробного</button>}
            <div className="postTrialActions">
              <button className="primary" onClick={() => setTrialMode("schedule")}>Перезаписати пробне</button>
              <button className="search" onClick={() => { setPostTrialMode("thinking"); setWorkspaceError(""); }}>Передзвонити пізніше</button>
              <button className="search" onClick={() => { setCloseKind("declined"); setPostTrialMode("close"); setWorkspaceError(""); }}>Закрити заявку</button>
            </div>
          </div>}

          {postTrialMode === "thinking" && <div id="lead-followup-workflow" className="workflowBox leadWorkflowBox">
            <div className="workflowHead"><h3>{selected.trialResult === "no_show" || selected.trialResult === "cancelled" ? "Передзвонити пізніше" : "Ще думають"}</h3><button onClick={() => setPostTrialMode(null)}>×</button></div>
            <p className="softPreferenceHint">Залишаємо заявку в роботі й ставимо дату, коли треба зв’язатися з батьками знову.</p>
            <DateTimeEditor label="Наступний контакт" value={followUpAt} onChange={setFollowUpAt} />
            <button className="primary full" disabled={!followUpAt} onClick={saveThinkingFollowUp}>Зберегти нагадування</button>
          </div>}

          {postTrialMode === "defer" && <div id="lead-defer-workflow" className="workflowBox leadWorkflowBox deferWorkflowBox">
            <div className="workflowHead"><h3>Повернутись пізніше</h3><button onClick={() => setPostTrialMode(null)}>×</button></div>
            <p className="softPreferenceHint">Заявка сховається з основного канбану. У потрібний день вона автоматично повернеться в активні дії.</p>
            <div className="deferQuickDates">
              <button className="search" type="button" onClick={() => setDeferredMonths(1)}>Через 1 місяць</button>
              <button className="search" type="button" onClick={() => setDeferredMonths(3)}>Через 3 місяці</button>
              <button className="search" type="button" onClick={() => setDeferredMonths(6)}>Через 6 місяців</button>
            </div>
            <DateTimeEditor label="Повернутись до заявки" value={deferAt} onChange={setDeferAt} />
            <label>Причина<select value={deferReason} onChange={(e) => setDeferReason(e.target.value)}>
              <option value="later">Зараз не можуть, хочуть пізніше</option>
              <option value="age">Ще замала дитина</option>
              <option value="schedule">Зараз не підходить графік</option>
              <option value="finance">Фінанси / тимчасово не готові</option>
              <option value="school">Навчання / завантаженість</option>
              <option value="move">Переїзд / тимчасово не в місті</option>
              <option value="other">Інше</option>
            </select></label>
            <label>Коментар<textarea value={deferNote} onChange={(e) => setDeferNote(e.target.value)} placeholder="Наприклад: написати після зимових канікул" /></label>
            <button className="primary full" disabled={!deferAt || !deferReason} onClick={saveDeferredLead}>{leadIsDeferred(selected) ? "Зберегти зміни" : "Відкласти заявку"}</button>
          </div>}

          {leadIsDeferred(selected) && <div className="deferredLeadNotice">
            <span>Повернутись пізніше</span>
            <b>{selected.deferredUntil ? new Date(selected.deferredUntil).toLocaleString("uk-UA", { day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}</b>
            <small>{deferReasonLabel(selected.deferredReason)}{selected.deferredNote ? " · " + selected.deferredNote : ""}</small>
            {canManageLeads && <button className="inlineEditLink" type="button" onClick={beginLeadDefer}>Змінити дату й причину</button>}<button className="search" type="button" onClick={resumeDeferredLead}>Повернути в роботу зараз</button>
          </div>}

          {postTrialMode === "close" && <div id="lead-close-workflow" className="workflowBox leadWorkflowBox">
            <div className="workflowHead"><h3>Закрити заявку</h3><button onClick={() => setPostTrialMode(null)}>×</button></div>
            <label>Результат<select value={closeKind} onChange={(e) => setCloseKind(e.target.value as typeof closeKind)}>
              <option value="declined">Відмовились</option>
              <option value="no_response">Не відповідає</option>
              <option value="not_relevant">Неактуально</option>
            </select></label>
            {closeKind === "declined" && <label>Причина<select value={closeReason} onChange={(e) => setCloseReason(e.target.value)}>
              <option value="price">Ціна</option>
              <option value="schedule">Не підходить графік</option>
              <option value="child_not_interested">Дитині не сподобалось / не цікаво</option>
              <option value="parents_changed_mind">Батьки передумали</option>
              <option value="location">Далеко / не підходить локація</option>
              <option value="other_club">Обрали інший гурток</option>
              <option value="other">Інше</option>
            </select></label>}
            <label>Коментар<textarea value={closeNote} onChange={(e) => setCloseNote(e.target.value)} placeholder="За потреби додайте коротке пояснення" /></label>
            <button className="primary full" onClick={closeLead}>{["Відмовились","Не відповідає","Неактуально"].includes(selected.status) ? "Зберегти зміни" : "Закрити заявку"}</button>
          </div>}

          {!["Відмовились","Не відповідає","Неактуально","Зарахований"].includes(selected.status) && postTrialMode !== "close" && <div className="leadCancelBeforeHistory">
            {!leadIsDeferred(selected) && <button className="search deferLeadAction" onClick={beginLeadDefer}>Повернутись пізніше</button>}
            <button className="search dangerSoft" onClick={beginLeadClose}>Скасувати заявку</button>
          </div>}

          <div className="mobileLeadActionBar" aria-label="Дії із заявкою">
            <button className="primary mobileLeadPrimaryAction" onClick={handleLeadPrimaryAction}>
              <small>Наступна дія</small>
              <strong>{leadPrimaryActionLabel(selected)}</strong>
            </button>
            <button className="mobileLeadMoreAction" aria-label="Інші дії" onClick={() => { setLeadStatusMenuOpen(false); setLeadActionsOpen(true); }}>•••</button>
          </div>

          {leadActionsOpen && <div className="mobileLeadSheetLayer">
            <section className="mobileLeadSheet" role="dialog" aria-modal="true" aria-label="Дії із заявкою">
              <div className="mobileLeadSheetHead"><div><span>Заявка</span><h3>{selected.child}</h3></div><button aria-label="Закрити меню дій" onClick={() => setLeadActionsOpen(false)}>×</button></div>
              <div className="mobileLeadSheetActions">
                {selected.phone && <a className="mobileLeadSheetAction" href={"tel:" + selected.phone.replace(/\s/g, "")}><i>☎</i><span><b>Подзвонити</b><small>{formatUaPhone(selected.phone)}</small></span></a>}
                {selected.status === "Нова" && <button className="mobileLeadSheetAction" onClick={() => { setLeadActionsOpen(false); void updateStatus(selected.id, "Зв'язались"); }}><i>✓</i><span><b>Позначити «Зв'язались»</b><small>Перейти до наступного етапу</small></span></button>}
                {(selected.status === "Зв'язались" || selected.trialResult === "no_show" || selected.trialResult === "cancelled") && <button className="mobileLeadSheetAction" onClick={beginTrialScheduling}><i>◷</i><span><b>{selected.trialResult === "no_show" || selected.trialResult === "cancelled" ? "Перезаписати на пробне" : "Записати на пробне"}</b><small>Обрати дату, час і локацію</small></span></button>}
                {selected.status === "Пробне заплановано" && <><button className="mobileLeadSheetAction" onClick={beginTrialResult}><i>✓</i><span><b>Внести результат пробного</b><small>Був / не прийшов / скасували</small></span></button><button className="mobileLeadSheetAction" onClick={beginTrialScheduling}><i>↻</i><span><b>Перенести пробне</b><small>Змінити дату, час або локацію</small></span></button></>}
                {selected.status === "Після пробного" && <><button className="mobileLeadSheetAction" onClick={() => { setLeadActionsOpen(false); void saveLeadOutcome("waiting_for_group"); }}><i>✓</i><span><b>Готові навчатися</b><small>Перемістити в «Очікує групу»</small></span></button><button className="mobileLeadSheetAction" onClick={beginLeadFollowUp}><i>☎</i><span><b>Ще думають</b><small>Запланувати наступний контакт</small></span></button></>}
                {selected.status === "Очікує групу" && <button className="mobileLeadSheetAction" onClick={beginLeadEnrollment}><i>→</i><span><b>Зарахувати учня</b><small>У групу або без групи</small></span></button>}
                {!["Відмовились","Не відповідає","Неактуально","Зарахований"].includes(selected.status) && selected.status !== "Пробне заплановано" && <button className="mobileLeadSheetAction" onClick={beginLeadFollowUp}><i>◷</i><span><b>Запланувати дзвінок</b><small>Поставити дату наступного контакту</small></span></button>}
                {!["Відмовились","Не відповідає","Неактуально","Зарахований"].includes(selected.status) && selected.status !== "Очікує групу" && <button className="mobileLeadSheetAction" onClick={() => { setLeadActionsOpen(false); void updateStatus(selected.id, "Очікує групу"); }}><i>◎</i><span><b>Очікує групу</b><small>Позначити готовність до підбору групи</small></span></button>}
                <button className="mobileLeadSheetAction" onClick={() => { setLeadActionsOpen(false); setLeadStatusMenuOpen(true); }}><i>⇄</i><span><b>Перемістити заявку</b><small>Змінити етап вручну</small></span></button>
                {!leadIsDeferred(selected) && !["Відмовились","Не відповідає","Неактуально","Зарахований"].includes(selected.status) && <button className="mobileLeadSheetAction" onClick={beginLeadDefer}><i>◷</i><span><b>Повернутись пізніше</b><small>Сховати заявку до вибраної дати</small></span></button>}
                {leadIsDeferred(selected) && <button className="mobileLeadSheetAction" onClick={() => { setLeadActionsOpen(false); void resumeDeferredLead(); }}><i>↺</i><span><b>Повернути в роботу зараз</b><small>Прибрати відкладене нагадування</small></span></button>}
                {!["Відмовились","Не відповідає","Неактуально","Зарахований"].includes(selected.status) && <button className="mobileLeadSheetAction danger" onClick={beginLeadClose}><i>×</i><span><b>Закрити заявку</b><small>Відмова, немає відповіді або неактуально</small></span></button>}
                {["Відмовились","Не відповідає","Неактуально"].includes(selected.status) && <button className="mobileLeadSheetAction" onClick={() => { setLeadActionsOpen(false); reopenLead(); }}><i>↺</i><span><b>Повернути в роботу</b><small>Відновити активну заявку</small></span></button>}
                {canDeleteStudents && <button className="mobileLeadSheetAction danger quietDelete" disabled={leadDeleteSaving} onClick={deleteSelectedLead}><i>⌫</i><span><b>{leadDeleteSaving ? "Видаляємо…" : "Видалити заявку"}</b><small>Тільки якщо створена помилково</small></span></button>}
              </div>
            </section>
          </div>}

          {leadStatusMenuOpen && <div className="mobileLeadSheetLayer">
            <section className="mobileLeadSheet" role="dialog" aria-modal="true" aria-label="Перемістити заявку">
              <div className="mobileLeadSheetHead"><div><span>Статус</span><h3>Перемістити заявку</h3></div><button aria-label="Закрити вибір статусу" onClick={() => setLeadStatusMenuOpen(false)}>×</button></div>
              <div className="mobileLeadStageList">
                <button className={"mobileLeadStageOption stage-new " + (selected.status === "Нова" ? "active" : "")} onClick={() => setLeadMobileStatus("Нова")}><i></i><span><b>Нова</b><small>Ще не опрацьована</small></span>{selected.status === "Нова" && <strong>✓</strong>}</button>
                <button className={"mobileLeadStageOption stage-contacted " + (selected.status === "Зв'язались" ? "active" : "")} onClick={() => setLeadMobileStatus("Зв'язались")}><i></i><span><b>Зв'язались</b><small>Контакт уже відбувся</small></span>{selected.status === "Зв'язались" && <strong>✓</strong>}</button>
                <button className={"mobileLeadStageOption stage-trial " + (selected.status === "Пробне заплановано" ? "active" : "")} onClick={beginTrialScheduling}><i></i><span><b>Пробне заплановано</b><small>Спочатку вкажіть дату і час</small></span>{selected.status === "Пробне заплановано" && <strong>✓</strong>}</button>
                <button className={"mobileLeadStageOption stage-after_trial " + (selected.status === "Після пробного" ? "active" : "")} onClick={beginTrialResult}><i></i><span><b>Після пробного</b><small>Зафіксувати результат заняття</small></span>{selected.status === "Після пробного" && <strong>✓</strong>}</button>
                <button className={"mobileLeadStageOption stage-waiting " + (selected.status === "Очікує групу" ? "active" : "")} onClick={() => setLeadMobileStatus("Очікує групу")}><i></i><span><b>Очікує групу</b><small>Готові до підбору групи</small></span>{selected.status === "Очікує групу" && <strong>✓</strong>}</button>
                <button className={"mobileLeadStageOption stage-enrolled " + (selected.status === "Зарахований" ? "active" : "")} onClick={beginLeadEnrollment}><i></i><span><b>Зарахувати учня</b><small>У групу або без групи</small></span>{selected.status === "Зарахований" && <strong>✓</strong>}</button>
                <button className="mobileLeadStageOption stage-closed" onClick={beginLeadClose}><i></i><span><b>Закрити заявку</b><small>Зберегти причину закриття</small></span></button>
              </div>
            </section>
          </div>}

          {canDeleteStudents && <div className="recordDangerZone">
            <span>Службова дія</span>
            <button className="subtleDangerAction" type="button" disabled={leadDeleteSaving} onClick={deleteSelectedLead}>{leadDeleteSaving ? "Видаляємо…" : "Видалити заявку"}</button>
          </div>}
          {apiEnabled ? <AuditHistory title="Історія" events={entityEvents} loading={historyLoading} labelForEvent={auditEventLabel} detailForEvent={auditEventDetail} /> : <div className="history">
            <h3>Історія</h3>
            <div><i></i><p><b>Заявка створена</b><span>Джерело: {leadSourceLabel(selected.source)}</span></p></div>
            {selected.trialAt && <div><i></i><p><b>Пробне заплановано</b><span>{new Date(selected.trialAt).toLocaleString("uk-UA")}</span></p></div>}
            {selected.trialResult === "completed" && <div><i></i><p><b>Пробне пройдено</b><span>Рівень: {selected.recommendedLevel ?? "не вказано"}</span></p></div>}
            {selected.status !== "Нова" && <div><i></i><p><b>Поточний статус</b><span>{selected.status}</span></p></div>}
          </div>}
        </aside>
      </div>;
}
