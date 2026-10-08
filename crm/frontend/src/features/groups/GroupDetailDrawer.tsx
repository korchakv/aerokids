import type { ApiGroupDetail } from "../../api";
import { ScheduleSlotEditor, type DraftScheduleSlot } from "../../components/ScheduleEditors";
import { UiIcon } from "../../components/UiIcon";
import type { PaymentDemo } from "../billing/model";
import { availabilityLabel } from "../leads/availability";
import type { EntityId, Lead } from "../leads/model";
import type { LocationDemo } from "../locations/types";
import type { StaffDemo } from "../staff/model";
import { candidateCompatibility, MatchBadge } from "./matching";
import type { GroupItem } from "./types";

type GroupDetailDrawerProps = {
  groupId: EntityId | null;
  selectedGroup?: GroupItem;
  groupDetail: ApiGroupDetail | null;
  groupDetailLoading: boolean;
  apiEnabled: boolean;
  leads: Lead[];
  payments: PaymentDemo[];
  activeLocations: LocationDemo[];
  activeTeachers: StaffDemo[];
  teacherName?: string;
  canEditGroups: boolean;
  canManageStaff: boolean;
  canManageLeads: boolean;

  groupEditing: boolean;
  groupEditName: string;
  groupEditCapacity: number;
  groupEditLocationId: EntityId | "";
  groupEditTeacherId: EntityId | "";
  groupEditSchedule: DraftScheduleSlot[];
  groupEditError: string;
  groupEditSaving: boolean;
  groupDeleteSaving: boolean;

  groupTeacherEditing: boolean;
  selectedGroupTeacherId: EntityId | "";
  groupTeacherSaving: boolean;

  showGroupCandidatePicker: boolean;
  existingGroupCandidates: Lead[];
  groupCandidateId: EntityId | "";
  groupCandidateSaving: boolean;

  money: (value: number) => string;
  formatPhone: (value: string) => string;
  hasDuplicateSlots: (slots: DraftScheduleSlot[]) => boolean;

  onClose: () => void;
  onBeginEdit: () => void;
  onEditNameChange: (value: string) => void;
  onEditCapacityChange: (value: number) => void;
  onEditLocationChange: (value: EntityId | "") => void;
  onEditTeacherChange: (value: EntityId | "") => void;
  onEditScheduleChange: (value: DraftScheduleSlot[]) => void;
  onClearEditError: () => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void | Promise<void>;
  onDelete: () => void | Promise<void>;

  onBeginTeacherEdit: () => void;
  onSelectedTeacherChange: (value: EntityId | "") => void;
  onCancelTeacherEdit: () => void;
  onSaveTeacher: () => void | Promise<void>;

  onToggleCandidatePicker: () => void;
  onCloseCandidatePicker: () => void;
  onAddCandidate: (studentId: EntityId) => void | Promise<void>;

  onOpenStudent: (studentId: EntityId) => void;
  onOpenStudentAttendance: (studentId: EntityId, groupId: EntityId) => void;
  onOpenStudentPayments: (studentId: EntityId, paymentId?: EntityId) => void;
};

export function GroupDetailDrawer({
  groupId,
  selectedGroup,
  groupDetail,
  groupDetailLoading,
  apiEnabled,
  leads,
  payments,
  activeLocations,
  activeTeachers,
  teacherName,
  canEditGroups,
  canManageStaff,
  canManageLeads,
  groupEditing,
  groupEditName,
  groupEditCapacity,
  groupEditLocationId,
  groupEditTeacherId,
  groupEditSchedule,
  groupEditError,
  groupEditSaving,
  groupDeleteSaving,
  groupTeacherEditing,
  selectedGroupTeacherId,
  groupTeacherSaving,
  showGroupCandidatePicker,
  existingGroupCandidates,
  groupCandidateId,
  groupCandidateSaving,
  money,
  formatPhone,
  hasDuplicateSlots,
  onClose,
  onBeginEdit,
  onEditNameChange,
  onEditCapacityChange,
  onEditLocationChange,
  onEditTeacherChange,
  onEditScheduleChange,
  onClearEditError,
  onCancelEdit,
  onSaveEdit,
  onDelete,
  onBeginTeacherEdit,
  onSelectedTeacherChange,
  onCancelTeacherEdit,
  onSaveTeacher,
  onToggleCandidatePicker,
  onCloseCandidatePicker,
  onAddCandidate,
  onOpenStudent,
  onOpenStudentAttendance,
  onOpenStudentPayments,
}: GroupDetailDrawerProps) {
  if (!groupId) return null;
  const memberCount = groupDetail?.members.length ?? selectedGroup?.members.length ?? 0;
  const capacity = groupDetail?.group.capacity ?? selectedGroup?.capacity ?? "—";

  return <div className="drawerBackdrop groupPageBackdrop" data-testid="group-detail-drawer" onClick={onClose}>
    <aside className="drawer groupDetailDrawer" onClick={(event) => event.stopPropagation()}>
      <div className="groupPageTopbar">
        <button className="groupBackButton" aria-label="До списку груп" title="До списку груп" onClick={onClose}><UiIcon name="back" size={16} /><span>До списку груп</span></button>
        <button className="groupPageClose" aria-label="Закрити групу" title="Закрити" onClick={onClose}><UiIcon name="x" size={18} /></button>
      </div>
      <p className="eyebrow">Група</p>
      <div className="groupDetailHero">
        <div className="groupDetailIdentity">
          <div className="groupDetailTitleRow">
            <h2>{groupDetail?.group.name ?? selectedGroup?.name ?? "Група"}</h2>
            {canEditGroups && <button className="groupEditIcon" type="button" aria-label="Редагувати групу" title="Редагувати групу" onClick={onBeginEdit}><UiIcon name="edit" size={15} /></button>}
          </div>
          <div className="groupDetailMeta">
            <span>{selectedGroup?.location ?? "Локація не вказана"}</span>
            <span>{selectedGroup?.schedule ?? "Розклад не вказаний"}</span>
            {canManageStaff
              ? <button className="groupTeacherLink" onClick={onBeginTeacherEdit}>{teacherName ? "Викладач: " + teacherName : "+ Призначити викладача"}</button>
              : <span>{teacherName ? "Викладач: " + teacherName : "Викладач не призначений"}</span>}
          </div>
        </div>
        <div className="groupDetailHeroActions">
          <strong>{memberCount}/{capacity}</strong>
          {canManageLeads && <button className="primary compact" onClick={onToggleCandidatePicker}>+ Додати учня</button>}
        </div>
      </div>

      {groupEditing && <div className="groupEditPanel">
        <div className="groupEditPanelHead">
          <div><b>Редагування групи</b><small>Назва, місткість, локація, викладач і регулярний розклад.</small></div>
          <button className="groupEditPanelClose" type="button" aria-label="Закрити редагування" onClick={onCancelEdit}><UiIcon name="x" size={16} /></button>
        </div>
        <label>Назва групи<input autoFocus value={groupEditName} maxLength={160} onChange={(event) => { onEditNameChange(event.target.value); onClearEditError(); }} /></label>
        <div className="formTwo">
          <label>Місткість<input type="number" min={Math.max(1, memberCount)} max={100} value={groupEditCapacity} onChange={(event) => { onEditCapacityChange(Number(event.target.value)); onClearEditError(); }} /></label>
          <label>Локація <small>(необов’язково)</small><select value={groupEditLocationId} onChange={(event) => onEditLocationChange(event.target.value)}>
            <option value="">Без локації</option>
            {activeLocations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
          </select></label>
        </div>
        {canManageStaff && <label>Викладач <small>(необов’язково)</small><select value={groupEditTeacherId} onChange={(event) => onEditTeacherChange(event.target.value)}>
          <option value="">Не призначено</option>
          {activeTeachers.map((teacher) => <option value={teacher.id} key={teacher.id}>{teacher.fullName}</option>)}
        </select></label>}
        <div className="groupCreateScheduleHead"><div><b>Регулярний розклад</b><small>Можна змінити день, годину, тривалість, додати або прибрати заняття.</small></div></div>
        <ScheduleSlotEditor value={groupEditSchedule} onChange={(slots) => { onEditScheduleChange(slots); onClearEditError(); }} />
        {groupEditSchedule.length === 0 && <div className="groupEditHint">Розклад можна залишити порожнім і додати пізніше.</div>}
        {groupEditError && <div className="groupCreateError">{groupEditError}</div>}
        <div className="groupEditFooter">
          <button className="subtleDangerAction" type="button" disabled={groupEditSaving || groupDeleteSaving} onClick={() => void onDelete()}>{groupDeleteSaving ? "Видаляємо…" : "Видалити групу"}</button>
          <div className="groupEditActions">
            <button className="search" type="button" disabled={groupEditSaving || groupDeleteSaving} onClick={onCancelEdit}>Скасувати</button>
            <button className="primary" type="button" disabled={groupEditSaving || groupDeleteSaving || !groupEditName.trim() || hasDuplicateSlots(groupEditSchedule)} onClick={() => void onSaveEdit()}>{groupEditSaving ? "Зберігаємо…" : "Зберегти зміни"}</button>
          </div>
        </div>
      </div>}

      {canManageStaff && groupTeacherEditing && <div className="groupTeacherAssign">
        <label>Викладач<select autoFocus value={selectedGroupTeacherId} onChange={(event) => onSelectedTeacherChange(event.target.value)}>
          <option value="">Не призначено</option>
          {activeTeachers.map((teacher) => <option value={teacher.id} key={teacher.id}>{teacher.fullName}</option>)}
        </select></label>
        <div className="groupTeacherAssignActions">
          <button className="search" onClick={onCancelTeacherEdit}>Скасувати</button>
          <button className="primary" disabled={groupTeacherSaving} onClick={() => void onSaveTeacher()}>{groupTeacherSaving ? "Зберігаємо…" : "Зберегти"}</button>
        </div>
      </div>}

      {showGroupCandidatePicker && <div className="groupCandidatePicker">
        <div className="groupCandidatePickerHead"><div><b>Нові учасники</b><small>Кандидати, яких можна додати до цієї групи.</small></div><span>{existingGroupCandidates.length} кандидатів</span></div>
        {existingGroupCandidates.length === 0 ? <div className="emptyState compactEmpty">Немає кандидатів після пробного, яких можна додати до цієї групи.</div> : <div className="groupCandidateRows">
          {existingGroupCandidates.map((candidate) => {
            const slots = (groupDetail?.schedules ?? []).map((slot) => ({ weekday: slot.weekday, start_time: slot.start_time.slice(0, 5), duration_minutes: slot.duration_minutes }));
            const match = candidateCompatibility(candidate, slots, groupDetail?.group.location_id ?? null);
            return <article className="groupMemberCard groupCandidateMemberRow" key={candidate.id}>
              <div className="groupMemberTop"><span className="candidateAvatar">{candidate.child[0]}</span><div><b>{candidate.child}</b><small>{candidate.age} років · {candidate.recommendedLevel ?? "рівень не вказано"} · {candidate.status}</small><small>{candidate.parent}{candidate.phone ? " · " + formatPhone(candidate.phone) : ""}</small></div></div>
              <div className="candidateRowMatch"><MatchBadge match={match} /><small>{availabilityLabel(candidate.availability ?? [])}</small></div>
              <button className="primary compact" disabled={groupCandidateSaving && groupCandidateId === candidate.id} onClick={() => void onAddCandidate(candidate.id)}>{groupCandidateSaving && groupCandidateId === candidate.id ? "Додаємо…" : "Додати до групи"}</button>
            </article>;
          })}
        </div>}
        <div className="groupCandidatePickerActions"><button className="search" onClick={onCloseCandidatePicker}>Закрити</button></div>
      </div>}

      {groupDetailLoading && <div className="emptyState">Завантажуємо дані групи…</div>}

      {!apiEnabled && selectedGroup && <div className="groupMemberList">{selectedGroup.members.map((studentId) => {
        const student = leads.find((item) => item.id === studentId);
        const studentPayments = payments.filter((item) => item.studentId === studentId);
        const due = studentPayments.find((item) => item.status === "overdue") ?? studentPayments.find((item) => item.status === "pending");
        return <article className="groupMemberCard" key={studentId}>
          <div className="groupMemberTop"><span className="candidateAvatar">{student?.child?.[0] ?? "?"}</span><div><b>{student?.child ?? "Учень"}</b><small>{student?.age ?? "—"} років · {student?.parent ?? "Контакт не вказано"}</small></div></div>
          <div className="groupMemberMetrics"><span>Оплата <b>{due ? (due.status === "overdue" ? "прострочена" : "очікується") : "✓"}</b></span><span>До дати <b>{due?.dueDate ? new Date(due.dueDate).toLocaleDateString("uk-UA") : "—"}</b></span></div>
          <button className="link" onClick={() => onOpenStudent(studentId)}>Відкрити учня →</button>
        </article>;
      })}</div>}

      {apiEnabled && groupDetail && <div className="groupMemberList groupRoster">
        <div className="groupMemberSectionHead">
          <div><b>Активні учасники</b><small>{groupDetail.members.length} у групі</small></div>
          <span className="groupRosterHint">Учень · відвідування · оплата</span>
        </div>
        {groupDetail.members.length === 0 && <div className="emptyState">У групі немає активних або призупинених учнів.</div>}
        {groupDetail.members.map((member) => {
          const billingLabel = member.billing?.status === "overdue" ? "Прострочено" : member.billing?.status === "due" ? "Оплата сьогодні" : member.billing?.status === "upcoming" ? "Очікується" : member.billing?.status === "current" ? "Сплачено" : "Без тарифу";
          const latestPayment = member.payments.find((payment) => payment.balance_minor > 0) ?? member.payments[0];
          const usage = member.billing?.lessons_included != null ? `${member.billing.lessons_used ?? 0}/${member.billing.lessons_included}` : null;
          const remaining = member.billing?.lessons_remaining;
          return <article className="groupMemberCard groupMemberCardCompact groupRosterRow" key={member.student_id}>
            <div className="groupMemberIdentityCell groupRosterIdentity">
              <div className="groupMemberTop">
                <span className="candidateAvatar groupRosterAvatar">{member.first_name[0]}</span>
                <div>
                  <b>{member.first_name} {member.last_name ?? ""}</b>
                  <small>{member.age ?? "—"} років · у групі з {new Date(member.enrollment_started_at + "T00:00:00").toLocaleDateString("uk-UA")}</small>
                  <small className="groupRosterContact">{member.contact_name ?? "Відповідальний не вказаний"}{member.contact_phone ? " · " + formatPhone(member.contact_phone) : ""}</small>
                </div>
              </div>
              <button className="groupRosterStudentLink" onClick={() => onOpenStudent(member.student_id)}>Картка учня →</button>
            </div>
            <button className="groupMemberMetricButton attendanceMetric groupRosterMetric" onClick={() => onOpenStudentAttendance(member.student_id, groupDetail.group.id)}>
              <span className="groupRosterMetricHead"><small>Відвідування</small><b>{member.attendance.attendance_rate}%</b></span>
              <span className="groupRosterProgress"><i style={{ width: Math.max(0, Math.min(100, member.attendance.attendance_rate)) + "%" }} /></span>
              <em>{member.attendance.present} був · {member.attendance.late} запізн. · {member.attendance.absent} нема · {member.attendance.excused} поважн.</em>
              <span className="groupRosterOpen">Журнал →</span>
            </button>
            {member.billing ? <div className="groupMemberFinanceCell groupRosterFinance">
              <button className="groupMemberMetricButton paymentMetric groupRosterPayment" onClick={() => onOpenStudentPayments(member.student_id, latestPayment?.id)}>
                <span className="groupRosterMetricHead"><small>Оплата</small><b className={"groupPaymentBadge " + member.billing.status}>{billingLabel}</b></span>
                <span className="groupRosterPlan"><b>{member.billing.plan_name ?? "Тариф не вказано"}</b>{usage && <small>{usage} занять{remaining != null ? " · залишилось " + remaining : ""}</small>}</span>
                <span className="groupRosterPaymentFooter"><small>{member.billing.subscription_ends_on ? "До " + new Date(member.billing.subscription_ends_on + "T00:00:00").toLocaleDateString("uk-UA") : "Без дати завершення"}</small><b className={member.billing.amount_due_minor > 0 ? "debt" : "paid"}>{member.billing.amount_due_minor > 0 ? "Борг " + money(member.billing.amount_due_minor / 100) : "Оплачено"}</b></span>
              </button>
              {member.payments.length > 0 && <details className="memberPayments memberPaymentsInline groupRosterHistory">
                <summary>Історія оплат ({member.payments.length})</summary>
                <div>{member.payments.map((payment) => <button className="memberPaymentHistoryRow" key={payment.id} onClick={() => onOpenStudentPayments(member.student_id, payment.id)}><span>{payment.note ?? "Нарахування"}<small>{payment.due_date ? "До " + new Date(payment.due_date + "T00:00:00").toLocaleDateString("uk-UA") : "Без дати"}</small></span><b>{money(payment.adjusted_amount_minor / 100)}<small>{payment.balance_minor > 0 ? "Залишок " + money(payment.balance_minor / 100) : payment.status === "cancelled" ? "Скасовано" : payment.status === "refunded" ? "Повернено" : "Сплачено"}</small></b></button>)}</div>
              </details>}
            </div> : <div className="groupMemberFinanceCell groupRosterFinance"><span className="groupMemberMetricStatic"><small>Оплата</small><b>Приховано для ролі</b><em>Фінансові дані недоступні</em></span></div>}
          </article>;
        })}
      </div>}
    </aside>
  </div>;
}
