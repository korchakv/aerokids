import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { UiIcon, navigationIcon } from "./components/UiIcon";
import { AuditHistory } from "./components/AuditHistory";
import { LoginView } from "./features/auth/LoginView";
import { AvailabilityWindowEditor, DateTimeEditor, DAY_NAMES, DurationSelect, ScheduleSlotEditor, TimeSelect, type AvailabilitySlot, type AvailabilityWindowDraft, type DraftScheduleSlot } from "./components/ScheduleEditors";
import { apiDelete, apiEnabled, apiPatch, apiPost, apiPut, changeOrganization, checkIntakeDuplicates, clearSession, loadAttendance, loadAuditEvents, loadGroupDetail, loadGroupRoster, loadOperations, loadOverviewReport, loadPaymentReminders, loadSession, loadStudentAttendanceHistory, loadTeaching, loadWorkspace, recordPaymentReminder, refreshMe, runBillingRenewals, type ApiAuditEvent, type ApiGroupDetail, type ApiGroupRosterStudent, type ApiPaymentReminder, type ApiStudentAttendanceHistoryItem, type ApiStudentSubscription, type IntakeDuplicateMatch, type OperationsBundle, type OverviewReport, type Session, type TeachingBundle, type WorkspaceBundle } from "./api";

type LeadStatus = "Нова" | "Зв'язались" | "Пробне заплановано" | "Після пробного" | "Очікує групу" | "Зарахований" | "Не відповідає" | "Відмовились" | "Неактуально";

type EntityId = string;
type UiScale = 1 | 1.1 | 1.25 | 1.4;
const UI_SCALE_LEVELS: UiScale[] = [1, 1.1, 1.25, 1.4];

type LeadKanbanColumnId = "new" | "contacted" | "trial" | "no_show" | "after_trial" | "waiting" | "deferred" | "closed";

const leadKanbanColumns: Array<{ id: LeadKanbanColumnId; title: string; hint: string }> = [
  { id: "new", title: "Нові", hint: "Перший контакт" },
  { id: "contacted", title: "Зв’язались", hint: "В роботі" },
  { id: "trial", title: "Пробне", hint: "Заплановано" },
  { id: "no_show", title: "Не прийшов", hint: "Потрібна дія" },
  { id: "after_trial", title: "Після пробного", hint: "Очікуємо рішення" },
  { id: "waiting", title: "Очікує групу", hint: "Готовий до набору" },
  { id: "deferred", title: "Повернутись пізніше", hint: "Нагадування на майбутнє" },
  { id: "closed", title: "Закриті", hint: "Відмова / неактуально" },
];

type Lead = {
  id: EntityId;
  createdAt?: string;
  firstName?: string;
  lastName?: string;
  child: string;
  age: number;
  parent: string;
  phone: string;
  childPhone?: string;
  source: string;
  status: LeadStatus;
  comment?: string;
  preferredLocationId?: string;
  preferredLocationName?: string;
  availability?: AvailabilitySlot[];
  trialId?: string;
  trialAt?: string;
  trialLocationId?: string;
  trialLocation?: string;
  trialResult?: "scheduled" | "completed" | "no_show" | "cancelled";
  recommendedLevel?: string;
  teacherNotes?: string;
  nextContactAt?: string;
  deferredUntil?: string;
  deferredReason?: string;
  deferredNote?: string;
  closeReason?: string;
  closeNote?: string;
};

type GroupItem = {
  id: EntityId;
  name: string;
  ages: string;
  schedule: string;
  location: string;
  capacity: number;
  members: EntityId[];
  teacherName?: string;
};

type AttendanceValue = "present" | "absent" | "late" | "excused";

type LessonItem = {
  id: EntityId;
  groupId: EntityId;
  startsAt: string;
  duration: number;
  topic: string;
  notes?: string;
  status?: "scheduled" | "completed" | "cancelled";
  attendancePresent?: number;
  attendanceAbsent?: number;
  attendanceLate?: number;
  attendanceExcused?: number;
  attendanceTotal?: number;
};

type PlanDemo = {
  id: EntityId;
  name: string;
  price: number;
  days: number | null;
  lessons: number | null;
  isActive: boolean;
  usageMode?: "attendance" | "scheduled" | "period";
  absentRule?: "consume" | "dont_consume" | "choice";
  excusedRule?: "consume" | "dont_consume" | "makeup";
  endRule?: "lessons" | "date" | "whichever_first";
};

type PaymentDemo = {
  id: EntityId;
  studentId: EntityId;
  planId: EntityId;
  subscriptionId?: EntityId;
  amount: number;
  adjustedAmount: number;
  paidAmount: number;
  refundedAmount: number;
  balanceAmount: number;
  creditAmount: number;
  dueDate: string;
  status: "pending" | "paid" | "overdue" | "refunded" | "cancelled";
  method?: "Картка" | "Готівка" | "Переказ";
};

type LocationDemo = {
  id: EntityId;
  name: string;
  address: string;
  isActive: boolean;
};

type StaffRoleDemo = "Власник" | "Адміністратор" | "Менеджер" | "Викладач" | "Бухгалтер";

type StaffDemo = {
  id: EntityId;
  fullName: string;
  role: StaffRoleDemo;
  canTeach: boolean;
  email: string;
  phone: string;
  locationIds: EntityId[];
  groupIds: EntityId[];
  isActive: boolean;
};

const allNav = ["Дашборд", "Заявки", "Учні", "Групи", "Розклад", "Відвідування", "Оплати", "Працівники", "Локації", "Звіти", "Налаштування"];

function cleanSpaces(value: string) {
  return value.trim().replace(/\s+/g, " ");
}

function personNameError(value: string, label = "Ім’я"): string {
  const name = cleanSpaces(value);
  if (!name) return label + " обов’язкове";
  if (name.length < 2) return label + " має містити щонайменше 2 символи";
  if (name.length > 160) return label + " занадто довге";
  if (!/^[A-Za-zА-Яа-яІіЇїЄєҐґ'’\- ]+$/.test(name)) return label + ": лише літери, пробіл, апостроф або дефіс";
  if (/^[ '’\-]|[ '’\-]$|[ '’\-]{2,}/.test(name)) return "Перевірте написання поля «" + label + "»";
  return "";
}

function fullNameError(value: string, label: string): string {
  const basic = personNameError(value, label);
  if (basic) return basic;
  if (cleanSpaces(value).split(" ").filter(Boolean).length < 2) return label + ": вкажіть ім’я та прізвище";
  return "";
}


function normalizeUaPhone(value: string): string | null {
  const digits = value.replace(/\D/g, "");
  let national = "";
  if (digits.startsWith("380") && digits.length === 12) national = digits.slice(3);
  else if (digits.startsWith("0") && digits.length === 10) national = digits.slice(1);
  else if (digits.length === 9) national = digits;
  else return null;
  if (!/^[3-9]\d{8}$/.test(national)) return null;
  return "+380" + national;
}

function uaPhoneError(value: string, required = true): string {
  if (!value.trim()) return required ? "Телефон обов’язковий" : "";
  return normalizeUaPhone(value) ? "" : "Некоректний номер України. Приклад: +380 67 123 45 67";
}

function formatUaPhone(value: string): string {
  const normalized = normalizeUaPhone(value);
  if (!normalized) return value;
  const n = normalized.slice(4);
  return "+380 " + n.slice(0, 2) + " " + n.slice(2, 5) + " " + n.slice(5, 7) + " " + n.slice(7, 9);
}

function normalizedSearch(value: string) {
  return cleanSpaces(value).toLocaleLowerCase("uk-UA");
}

function searchMatches(query: string, value: string | null | undefined) {
  if (!value) return false;
  if (normalizedSearch(value).includes(query)) return true;
  const queryDigits = query.replace(/\D/g, "");
  const valueDigits = value.replace(/\D/g, "");
  return queryDigits.length >= 3 && valueDigits.includes(queryDigits);
}

function dayOffsetForDate(value: string | Date) {
  const current = new Date();
  current.setHours(0, 0, 0, 0);
  const target = typeof value === "string" ? new Date(value) : new Date(value);
  target.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - current.getTime()) / (24 * 60 * 60 * 1000));
}

function weekdayLong(value: string) {
  const text = new Date(value).toLocaleDateString("uk-UA", { weekday: "long" });
  return text ? text.charAt(0).toLocaleUpperCase("uk-UA") + text.slice(1) : "";
}

function tariffHistoryDetail(event: ApiAuditEvent) {
  const payload = event.payload ?? {};
  const before = (payload.before && typeof payload.before === "object" ? payload.before : {}) as Record<string, unknown>;
  const after = (payload.after && typeof payload.after === "object" ? payload.after : {}) as Record<string, unknown>;
  const changed = Array.isArray(payload.changed_fields) ? payload.changed_fields.filter((field): field is string => typeof field === "string") : [];

  const formatValue = (field: string, value: unknown) => {
    if (value === null || value === undefined || value === "") return "—";
    if (field === "price_minor" && typeof value === "number") return (value / 100).toLocaleString("uk-UA") + " грн";
    if (field === "period_days") return String(value) + " дн.";
    if (field === "lessons_included") return String(value) + " відв.";
    if (field === "is_active") return value ? "Активний" : "Неактивний";
    return String(value);
  };
  const labels: Record<string, string> = {
    name: "Назва",
    price_minor: "Ціна",
    period_days: "Дні",
    lessons_included: "Відвідування",
    is_active: "Статус",
  };

  if (event.event_type === "subscription_plan.created") {
    const parts = [
      typeof payload.price_minor === "number" ? formatValue("price_minor", payload.price_minor) : "",
      payload.period_days ? formatValue("period_days", payload.period_days) : "",
      payload.lessons_included ? formatValue("lessons_included", payload.lessons_included) : "",
    ].filter(Boolean);
    return parts.join(" · ") || "Тариф створено";
  }
  return changed.map((field) => `${labels[field] ?? field}: ${formatValue(field, before[field])} → ${formatValue(field, after[field])}`).join(" · ") || "Змінено";
}

function attendanceStatusLabel(value: AttendanceValue | undefined) {
  const labels: Record<AttendanceValue, string> = {
    present: "Був",
    absent: "Не був",
    excused: "Поважна причина",
    late: "Запізнився",
  };
  return value ? labels[value] : "Не відмічено";
}

function emailError(value: string, required = false): string {
  const email = value.trim().toLowerCase();
  if (!email) return required ? "Email обов’язковий" : "";
  if (email.length > 255 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return "Некоректна email-адреса";
  return "";
}

const initialLeads: Lead[] = [
  { id: "1", child: "Максим", age: 9, parent: "Оксана", phone: "+380 67 123 45 67", status: "Очікує групу", source: "Сайт", comment: "Цікавиться FPV та симулятором.", trialResult: "completed", recommendedLevel: "Початковий" },
  { id: "2", child: "Артем", age: 10, parent: "Ірина", phone: "+380 50 222 14 09", status: "Пробне заплановано", source: "Instagram", trialAt: "2026-10-05T17:00", trialLocation: "Основна локація", trialResult: "scheduled" },
  { id: "3", child: "Софія", age: 11, parent: "Марина", phone: "+380 96 411 28 60", status: "Очікує групу", source: "Сайт", comment: "Після пробного готова продовжувати.", trialResult: "completed", recommendedLevel: "Початковий" },
  { id: "4", child: "Данило", age: 8, parent: "Олег", phone: "+380 93 701 44 31", status: "Очікує групу", source: "Сайт", trialResult: "completed", recommendedLevel: "Початковий" },
  { id: "5", child: "Анна", age: 9, parent: "Наталія", phone: "+380 68 555 11 20", status: "Очікує групу", source: "Рекомендація", trialResult: "completed", recommendedLevel: "Початковий" },
  { id: "6", child: "Олег", age: 10, parent: "Вікторія", phone: "+380 95 100 23 44", status: "Очікує групу", source: "Сайт", trialResult: "completed", recommendedLevel: "Початковий" },
  { id: "7", child: "Ілля", age: 12, parent: "Юлія", phone: "+380 97 222 42 15", status: "Очікує групу", source: "Instagram", trialResult: "completed", recommendedLevel: "Середній" },
  { id: "8", child: "Марта", age: 9, parent: "Андрій", phone: "+380 67 700 10 08", status: "Зарахований", source: "Сайт", trialResult: "completed", recommendedLevel: "Початковий" },
  { id: "9", child: "Назар", age: 10, parent: "Олена", phone: "+380 95 700 10 09", status: "Зарахований", source: "Рекомендація", trialResult: "completed", recommendedLevel: "Початковий" },
];

const statuses: LeadStatus[] = ["Нова", "Зв'язались", "Пробне заплановано", "Після пробного", "Очікує групу"];

function App() {
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const saved = window.localStorage.getItem("aerokids-crm-theme");
    if (saved === "dark" || saved === "light") return saved;
    return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
  });
  const [uiScale, setUiScale] = useState<UiScale>(() => {
    const saved = Number(window.localStorage.getItem("aerokids-crm-ui-scale"));
    return UI_SCALE_LEVELS.includes(saved as UiScale) ? saved as UiScale : 1;
  });
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const [workspaceLoading, setWorkspaceLoading] = useState(() => Boolean(apiEnabled && loadSession()));
  const [workspaceRefreshing, setWorkspaceRefreshing] = useState(false);
  const [workspaceError, setWorkspaceError] = useState("");
  const [saveToastTick, setSaveToastTick] = useState(0);
  const [workspaceLoaded, setWorkspaceLoaded] = useState(false);
  const [overviewReport, setOverviewReport] = useState<OverviewReport | null>(null);
  const [entityEvents, setEntityEvents] = useState<ApiAuditEvent[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [active, setActive] = useState("Дашборд");
  const [organizationName, setOrganizationName] = useState("");
  const [organizationTimezone, setOrganizationTimezone] = useState("Europe/Kyiv");
  const [organizationCurrency, setOrganizationCurrency] = useState("UAH");
  const [organizationLocale, setOrganizationLocale] = useState("uk-UA");
  const [organizationSaving, setOrganizationSaving] = useState(false);
  const [leadSort, setLeadSort] = useState<"priority" | "next_action" | "newest">("priority");
  const [leadSourceFilter, setLeadSourceFilter] = useState("all");
  const [leadMoveSavingId, setLeadMoveSavingId] = useState<EntityId | null>(null);
  const [leadProcedureTarget, setLeadProcedureTarget] = useState<LeadKanbanColumnId | null>(null);
  const [leadEnrollmentGroupId, setLeadEnrollmentGroupId] = useState<EntityId | "">("");
  const [leadEnrollmentSaving, setLeadEnrollmentSaving] = useState(false);
  const [leadActionsOpen, setLeadActionsOpen] = useState(false);
  const [leadStatusMenuOpen, setLeadStatusMenuOpen] = useState(false);
  const [leadDeleteSaving, setLeadDeleteSaving] = useState(false);
  const [studentFilter, setStudentFilter] = useState<"all" | "active" | "paused" | "archived">("all");
  const [candidateAgeFilter, setCandidateAgeFilter] = useState<"all" | "8-10" | "11-13">("all");
  const [candidateLevelFilter, setCandidateLevelFilter] = useState("all");
  const [candidateLocationFilter, setCandidateLocationFilter] = useState("all");
  const [candidateMatchFilter, setCandidateMatchFilter] = useState<"all" | "match" | "partial" | "conflict" | "unknown">("all");
  const [candidateSort, setCandidateSort] = useState<"match" | "age" | "name">("match");
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadChildName, setLeadChildName] = useState("");
  const [leadChildLastName, setLeadChildLastName] = useState("");
  const [leadChildPhone, setLeadChildPhone] = useState("");
  const [leadAge, setLeadAge] = useState(9);
  const [leadContactName, setLeadContactName] = useState("");
  const [leadPhone, setLeadPhone] = useState("");
  const [leadSource, setLeadSource] = useState("phone");
  const [leadComment, setLeadComment] = useState("");
  const [leadEditing, setLeadEditing] = useState(false);
  const [leadEditFirstName, setLeadEditFirstName] = useState("");
  const [leadEditLastName, setLeadEditLastName] = useState("");
  const [leadEditChildPhone, setLeadEditChildPhone] = useState("");
  const [leadEditAge, setLeadEditAge] = useState(9);
  const [leadEditContactName, setLeadEditContactName] = useState("");
  const [leadEditPhone, setLeadEditPhone] = useState("");
  const [leadEditSource, setLeadEditSource] = useState("phone");
  const [leadEditComment, setLeadEditComment] = useState("");
  const [leadEditSaving, setLeadEditSaving] = useState(false);
  const [leadDuplicateMatches, setLeadDuplicateMatches] = useState<IntakeDuplicateMatch[]>([]);
  const [leadDuplicateChecking, setLeadDuplicateChecking] = useState(false);
  const [leads, setLeads] = useState<Lead[]>(apiEnabled ? [] : initialLeads);
  const [groups, setGroups] = useState<GroupItem[]>(apiEnabled ? [] : [
    { id: "1", name: "FPV Start 8–10", ages: "8–10", schedule: "Пн / Ср · 17:00", location: "Основна локація", capacity: 8, members: ["8", "9"] },
  ]);
  const [lessons, setLessons] = useState<LessonItem[]>(apiEnabled ? [] : [
    { id: "1", groupId: "1", startsAt: "2026-09-30T17:00", duration: 60, topic: "FPV: траса в симуляторі" },
    { id: "2", groupId: "1", startsAt: "2026-10-05T17:00", duration: 60, topic: "Whoop: базове керування" },
  ]);
  const [selectedLessonId, setSelectedLessonId] = useState<EntityId>(apiEnabled ? "" : "1");
  const [attendance, setAttendance] = useState<Record<EntityId, Record<EntityId, AttendanceValue>>>(apiEnabled ? {} : {
    "1": { "8": "present", "9": "late" },
  });
  const [attendanceNotes, setAttendanceNotes] = useState<Record<EntityId, Record<EntityId, string>>>({});
  const [attendanceConsume, setAttendanceConsume] = useState<Record<EntityId, Record<EntityId, boolean>>>({});
  const [attendanceLoading, setAttendanceLoading] = useState(false);
  const [attendanceSaving, setAttendanceSaving] = useState(false);
  const [focusedAttendanceStudentId, setFocusedAttendanceStudentId] = useState<EntityId | null>(null);
  const [focusedAttendanceGroupId, setFocusedAttendanceGroupId] = useState<EntityId | null>(null);
  const [studentAttendanceHistory, setStudentAttendanceHistory] = useState<ApiStudentAttendanceHistoryItem[]>([]);
  const [studentAttendanceHistoryLoading, setStudentAttendanceHistoryLoading] = useState(false);
  const [lessonSaveNotice, setLessonSaveNotice] = useState<"" | "details" | "attendance">("");
  const [lessonRoster, setLessonRoster] = useState<ApiGroupRosterStudent[] | null>(null);
  const [lessonRosterLoading, setLessonRosterLoading] = useState(false);
  const [lessonTopicDraft, setLessonTopicDraft] = useState("");
  const [lessonNotesDraft, setLessonNotesDraft] = useState("");
  const [lessonDetailsSaving, setLessonDetailsSaving] = useState(false);
  const [lessonEditing, setLessonEditing] = useState(true);
  const [plans, setPlans] = useState<PlanDemo[]>(apiEnabled ? [] : [
    { id: "1", name: "8 занять / 30 днів", price: 1800, days: 30, lessons: 8, isActive: true },
    { id: "2", name: "Індивідуальний", price: 0, days: 30, lessons: null, isActive: true },
  ]);
  const [payments, setPayments] = useState<PaymentDemo[]>(apiEnabled ? [] : [
    { id: "1", studentId: "8", planId: "1", amount: 1800, adjustedAmount: 1800, paidAmount: 0, refundedAmount: 0, balanceAmount: 1800, creditAmount: 0, dueDate: "2026-10-05", status: "pending" },
    { id: "2", studentId: "9", planId: "1", amount: 1800, adjustedAmount: 1800, paidAmount: 1800, refundedAmount: 0, balanceAmount: 0, creditAmount: 0, dueDate: "2026-09-28", status: "paid", method: "Картка" },
  ]);
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [paymentStudentId, setPaymentStudentId] = useState<EntityId>("8");
  const [paymentPlanId, setPaymentPlanId] = useState<EntityId>("1");
  const [paymentDueDate, setPaymentDueDate] = useState(() => defaultPaymentDueDate());
  const [paymentSaving, setPaymentSaving] = useState(false);
  const [subscriptions, setSubscriptions] = useState<ApiStudentSubscription[]>([]);
  const [paymentAutoRenew, setPaymentAutoRenew] = useState(true);
  const [paymentActionId, setPaymentActionId] = useState<EntityId | null>(null);
  const [focusedPaymentId, setFocusedPaymentId] = useState<EntityId | null>(null);
  const [paymentActionType, setPaymentActionType] = useState<"partial" | "refund" | "adjustment" | null>(null);
  const [paymentActionAmount, setPaymentActionAmount] = useState("");
  const [paymentActionReason, setPaymentActionReason] = useState("");
  const [paymentActionMethod, setPaymentActionMethod] = useState<"cash" | "card" | "bank">("card");
  const [paymentAdjustmentDirection, setPaymentAdjustmentDirection] = useState<"decrease" | "increase">("decrease");
  const [paymentActionSaving, setPaymentActionSaving] = useState(false);
  const [pauseSubscriptionId, setPauseSubscriptionId] = useState<EntityId | null>(null);
  const [pauseStart, setPauseStart] = useState(() => localDateInput(new Date()));
  const [pauseResumeOn, setPauseResumeOn] = useState("");
  const [pauseNote, setPauseNote] = useState("");
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [planEditId, setPlanEditId] = useState<EntityId | null>(null);
  const [planName, setPlanName] = useState("8 занять / 30 днів");
  const [planPrice, setPlanPrice] = useState("");
  const [planDays, setPlanDays] = useState("30");
  const [planLessons, setPlanLessons] = useState("8");
  const [planActive, setPlanActive] = useState(true);
  const [planSaving, setPlanSaving] = useState(false);
  const [showInactivePlans, setShowInactivePlans] = useState(false);
  const [planHistory, setPlanHistory] = useState<ApiAuditEvent[]>([]);
  const [planHistoryLoading, setPlanHistoryLoading] = useState(false);
  const [planHistoryOpen, setPlanHistoryOpen] = useState(false);
  const [planChangeSubscriptionId, setPlanChangeSubscriptionId] = useState<EntityId | null>(null);
  const [planChangePlanId, setPlanChangePlanId] = useState<EntityId | "">("");
  const [planChangeReason, setPlanChangeReason] = useState("");
  const [planChangeSaving, setPlanChangeSaving] = useState(false);
  const [planChangeResult, setPlanChangeResult] = useState("");
  const [planUsageMode, setPlanUsageMode] = useState<"attendance" | "scheduled" | "period">("attendance");
  const [planAbsentRule, setPlanAbsentRule] = useState<"consume" | "dont_consume" | "choice">("choice");
  const [planExcusedRule, setPlanExcusedRule] = useState<"consume" | "dont_consume" | "makeup">("makeup");
  const [planEndRule, setPlanEndRule] = useState<"lessons" | "date" | "whichever_first">("whichever_first");
  const [locations, setLocations] = useState<LocationDemo[]>([
    { id: "1", name: "Основна локація", address: "Івано-Франківськ", isActive: true },
  ]);
  const [staff, setStaff] = useState<StaffDemo[]>([
    { id: "1", fullName: "Іван Викладач", role: "Викладач", canTeach: true, email: "ivan@aerokids.example", phone: "+380 67 111 22 33", locationIds: ["1"], groupIds: ["1"], isActive: true },
    { id: "2", fullName: "Адміністратор AeroKids", role: "Адміністратор", canTeach: true, email: "admin@aerokids.example", phone: "+380 67 444 55 66", locationIds: ["1"], groupIds: [], isActive: true },
  ]);
  const [selectedStaffId, setSelectedStaffId] = useState<EntityId | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<EntityId | null>(null);
  const [groupDetail, setGroupDetail] = useState<ApiGroupDetail | null>(null);
  const [groupDetailLoading, setGroupDetailLoading] = useState(false);
  const [showGroupCandidatePicker, setShowGroupCandidatePicker] = useState(false);
  const [groupCandidateId, setGroupCandidateId] = useState<EntityId | "">("");
  const [groupCandidateSaving, setGroupCandidateSaving] = useState(false);
  const [selectedGroupTeacherId, setSelectedGroupTeacherId] = useState<EntityId | "">("");
  const [groupTeacherSaving, setGroupTeacherSaving] = useState(false);
  const [groupTeacherEditing, setGroupTeacherEditing] = useState(false);
  const [groupEditing, setGroupEditing] = useState(false);
  const [groupEditName, setGroupEditName] = useState("");
  const [groupEditCapacity, setGroupEditCapacity] = useState(8);
  const [groupEditLocationId, setGroupEditLocationId] = useState<EntityId | "">("");
  const [groupEditTeacherId, setGroupEditTeacherId] = useState<EntityId | "">("");
  const [groupEditSchedule, setGroupEditSchedule] = useState<DraftScheduleSlot[]>([]);
  const [groupEditSaving, setGroupEditSaving] = useState(false);
  const [groupDeleteSaving, setGroupDeleteSaving] = useState(false);
  const [groupEditError, setGroupEditError] = useState("");
  const [paymentReminders, setPaymentReminders] = useState<ApiPaymentReminder[]>([]);
  const [reminderSavingId, setReminderSavingId] = useState<EntityId | null>(null);
  const [showStaffForm, setShowStaffForm] = useState(false);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<StaffRoleDemo>("Викладач");
  const [inviteCanTeach, setInviteCanTeach] = useState(true);
  const [inviteLink, setInviteLink] = useState("");
  const [staffResetLink, setStaffResetLink] = useState("");
  const [showLocationForm, setShowLocationForm] = useState(false);
  const [locationEditId, setLocationEditId] = useState<EntityId | null>(null);
  const [locationSaving, setLocationSaving] = useState(false);
  const [locationDeleteSaving, setLocationDeleteSaving] = useState(false);
  const [staffName, setStaffName] = useState("");
  const [staffRole, setStaffRole] = useState<StaffRoleDemo>("Викладач");
  const [staffCanTeach, setStaffCanTeach] = useState(true);
  const [staffEmail, setStaffEmail] = useState("");
  const [staffPhone, setStaffPhone] = useState("");
  const [locationName, setLocationName] = useState("");
  const [locationAddress, setLocationAddress] = useState("");
  const [selectedId, setSelectedId] = useState<EntityId | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<EntityId | null>(null);
  const [studentDeleteSaving, setStudentDeleteSaving] = useState(false);
  const [studentStates, setStudentStates] = useState<Record<EntityId, "Активний" | "Пауза" | "Архів">>({});
  const [transferGroupId, setTransferGroupId] = useState<EntityId | null>(null);
  const [trialMode, setTrialMode] = useState<"schedule" | "complete" | null>(null);
  const [postTrialMode, setPostTrialMode] = useState<"thinking" | "defer" | "close" | null>(null);
  const [followUpAt, setFollowUpAt] = useState("");
  const [deferAt, setDeferAt] = useState("");
  const [deferReason, setDeferReason] = useState("later");
  const [deferNote, setDeferNote] = useState("");
  const [closeKind, setCloseKind] = useState<"declined" | "no_response" | "not_relevant">("declined");
  const [closeReason, setCloseReason] = useState("schedule");
  const [closeNote, setCloseNote] = useState("");
  const [preferenceMode, setPreferenceMode] = useState(false);
  const [preferenceLocationId, setPreferenceLocationId] = useState<EntityId | "">("");
  const [availabilityWindows, setAvailabilityWindows] = useState<AvailabilityWindowDraft[]>([]);
  const [preferenceSaving, setPreferenceSaving] = useState(false);
  const [trialAt, setTrialAt] = useState("2026-10-05T17:00");
  const [trialLocation, setTrialLocation] = useState("Основна локація");
  const [trialLocationId, setTrialLocationId] = useState<EntityId | "">("");
  const [recommendedLevel, setRecommendedLevel] = useState("Початковий");
  const [teacherNotes, setTeacherNotes] = useState("");
  const [selectedCandidates, setSelectedCandidates] = useState<EntityId[]>([]);
  const [groupName, setGroupName] = useState("FPV Start 8–10");
  const [groupSchedule, setGroupSchedule] = useState<DraftScheduleSlot[]>([
    { weekday: 0, start_time: "17:00", duration_minutes: 60 },
    { weekday: 2, start_time: "17:00", duration_minutes: 60 },
  ]);
  const [groupCapacity, setGroupCapacity] = useState(8);
  const [groupLocationId, setGroupLocationId] = useState<EntityId | "">("");
  const [showGroupForm, setShowGroupForm] = useState(false);
  const [groupCreateError, setGroupCreateError] = useState("");
  const [locationReturnToGroup, setLocationReturnToGroup] = useState(false);
  const [groupCreateContext, setGroupCreateContext] = useState<"groups" | "candidates" | "lead">("groups");
  const [newGroupTeacherId, setNewGroupTeacherId] = useState<EntityId | "">("");
  const [newLessonGroupId, setNewLessonGroupId] = useState<EntityId>("1");
  const [newLessonAt, setNewLessonAt] = useState("2026-10-07T17:00");
  const [newLessonDuration, setNewLessonDuration] = useState(60);
  const [newLessonTopic, setNewLessonTopic] = useState("FPV / електроніка");
  const [scheduleGroupId, setScheduleGroupId] = useState<EntityId>("1");
  const [scheduleWeekday, setScheduleWeekday] = useState(0);
  const [scheduleTime, setScheduleTime] = useState("17:00");
  const [scheduleDuration, setScheduleDuration] = useState(60);
  const [scheduleWeekOffset, setScheduleWeekOffset] = useState(0);
  const [scheduleFilterGroupId, setScheduleFilterGroupId] = useState<EntityId | "all">("all");
  const [attendanceDayOffset, setAttendanceDayOffset] = useState(0);
  const workspaceAutoRefreshBusy = useRef(false);
  useEffect(() => {
    setStaffResetLink("");
  }, [selectedStaffId]);

  useEffect(() => {
    if (!lessonSaveNotice) return;
    const timer = window.setTimeout(() => setLessonSaveNotice(""), 2200);
    return () => window.clearTimeout(timer);
  }, [lessonSaveNotice]);

  useEffect(() => {
    const handleSaved = () => setSaveToastTick((value) => value + 1);
    window.addEventListener("crm:saved", handleSaved);
    return () => window.removeEventListener("crm:saved", handleSaved);
  }, []);

  useEffect(() => {
    if (!saveToastTick) return;
    const timer = window.setTimeout(() => setSaveToastTick(0), 1900);
    return () => window.clearTimeout(timer);
  }, [saveToastTick]);

  useEffect(() => {
    if (!apiEnabled || !session) return;
    refreshMe(session).then(setSession).catch(() => {
      clearSession();
      setSession(null);
    });
    // Session is refreshed once when the app shell mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  const syncWorkspace = async (currentSession: Session) => {
    setWorkspaceLoading(true);
    setWorkspaceError("");
    try {
      const membership = currentSession.user.memberships.find((item) => item.organization_id === currentSession.organizationId);
      const role = membership?.role ?? "";
      const financeRole = ["owner", "admin", "accountant"].includes(role);
      const reportRole = ["owner", "admin", "manager", "accountant"].includes(role);
      if (financeRole) {
        await runBillingRenewals(currentSession).catch(() => undefined);
      }
      const [bundle, operations, teaching, report, reminders] = await Promise.all([
        loadWorkspace(currentSession),
        loadOperations(currentSession),
        loadTeaching(currentSession),
        reportRole ? loadOverviewReport(currentSession) : Promise.resolve(null),
        financeRole ? loadPaymentReminders(currentSession).catch(() => []) : Promise.resolve([]),
      ]);
      applyWorkspace(bundle, setLeads, setGroups, setStudentStates);
      applyOperations(operations, setLocations, setStaff, setPlans, setPayments, setSubscriptions);
      setPaymentStudentId((current) =>
        bundle.students.some((student) => student.student_id === current)
          ? current
          : (bundle.students[0]?.student_id ?? "")
      );
      setPaymentPlanId((current) =>
        operations.plans.some((plan) => plan.id === current && plan.price_minor > 0)
          ? current
          : (operations.plans.find((plan) => plan.price_minor > 0)?.id ?? operations.plans[0]?.id ?? "")
      );
      const activeOpsLocations = operations.locations.filter((location) => location.is_active);
      if (activeOpsLocations.length === 1) {
        setTrialLocationId(activeOpsLocations[0].id);
        setTrialLocation(activeOpsLocations[0].name);
        setGroupLocationId((current) => current || activeOpsLocations[0].id);
        setPreferenceLocationId((current) => current || activeOpsLocations[0].id);
      } else {
        if (!trialLocationId && activeOpsLocations[0]) setTrialLocationId(activeOpsLocations[0].id);
        if (!groupLocationId && activeOpsLocations[0]) setGroupLocationId(activeOpsLocations[0].id);
      }
      applyTeaching(teaching, setLessons, setGroups);
      setOverviewReport(report);
      setPaymentReminders(reminders);
      setSelectedLessonId((current) => {
        if (teaching.lessons.some((item) => item.id === current)) return current;
        const now = Date.now();
        const nearest = [...teaching.lessons].sort((a, b) =>
          Math.abs(new Date(a.starts_at).getTime() - now) - Math.abs(new Date(b.starts_at).getTime() - now)
        )[0];
        return nearest?.id ?? "";
      });
      setWorkspaceLoaded(true);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося завантажити дані CRM");
      throw error;
    } finally {
      setWorkspaceLoading(false);
    }
  };

  useEffect(() => {
    if (!apiEnabled || !session) return;
    syncWorkspace(session).catch(() => undefined);
    // Reload whenever the selected organization changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.accessToken, session?.organizationId]);

  useEffect(() => {
    if (!apiEnabled || !session) return;

    const refreshWorkspaceSnapshot = async () => {
      if (document.visibilityState !== "visible" || workspaceAutoRefreshBusy.current) return;
      workspaceAutoRefreshBusy.current = true;
      setWorkspaceRefreshing(true);
      try {
        const [bundle, teaching] = await Promise.all([
          loadWorkspace(session),
          loadTeaching(session),
        ]);
        applyWorkspace(bundle, setLeads, setGroups, setStudentStates);
        applyTeaching(teaching, setLessons, setGroups);
      } catch {
        // Keep the current UI stable on a transient background refresh failure.
      } finally {
        workspaceAutoRefreshBusy.current = false;
        setWorkspaceRefreshing(false);
      }
    };

    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refreshWorkspaceSnapshot();
    };
    const intervalId = window.setInterval(() => void refreshWorkspaceSnapshot(), 15_000);

    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      workspaceAutoRefreshBusy.current = false;
    };
  }, [session?.accessToken, session?.organizationId]);

    const selected = leads.find((lead) => lead.id === selectedId) ?? null;
  const selectedMissingDetails = selected ? leadMissingDetails(selected) : [];
  const selectedStudent = leads.find((lead) => lead.id === selectedStudentId) ?? null;
  const activeStudents = leads.filter((lead) => lead.status === "Зарахований");
  const activeLocations = useMemo(() => locations.filter((location) => location.isActive), [locations]);

  useEffect(() => {
    if (activeLocations.length !== 1) return;
    const only = activeLocations[0];
    setTrialLocationId(only.id);
    setTrialLocation(only.name);
    setGroupLocationId((current) => current || only.id);
    setPreferenceLocationId((current) => current || only.id);
  }, [activeLocations]);

  useEffect(() => {
    const entityId = selected?.id ?? selectedStudent?.id;
    if (!entityId || !apiEnabled || !session) {
      setEntityEvents([]);
      return;
    }
    const role = session.user.memberships.find((item) => item.organization_id === session.organizationId)?.role;
    if (!["owner", "admin", "manager", "teacher"].includes(role ?? "")) {
      setEntityEvents([]);
      return;
    }

    let cancelled = false;
    setHistoryLoading(true);
    loadAuditEvents("student", entityId, session)
      .then((events) => {
        if (!cancelled) setEntityEvents(events);
      })
      .catch(() => {
        if (!cancelled) setEntityEvents([]);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });

    return () => { cancelled = true; };
  }, [selected?.id, selectedStudent?.id, session?.accessToken, session?.organizationId]);
  const studentGroup = (studentId: EntityId) => groups.find((group) => group.members.includes(studentId));

  const waiting = useMemo(() => leads.filter((x) => x.status === "Очікує групу"), [leads]);
  const stats = useMemo(() => ({
    newLeads: leads.filter((x) => x.status === "Нова").length,
    trial: leads.filter((x) => x.status === "Пробне заплановано").length,
    waiting: waiting.length,
    activeStudents: leads.filter((x) => x.status === "Зарахований").length,
  }), [leads, waiting]);

  const upcomingTrials = useMemo(() => leads
    .filter((lead) => lead.trialAt && lead.status === "Пробне заплановано")
    .sort((a, b) => new Date(a.trialAt ?? 0).getTime() - new Date(b.trialAt ?? 0).getTime())
    .slice(0, 5), [leads]);

  const visibleLeads = useMemo(() => {
    let items = leads.filter((item) => item.status !== "Зарахований");

    if (leadSourceFilter !== "all") {
      items = items.filter((item) => canonicalLeadSource(item.source) === leadSourceFilter);
    }

    items = [...items].sort((a, b) => {
      if (leadSort === "newest") return dateValue(b.createdAt) - dateValue(a.createdAt);
      if (leadSort === "next_action") {
        const aAction = dateValue(a.nextContactAt ?? a.trialAt, Number.MAX_SAFE_INTEGER);
        const bAction = dateValue(b.nextContactAt ?? b.trialAt, Number.MAX_SAFE_INTEGER);
        if (aAction !== bAction) return aAction - bAction;
        return leadActionPriority(a) - leadActionPriority(b);
      }
      const priority = leadActionPriority(a) - leadActionPriority(b);
      if (priority !== 0) return priority;
      const followUpOrder = dateValue(a.nextContactAt ?? a.trialAt, Number.MAX_SAFE_INTEGER)
        - dateValue(b.nextContactAt ?? b.trialAt, Number.MAX_SAFE_INTEGER);
      if (followUpOrder !== 0) return followUpOrder;
      return dateValue(b.createdAt) - dateValue(a.createdAt);
    });
    return items;
  }, [leads, leadSort, leadSourceFilter]);

  const leadActionCount = useMemo(() => leads.filter((lead) => {
    if (leadIsDeferred(lead)) return false;
    if (["Відмовились", "Не відповідає", "Неактуально", "Зарахований"].includes(lead.status)) return false;
    if (lead.nextContactAt && dateValue(lead.nextContactAt) <= Date.now()) return true;
    if (lead.trialResult === "no_show" || lead.trialResult === "cancelled") return true;
    if (lead.status === "Нова" || lead.status === "Після пробного") return true;
    return false;
  }).length, [leads]);

  const leadActiveCount = useMemo(() => leads.filter((lead) =>
    !leadIsDeferred(lead) && !["Відмовились", "Не відповідає", "Неактуально", "Зарахований"].includes(lead.status)
  ).length, [leads]);

  const visibleStudents = useMemo(() => activeStudents.filter((item) => {
    const state = studentStates[item.id] ?? "Активний";
    if (studentFilter === "active") return state === "Активний";
    if (studentFilter === "paused") return state === "Пауза";
    if (studentFilter === "archived") return state === "Архів";
    return true;
  }), [activeStudents, studentStates, studentFilter]);

  const candidateLevels = useMemo(() => Array.from(new Set(waiting.map((item) => item.recommendedLevel).filter((value): value is string => Boolean(value)))).sort((a, b) => a.localeCompare(b, "uk-UA")), [waiting]);

  const visibleWaiting = useMemo(() => {
    const matchOrder = ["match", "partial", "unknown", "conflict"] as const;
    const rows = waiting.map((item) => ({
      item,
      match: candidateCompatibility(item, groupSchedule, groupLocationId || null),
    })).filter(({ item, match }) => {
      if (candidateAgeFilter === "8-10" && !(item.age >= 8 && item.age <= 10)) return false;
      if (candidateAgeFilter === "11-13" && !(item.age >= 11 && item.age <= 13)) return false;
      if (candidateLevelFilter !== "all" && item.recommendedLevel !== candidateLevelFilter) return false;
      if (candidateLocationFilter === "none" && item.preferredLocationId) return false;
      if (!["all", "none"].includes(candidateLocationFilter) && item.preferredLocationId !== candidateLocationFilter) return false;
      if (candidateMatchFilter !== "all" && match.state !== candidateMatchFilter) return false;
      return true;
    });

    rows.sort((a, b) => {
      if (candidateSort === "age") return a.item.age - b.item.age || a.item.child.localeCompare(b.item.child, "uk-UA");
      if (candidateSort === "name") return a.item.child.localeCompare(b.item.child, "uk-UA");

      const matchDiff = matchOrder.indexOf(a.match.state) - matchOrder.indexOf(b.match.state);
      if (matchDiff !== 0) return matchDiff;

      if (groupLocationId) {
        const aSameLocation = a.item.preferredLocationId === groupLocationId ? 0 : 1;
        const bSameLocation = b.item.preferredLocationId === groupLocationId ? 0 : 1;
        if (aSameLocation !== bSameLocation) return aSameLocation - bSameLocation;
      }

      return a.item.age - b.item.age || a.item.child.localeCompare(b.item.child, "uk-UA");
    });

    return rows.map(({ item }) => item);
  }, [waiting, candidateAgeFilter, candidateLevelFilter, candidateLocationFilter, candidateMatchFilter, candidateSort, groupSchedule, groupLocationId]);

  const saveOrganizationSettings = async () => {
    if (!session || !organizationName.trim()) return;
    setOrganizationSaving(true);
    setWorkspaceError("");
    try {
      await apiPatch("/organization", {
        name: organizationName.trim(),
        timezone: organizationTimezone.trim(),
        currency: organizationCurrency.trim().toUpperCase(),
        locale: organizationLocale.trim(),
      }, session);
      const refreshed = await refreshMe(session);
      setSession(refreshed);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти налаштування");
    } finally {
      setOrganizationSaving(false);
    }
  };

  const checkManualLeadDuplicates = async (): Promise<IntakeDuplicateMatch[]> => {
    if (!apiEnabled || !session) return [];
    const normalizedPhone = normalizeUaPhone(leadPhone);
    const normalizedChildPhone = leadChildPhone.trim() ? normalizeUaPhone(leadChildPhone) : null;
    if (!normalizedPhone || !leadChildName.trim() || leadAge < 3 || leadAge > 25) {
      setLeadDuplicateMatches([]);
      return [];
    }
    setLeadDuplicateChecking(true);
    try {
      const result = await checkIntakeDuplicates({
        child_first_name: cleanSpaces(leadChildName),
        child_age: leadAge,
        phone: normalizedPhone,
        child_phone: normalizedChildPhone,
      }, session);
      setLeadDuplicateMatches(result.matches);
      return result.matches;
    } catch {
      setLeadDuplicateMatches([]);
      return [];
    } finally {
      setLeadDuplicateChecking(false);
    }
  };

  const openDuplicateStudent = (match: IntakeDuplicateMatch) => {
    setShowLeadForm(false);
    setLeadDuplicateMatches([]);
    if (match.crm_status === "enrolled") {
      setActive("Учні");
      setSelectedStudentId(match.student_id);
    } else {
      setActive("Заявки");
      setSelectedId(match.student_id);
    }
  };

  const createManualLead = async () => {
    const childNameError = personNameError(leadChildName, "Ім’я дитини");
    const childLastNameError = leadChildLastName.trim() ? personNameError(leadChildLastName, "Прізвище дитини") : "";
    const childPhoneError = uaPhoneError(leadChildPhone, false);
    const contactNameError = personNameError(leadContactName, "Відповідальна особа");
    const phoneError = uaPhoneError(leadPhone);
    if (childNameError || childLastNameError || childPhoneError || contactNameError || phoneError) {
      setWorkspaceError(childNameError || childLastNameError || childPhoneError || contactNameError || phoneError);
      return;
    }
    const normalizedPhone = normalizeUaPhone(leadPhone)!;
    const normalizedChildPhone = leadChildPhone.trim() ? normalizeUaPhone(leadChildPhone) : null;
    if (apiEnabled && session) {
      try {
        const matches = await checkManualLeadDuplicates();
        const likelyDuplicate = matches.find((item) => item.likely_same_student);
        if (likelyDuplicate) {
          setWorkspaceError("");
          return;
        }
        await apiPost("/intake", {
          child_first_name: cleanSpaces(leadChildName),
          child_last_name: leadChildLastName.trim() ? cleanSpaces(leadChildLastName) : null,
          child_phone: normalizedChildPhone,
          child_age: leadAge,
          contact_name: cleanSpaces(leadContactName),
          phone: normalizedPhone,
          source: leadSource,
          comment: leadComment.trim() || null,
        }, session);
        await syncWorkspace(session);
        setShowLeadForm(false);
        setLeadDuplicateMatches([]);
        setActive("Заявки");
        setLeadChildName("");
        setLeadChildLastName("");
        setLeadChildPhone("");
        setLeadContactName("");
        setLeadPhone("");
        setLeadComment("");
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося створити заявку");
        return;
      }
    }

    const nextId = crypto.randomUUID();
    setLeads((items) => [{
      id: nextId,
      firstName: cleanSpaces(leadChildName),
      lastName: leadChildLastName.trim() ? cleanSpaces(leadChildLastName) : undefined,
      child: [cleanSpaces(leadChildName), leadChildLastName.trim() ? cleanSpaces(leadChildLastName) : ""].filter(Boolean).join(" "),
      childPhone: normalizedChildPhone ? formatUaPhone(normalizedChildPhone) : undefined,
      age: leadAge,
      parent: cleanSpaces(leadContactName),
      phone: formatUaPhone(normalizedPhone),
      source: leadSource,
      status: "Нова",
      comment: leadComment.trim() || undefined,
    }, ...items]);
    setShowLeadForm(false);
    setLeadDuplicateMatches([]);
    setActive("Заявки");
  };

  const moveLeadOnBoard = async (lead: Lead, target: LeadKanbanColumnId) => {
    if (leadMoveSavingId || lead.status === "Зарахований") return;
    const currentColumn = leadKanbanColumn(lead);
    if (currentColumn === target) return;
    setWorkspaceError("");

    // Stages that require data open the exact procedure instead of silently changing status.
    if (target === "trial") {
      openLead(lead.id);
      setLeadProcedureTarget("trial");
      if (!lead.trialAt) setTrialAt(toLocalDateTimeInput(new Date().toISOString()));
      window.setTimeout(() => setTrialMode("schedule"), 0);
      return;
    }
    if (target === "after_trial") {
      openLead(lead.id);
      setLeadProcedureTarget("after_trial");
      if (!lead.trialAt) setTrialAt(toLocalDateTimeInput(new Date().toISOString()));
      window.setTimeout(() => setTrialMode("complete"), 0);
      return;
    }
    if (target === "no_show") {
      openLead(lead.id);
      setLeadProcedureTarget("no_show");
      if (!lead.trialAt) setTrialAt(toLocalDateTimeInput(new Date().toISOString()));
      window.setTimeout(() => setTrialMode("complete"), 0);
      return;
    }
    if (target === "waiting") {
      openLead(lead.id);
      setLeadProcedureTarget("waiting");
      return;
    }
    if (target === "deferred") {
      openLead(lead.id);
      const date = new Date();
      date.setMonth(date.getMonth() + 6);
      date.setHours(10, 0, 0, 0);
      setDeferAt(toLocalDateTimeInput(date.toISOString()));
      setDeferReason("later");
      setDeferNote("");
      window.setTimeout(() => setPostTrialMode("defer"), 0);
      return;
    }
    if (target === "closed") {
      openLead(lead.id);
      setLeadProcedureTarget("closed");
      window.setTimeout(() => setPostTrialMode("close"), 0);
      return;
    }

    // "Нова" and "Зв'язались" have no mandatory procedure.
    setLeadMoveSavingId(lead.id);
    try {
      if (apiEnabled && session) {
        const status = target === "new" ? "new" : "contacted";
        await apiPatch(`/students/${lead.id}/crm-status`, { crm_status: status }, session);
        await syncWorkspace(session);
      } else {
        setLeads((items) => items.map((item) => item.id !== lead.id ? item : {
          ...item,
          status: target === "new" ? "Нова" : "Зв'язались",
        }));
      }
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося перемістити заявку.");
    } finally {
      setLeadMoveSavingId(null);
    }
  };

  const updateStatus = async (id: EntityId, status: LeadStatus) => {
    if (apiEnabled && session) {
      try {
        await apiPatch(`/students/${id}/crm-status`, { crm_status: crmStatusValue(status) }, session);
        await syncWorkspace(session);
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося змінити статус заявки.");
        return;
      }
    }
    setLeads((items) => items.map((item) => item.id === id ? { ...item, status } : item));
  };

  const scheduleTrial = async () => {
    if (!selected) return;
    if (apiEnabled && session) {
      try {
        if (selected.trialId) {
          await apiPatch(`/trial-lessons/${selected.trialId}`, {
            location_id: trialLocationId || null,
            starts_at: new Date(trialAt).toISOString(),
          }, session);
        } else {
          await apiPost("/trial-lessons", {
            student_id: selected.id,
            location_id: trialLocationId || null,
            starts_at: new Date(trialAt).toISOString(),
          }, session);
        }
        await syncWorkspace(session);
        if (leadProcedureTarget === "after_trial" || leadProcedureTarget === "no_show") {
          setTrialMode("complete");
        } else {
          setTrialMode(null);
          setLeadProcedureTarget(null);
        }
        return;
      } catch {
        return;
      }
    }
    setLeads((items) => items.map((item) => item.id === selected.id ? {
      ...item,
      status: "Пробне заплановано",
      trialAt,
      trialLocation: locations.find((location) => location.id === trialLocationId)?.name ?? trialLocation,
      trialResult: "scheduled",
    } : item));
    setTrialMode(null);
  };

  const completeTrial = async (result: "completed" | "no_show" | "cancelled") => {
    if (!selected) return;
    if (apiEnabled && session) {
      try {
        let trialId = selected.trialId;
        if (!trialId) {
          const created = await apiPost<{ id: EntityId }>("/trial-lessons", {
            student_id: selected.id,
            location_id: trialLocationId || null,
            starts_at: new Date(trialAt).toISOString(),
          }, session);
          trialId = created.id;
        }
        await apiPatch(`/trial-lessons/${trialId}/complete`, {
          status: result,
          recommended_level: result === "completed" ? recommendedLevel : null,
          teacher_notes: teacherNotes || null,
        }, session);
        await syncWorkspace(session);
        setTrialMode(null);
        setLeadProcedureTarget(null);
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти результат пробного.");
        return;
      }
    }
    setLeads((items) => items.map((item) => item.id === selected.id ? {
      ...item,
      status: result === "completed" ? "Після пробного" : "Зв'язались",
      trialResult: result,
      recommendedLevel: result === "completed" ? recommendedLevel : item.recommendedLevel,
      teacherNotes: teacherNotes || item.teacherNotes,
    } : item));
    setTrialMode(null);
    setLeadProcedureTarget(null);
  };

  const openLead = (id: EntityId) => {
    setSelectedId(id);
    setLeadEditing(false);
    setTrialMode(null);
    setPostTrialMode(null);
    setPreferenceMode(false);
    setLeadProcedureTarget(null);
    setLeadEnrollmentGroupId("");
    setLeadActionsOpen(false);
    setLeadStatusMenuOpen(false);
    const lead = leads.find((item) => item.id === id);
    setTrialAt(lead?.trialAt ? toLocalDateTimeInput(lead.trialAt) : toLocalDateTimeInput(new Date().toISOString()));
    if (lead?.trialLocation) setTrialLocation(lead.trialLocation);
    if (lead?.trialLocationId) setTrialLocationId(lead.trialLocationId);
    if (lead?.recommendedLevel) setRecommendedLevel(lead.recommendedLevel);
    setTeacherNotes(lead?.teacherNotes ?? "");
    setFollowUpAt(lead?.nextContactAt ? toLocalDateTimeInput(lead.nextContactAt) : "");
    setCloseKind(lead?.status === "Не відповідає" ? "no_response" : lead?.status === "Неактуально" ? "not_relevant" : "declined");
    setCloseReason(lead?.closeReason ?? "schedule");
    setCloseNote(lead?.closeNote ?? "");
    setPreferenceLocationId(lead?.preferredLocationId ?? "");
    setAvailabilityWindows(groupAvailabilitySlots(lead?.availability ?? []));
  };

  const beginLeadEdit = () => {
    if (!selected) return;
    const fallbackParts = selected.child.trim().split(/\s+/);
    setLeadEditFirstName(selected.firstName ?? fallbackParts[0] ?? "");
    setLeadEditLastName(selected.lastName ?? fallbackParts.slice(1).join(" "));
    setLeadEditChildPhone(selected.childPhone ?? "");
    setLeadEditAge(selected.age || 9);
    setLeadEditContactName(selected.parent === "Контакт не вказано" ? "" : selected.parent);
    setLeadEditPhone(selected.phone ?? "");
    setLeadEditSource(canonicalLeadSource(selected.source) || "phone");
    setLeadEditComment(selected.comment ?? "");
    setWorkspaceError("");
    setLeadEditing(true);
  };

  const saveLeadDetails = async () => {
    if (!selected || leadEditSaving) return;
    const childNameError = personNameError(leadEditFirstName, "Ім’я дитини");
    const childLastNameError = leadEditLastName.trim() ? personNameError(leadEditLastName, "Прізвище дитини") : "";
    const childPhoneError = uaPhoneError(leadEditChildPhone, false);
    const contactNameError = personNameError(leadEditContactName, "Відповідальна особа");
    const phoneError = uaPhoneError(leadEditPhone);
    if (childNameError || childLastNameError || childPhoneError || contactNameError || phoneError) {
      setWorkspaceError(childNameError || childLastNameError || childPhoneError || contactNameError || phoneError);
      return;
    }
    if (leadEditAge < 3 || leadEditAge > 25) {
      setWorkspaceError("Вік дитини має бути від 3 до 25 років.");
      return;
    }

    const firstName = cleanSpaces(leadEditFirstName);
    const lastName = leadEditLastName.trim() ? cleanSpaces(leadEditLastName) : "";
    const childPhone = leadEditChildPhone.trim() ? normalizeUaPhone(leadEditChildPhone) : null;
    const phone = normalizeUaPhone(leadEditPhone);
    if (!phone) {
      setWorkspaceError("Вкажіть коректний номер відповідальної особи.");
      return;
    }

    setLeadEditSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiPatch(`/students/${selected.id}/lead-details`, {
          child_first_name: firstName,
          child_last_name: lastName || null,
          child_phone: childPhone,
          child_age: leadEditAge,
          contact_name: cleanSpaces(leadEditContactName),
          phone,
          source: leadEditSource,
          comment: leadEditComment.trim() || null,
        }, session);
        await syncWorkspace(session);
        try {
          setEntityEvents(await loadAuditEvents("student", selected.id, session));
        } catch {
          // The lead itself is already saved; history refresh can wait for the next open.
        }
      } else {
        setLeads((items) => items.map((item) => item.id === selected.id ? {
          ...item,
          firstName,
          lastName: lastName || undefined,
          child: [firstName, lastName].filter(Boolean).join(" "),
          childPhone: childPhone ? formatUaPhone(childPhone) : undefined,
          age: leadEditAge,
          parent: cleanSpaces(leadEditContactName),
          phone: formatUaPhone(phone),
          source: leadEditSource,
          comment: leadEditComment.trim() || undefined,
        } : item));
      }
      setLeadEditing(false);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти дані заявки.");
    } finally {
      setLeadEditSaving(false);
    }
  };

  const saveLeadOutcome = async (
    crmStatus: "contacted" | "trial_completed" | "waiting_for_group" | "declined" | "no_response" | "not_relevant",
    options: { nextContactAt?: string; closeReason?: string; closeNote?: string } = {},
  ) => {
    if (!selected) return;
    if (apiEnabled && session) {
      try {
        setWorkspaceError("");
        await apiPatch(`/students/${selected.id}/lead-outcome`, {
          crm_status: crmStatus,
          next_contact_at: options.nextContactAt ? new Date(options.nextContactAt).toISOString() : null,
          close_reason: options.closeReason || null,
          close_note: options.closeNote || null,
        }, session);
        await syncWorkspace(session);
        setPostTrialMode(null);
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося оновити результат заявки");
        return;
      }
    }

    const statusMap: Record<string, LeadStatus> = {
      contacted: "Зв'язались",
      trial_completed: "Після пробного",
      waiting_for_group: "Очікує групу",
      declined: "Відмовились",
      no_response: "Не відповідає",
      not_relevant: "Неактуально",
    };
    setLeads((items) => items.map((item) => item.id === selected.id ? {
      ...item,
      status: statusMap[crmStatus] ?? item.status,
      nextContactAt: options.nextContactAt || undefined,
      closeReason: options.closeReason || undefined,
      closeNote: options.closeNote || undefined,
    } : item));
    setPostTrialMode(null);
  };

  const saveThinkingFollowUp = () => {
    if (!followUpAt) {
      setWorkspaceError("Вкажіть дату наступного контакту.");
      return;
    }
    const status = selected?.trialResult === "no_show" || selected?.trialResult === "cancelled" ? "contacted" : "trial_completed";
    void saveLeadOutcome(status, { nextContactAt: followUpAt });
  };

  const saveDeferredLead = async () => {
    if (!selected || !deferAt) {
      setWorkspaceError("Вкажіть дату, коли повернутися до заявки.");
      return;
    }
    if (apiEnabled && session) {
      try {
        setWorkspaceError("");
        await apiPatch(`/students/${selected.id}/defer`, {
          deferred_until: new Date(deferAt).toISOString(),
          reason: deferReason,
          note: deferNote.trim() || null,
        }, session);
        await syncWorkspace(session);
        setPostTrialMode(null);
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося відкласти заявку.");
        return;
      }
    }
    setLeads((items) => items.map((item) => item.id === selected.id ? {
      ...item,
      deferredUntil: deferAt,
      deferredReason: deferReason,
      deferredNote: deferNote.trim() || undefined,
      nextContactAt: deferAt,
    } : item));
    setPostTrialMode(null);
  };

  const resumeDeferredLead = async () => {
    if (!selected) return;
    if (apiEnabled && session) {
      try {
        await apiPatch(`/students/${selected.id}/defer`, { deferred_until: null, reason: null, note: null }, session);
        await syncWorkspace(session);
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося повернути заявку в роботу.");
      }
      return;
    }
    setLeads((items) => items.map((item) => item.id === selected.id ? {
      ...item,
      deferredUntil: undefined,
      deferredReason: undefined,
      deferredNote: undefined,
      nextContactAt: undefined,
    } : item));
  };

  const closeLead = () => {
    if (closeKind === "declined" && !closeReason) {
      setWorkspaceError("Оберіть причину відмови.");
      return;
    }
    void saveLeadOutcome(closeKind, {
      closeReason: closeKind === "declined" ? closeReason : undefined,
      closeNote: closeNote.trim() || undefined,
    });
  };

  const reopenLead = () => {
    if (!selected) return;
    const status = selected.trialResult === "completed" ? "trial_completed" : "contacted";
    void saveLeadOutcome(status);
  };

  const revealLeadWorkflow = (id: string) => {
    window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };

  const beginTrialScheduling = () => {
    if (!selected) return;
    setLeadActionsOpen(false);
    setLeadStatusMenuOpen(false);
    setPostTrialMode(null);
    setLeadProcedureTarget("trial");
    setTrialAt(selected.trialAt ? toLocalDateTimeInput(selected.trialAt) : toLocalDateTimeInput(new Date().toISOString()));
    setTrialMode("schedule");
    revealLeadWorkflow("lead-trial-workflow");
  };

  const beginTrialResult = () => {
    if (!selected) return;
    setLeadActionsOpen(false);
    setLeadStatusMenuOpen(false);
    setPostTrialMode(null);
    setLeadProcedureTarget("after_trial");
    setTrialMode("complete");
    revealLeadWorkflow("lead-trial-result-workflow");
  };

  const beginLeadFollowUp = () => {
    setLeadActionsOpen(false);
    setLeadStatusMenuOpen(false);
    setTrialMode(null);
    setPostTrialMode("thinking");
    revealLeadWorkflow("lead-followup-workflow");
  };

  const beginLeadDefer = () => {
    setLeadActionsOpen(false);
    setLeadStatusMenuOpen(false);
    setTrialMode(null);
    const date = new Date();
    date.setMonth(date.getMonth() + 6);
    date.setHours(10, 0, 0, 0);
    setDeferAt(toLocalDateTimeInput(date.toISOString()));
    setDeferReason("later");
    setDeferNote("");
    setPostTrialMode("defer");
    revealLeadWorkflow("lead-defer-workflow");
  };

  const setDeferredMonths = (months: number) => {
    const date = new Date();
    date.setMonth(date.getMonth() + months);
    date.setHours(10, 0, 0, 0);
    setDeferAt(toLocalDateTimeInput(date.toISOString()));
  };

  const beginLeadEnrollment = () => {
    setLeadActionsOpen(false);
    setLeadStatusMenuOpen(false);
    setTrialMode(null);
    setPostTrialMode(null);
    setLeadProcedureTarget("waiting");
    revealLeadWorkflow("lead-enrollment-workflow");
  };

  const beginLeadClose = () => {
    setLeadActionsOpen(false);
    setLeadStatusMenuOpen(false);
    setCloseKind("declined");
    setPostTrialMode("close");
    revealLeadWorkflow("lead-close-workflow");
  };

  const deleteSelectedLead = async () => {
    if (!selected || leadDeleteSaving) return;
    if (!window.confirm(`Видалити заявку «${selected.child}»? Це варто робити тільки для помилково створених заявок. Якщо вже є важлива історія, CRM заблокує видалення.`)) return;
    setLeadDeleteSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiDelete(`/students/${selected.id}`, session);
        await syncWorkspace(session);
      } else {
        setLeads((items) => items.filter((item) => item.id !== selected.id));
      }
      setSelectedId(null);
      setLeadActionsOpen(false);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося видалити заявку.");
    } finally {
      setLeadDeleteSaving(false);
    }
  };

  const handleLeadPrimaryAction = () => {
    if (!selected) return;
    if (["Відмовились", "Не відповідає", "Неактуально"].includes(selected.status)) {
      reopenLead();
      return;
    }
    if (selected.status === "Зарахований") {
      setSelectedId(null);
      setSelectedStudentId(selected.id);
      setActive("Учні");
      return;
    }
    if (selected.status === "Нова") {
      void updateStatus(selected.id, "Зв'язались");
      return;
    }
    if (selected.status === "Пробне заплановано") {
      beginTrialResult();
      return;
    }
    if (selected.status === "Після пробного") {
      setLeadStatusMenuOpen(false);
      setLeadActionsOpen(true);
      return;
    }
    if (selected.status === "Очікує групу") {
      beginLeadEnrollment();
      return;
    }
    beginTrialScheduling();
  };

  const setLeadMobileStatus = (status: "Нова" | "Зв'язались" | "Очікує групу") => {
    if (!selected) return;
    setLeadStatusMenuOpen(false);
    setLeadActionsOpen(false);
    void updateStatus(selected.id, status);
  };

  const enrollLeadDirectly = async () => {
    if (!selected || !leadEnrollmentGroupId || leadEnrollmentSaving) return;
    setLeadEnrollmentSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiPost("/enrollments", {
          student_id: selected.id,
          group_id: leadEnrollmentGroupId,
          started_at: localDateInput(new Date()),
        }, session);
        await syncWorkspace(session);
      } else {
        setGroups((items) => items.map((group) => group.id === leadEnrollmentGroupId
          ? { ...group, members: Array.from(new Set([...group.members, selected.id])) }
          : group));
        setLeads((items) => items.map((lead) => lead.id === selected.id ? { ...lead, status: "Зарахований" } : lead));
      }
      setLeadProcedureTarget(null);
      setSelectedId(null);
      setSelectedStudentId(selected.id);
      setActive("Учні");
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зарахувати дитину до групи.");
    } finally {
      setLeadEnrollmentSaving(false);
    }
  };

  const enrollLeadWithoutGroup = async () => {
    if (!selected || leadEnrollmentSaving) return;
    setLeadEnrollmentSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiPost(`/students/${selected.id}/enroll-without-group`, {}, session);
        await syncWorkspace(session);
      } else {
        setLeads((items) => items.map((lead) => lead.id === selected.id ? { ...lead, status: "Зарахований" } : lead));
        setStudentStates((items) => ({ ...items, [selected.id]: "Активний" }));
      }
      setLeadProcedureTarget(null);
      setSelectedId(null);
      setSelectedStudentId(selected.id);
      setActive("Учні");
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зарахувати учня без групи.");
    } finally {
      setLeadEnrollmentSaving(false);
    }
  };

  const toggleCandidate = (id: EntityId) => {
    setSelectedCandidates((ids) => ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);
  };

  const saveStudentPreferences = async () => {
    if (!selected || !session) return;
    setPreferenceSaving(true);
    setWorkspaceError("");
    try {
      await apiPut(`/students/${selected.id}/preferences`, {
        preferred_location_id: preferenceLocationId || null,
        availability: flattenAvailabilityWindows(availabilityWindows),
      }, session);
      await syncWorkspace(session);
      setPreferenceMode(false);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти бажаний графік");
    } finally {
      setPreferenceSaving(false);
    }
  };

  const openGroupCreation = (context: "groups" | "candidates" | "lead") => {
    setGroupCreateContext(context);
    if (context === "groups" || context === "lead") setSelectedCandidates([]);
    setGroupName("");
    setGroupCapacity(8);
    setNewGroupTeacherId("");
    setGroupSchedule([{ weekday: 0, start_time: "17:00", duration_minutes: 60 }]);
    setGroupCreateError("");
    setWorkspaceError("");
    if (activeLocations.length === 1) {
      setGroupLocationId(activeLocations[0].id);
    } else if (!activeLocations.some((location) => location.id === groupLocationId)) {
      setGroupLocationId("");
    }
    setShowGroupForm(true);
  };

  const createLocationFromGroup = () => {
    setGroupCreateError("");
    setLocationEditId(null);
    setLocationName("");
    setLocationAddress("");
    setLocationReturnToGroup(true);
    setShowGroupForm(false);
    setShowLocationForm(true);
  };

  const createGroupFromCandidates = async () => {
    const normalizedGroupName = groupName.trim();
    if (!normalizedGroupName || hasDuplicateSlots(groupSchedule) || selectedCandidates.length > groupCapacity) return;
    const duplicateName = groups.find((group) => group.name.trim().toLocaleLowerCase("uk-UA") === normalizedGroupName.toLocaleLowerCase("uk-UA"));
    if (duplicateName) {
      setGroupCreateError("Група з такою назвою вже існує. Відкрийте її або виберіть іншу назву.");
      return;
    }
    setGroupCreateError("");
    if (apiEnabled && session) {
      try {
        setWorkspaceError("");
        const created = await apiPost<{ group: { id: EntityId }; enrolled_student_ids: EntityId[] }>("/groups/form", {
          name: normalizedGroupName,
          capacity: groupCapacity,
          location_id: groupLocationId || null,
          min_age: null,
          max_age: null,
          student_ids: selectedCandidates,
          schedule_slots: groupSchedule,
        }, session);
        if (newGroupTeacherId && canManageStaff) {
          await apiPost(`/staff/${newGroupTeacherId}/groups`, {
            group_id: created.group.id,
            is_primary: true,
          }, session);
        }
        await syncWorkspace(session);
        if (groupCreateContext === "lead") setLeadEnrollmentGroupId(created.group.id);
        setSelectedCandidates([]);
        setShowGroupForm(false);
        return;
      } catch (error) {
        setGroupCreateError(error instanceof Error ? error.message : "Не вдалося створити групу.");
        return;
      }
    }
    const nextId = crypto.randomUUID();
    setGroups((items) => [...items, {
      id: nextId,
      name: normalizedGroupName,
      ages: "—",
      schedule: scheduleDraftLabel(groupSchedule),
      location: locations.find((location) => location.id === groupLocationId)?.name ?? "Локацію не вказано",
      capacity: groupCapacity,
      members: selectedCandidates,
      teacherName: staff.find((member) => member.id === newGroupTeacherId)?.fullName,
    }]);
    setLeads((items) => items.map((item) => selectedCandidates.includes(item.id) ? { ...item, status: "Зарахований" } : item));
    if (groupCreateContext === "lead") setLeadEnrollmentGroupId(nextId);
    setSelectedCandidates([]);
    setShowGroupForm(false);
  };

  const transferStudent = async () => {
    if (!selectedStudent || transferGroupId === null) return;
    if (apiEnabled && session) {
      try {
        await apiPost(`/students/${selectedStudent.id}/transfer`, { to_group_id: transferGroupId }, session);
        await syncWorkspace(session);
        setTransferGroupId(null);
        return;
      } catch {
        return;
      }
    }
    setGroups((items) => items.map((group) => ({
      ...group,
      members: group.id === transferGroupId
        ? Array.from(new Set([...group.members, selectedStudent.id]))
        : group.members.filter((id) => id !== selectedStudent.id),
    })));
    setTransferGroupId(null);
  };

  const setStudentLifecycle = async (id: EntityId, state: "Активний" | "Пауза" | "Архів") => {
    if (apiEnabled && session) {
      try {
        const value = state === "Пауза" ? "paused" : state === "Архів" ? "archived" : "active";
        await apiPatch(`/students/${id}/status`, { student_status: value }, session);
        await syncWorkspace(session);
        return;
      } catch {
        return;
      }
    }
    setStudentStates((states) => ({ ...states, [id]: state }));
  };

  const deleteSelectedStudent = async () => {
    if (!selectedStudent || studentDeleteSaving) return;
    if (!window.confirm(`Видалити учня «${selectedStudent.child}»? Якщо вже є історія навчання або оплат, CRM не дозволить видалення.`)) return;

    setStudentDeleteSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiDelete(`/students/${selectedStudent.id}`, session);
        await syncWorkspace(session);
      } else {
        setLeads((items) => items.filter((item) => item.id !== selectedStudent.id));
        setGroups((items) => items.map((group) => ({ ...group, members: group.members.filter((id) => id !== selectedStudent.id) })));
      }
      setSelectedStudentId(null);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося видалити учня.");
    } finally {
      setStudentDeleteSaving(false);
    }
  };

  const attendanceDay = addLocalDays(new Date(), attendanceDayOffset);
  const attendanceDayKey = localDateInput(attendanceDay);
  const attendanceTodayKey = localDateInput(new Date());
  const attendanceNow = Date.now();
  const attendanceDayLessons = lessons
    .filter((lesson) => lesson.status !== "cancelled" && localDateInput(new Date(lesson.startsAt)) === attendanceDayKey)
    .sort((a, b) => dateValue(a.startsAt) - dateValue(b.startsAt));
  const pendingAttendanceLessons = attendanceDayLessons.filter((lesson) => lesson.status !== "completed");
  const completedAttendanceLessons = attendanceDayLessons.filter((lesson) => lesson.status === "completed");
  const journalLessons = [...pendingAttendanceLessons, ...completedAttendanceLessons];
  const overdueAttendanceLessons = pendingAttendanceLessons.filter((lesson) => dateValue(lesson.startsAt) + lesson.duration * 60_000 < attendanceNow);
  const inProgressAttendanceLesson = pendingAttendanceLessons.find((lesson) => {
    const start = dateValue(lesson.startsAt);
    const end = start + lesson.duration * 60_000;
    return attendanceDayKey === attendanceTodayKey && start <= attendanceNow && attendanceNow <= end;
  });
  const nextAttendanceLesson = pendingAttendanceLessons.find((lesson) => dateValue(lesson.startsAt) > attendanceNow);
  const nearestAttendanceLesson = inProgressAttendanceLesson ?? nextAttendanceLesson ?? pendingAttendanceLessons[0];
  const attendanceAttentionLesson = overdueAttendanceLessons[0] ?? nearestAttendanceLesson ?? completedAttendanceLessons[0];

  const nearestLesson = [...lessons].sort((a, b) => {
    const now = Date.now();
    return Math.abs(dateValue(a.startsAt) - now) - Math.abs(dateValue(b.startsAt) - now);
  })[0];
  const selectedLesson = apiEnabled && !workspaceLoaded
    ? undefined
    : active === "Відвідування"
      ? journalLessons.find((lesson) => lesson.id === selectedLessonId) ?? attendanceAttentionLesson
      : lessons.find((lesson) => lesson.id === selectedLessonId) ?? nearestLesson;
  const lessonGroup = selectedLesson ? groups.find((group) => group.id === selectedLesson.groupId) : undefined;
  const lessonStudents = lessonGroup
    ? (lessonRoster
        ? lessonRoster.map((student) => leads.find((lead) => lead.id === student.student_id)).filter((lead): lead is Lead => Boolean(lead))
        : leads.filter((lead) => lessonGroup.members.includes(lead.id) && (studentStates[lead.id] ?? "Активний") === "Активний"))
    : [];
  const focusedAttendanceStudent = focusedAttendanceStudentId ? leads.find((lead) => lead.id === focusedAttendanceStudentId) : undefined;
  const focusedAttendanceGroup = focusedAttendanceGroupId ? groups.find((group) => group.id === focusedAttendanceGroupId) : undefined;
  const focusedAttendanceRows = studentAttendanceHistory.filter((row) => !focusedAttendanceGroupId || row.group_id === focusedAttendanceGroupId);
  const focusedAttendanceCounts = focusedAttendanceRows.reduce((acc, row) => {
    acc.total += 1;
    acc[row.status] += 1;
    return acc;
  }, { present: 0, absent: 0, late: 0, excused: 0, total: 0 });
  const focusedAttendanceRate = focusedAttendanceCounts.total
    ? Math.round(((focusedAttendanceCounts.present + focusedAttendanceCounts.late) / focusedAttendanceCounts.total) * 100)
    : 0;

  useEffect(() => {
    if (active !== "Відвідування" || focusedAttendanceStudentId) return;
    if (journalLessons.length === 0) {
      if (selectedLessonId) setSelectedLessonId("");
      return;
    }
    if (!journalLessons.some((lesson) => lesson.id === selectedLessonId)) {
      setSelectedLessonId((attendanceAttentionLesson ?? journalLessons[0]).id);
    }
  }, [active, attendanceDayKey, journalLessons.map((lesson) => lesson.id).join("|"), focusedAttendanceStudentId]);

  useEffect(() => {
    setLessonTopicDraft(selectedLesson?.topic ?? "");
    setLessonNotesDraft(selectedLesson?.notes ?? "");
  }, [selectedLesson?.id, selectedLesson?.topic, selectedLesson?.notes]);

  useEffect(() => {
    setLessonEditing(selectedLesson?.status !== "completed");
  }, [selectedLesson?.id, selectedLesson?.status]);

  useEffect(() => {
    if (!focusedAttendanceStudentId) {
      setStudentAttendanceHistory([]);
      return;
    }
    if (!apiEnabled || !session) {
      const demoRows: ApiStudentAttendanceHistoryItem[] = lessons
        .filter((lesson) => !focusedAttendanceGroupId || lesson.groupId === focusedAttendanceGroupId)
        .flatMap((lesson) => {
          const status = attendance[lesson.id]?.[focusedAttendanceStudentId];
          if (!status) return [];
          return [{
            session_id: lesson.id,
            group_id: lesson.groupId,
            group_name: groups.find((group) => group.id === lesson.groupId)?.name ?? "Група",
            starts_at: lesson.startsAt,
            duration_minutes: lesson.duration,
            topic: lesson.topic ?? null,
            lesson_status: lesson.status ?? "scheduled",
            status,
            note: attendanceNotes[lesson.id]?.[focusedAttendanceStudentId] ?? null,
          }];
        })
        .sort((a, b) => dateValue(b.starts_at) - dateValue(a.starts_at));
      setStudentAttendanceHistory(demoRows);
      return;
    }
    let cancelled = false;
    setStudentAttendanceHistoryLoading(true);
    loadStudentAttendanceHistory(focusedAttendanceStudentId, session)
      .then((rows) => { if (!cancelled) setStudentAttendanceHistory(rows); })
      .catch((error) => {
        if (!cancelled) {
          setStudentAttendanceHistory([]);
          setWorkspaceError(error instanceof Error ? error.message : "Не вдалося завантажити історію відвідування.");
        }
      })
      .finally(() => { if (!cancelled) setStudentAttendanceHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [focusedAttendanceStudentId, focusedAttendanceGroupId, session?.accessToken, session?.organizationId]);

  useEffect(() => {
    if (!apiEnabled || !session || !selectedLesson?.groupId) {
      setLessonRoster(null);
      return;
    }
    let cancelled = false;
    setLessonRosterLoading(true);
    loadGroupRoster(selectedLesson.groupId, session)
      .then((rows) => {
        if (!cancelled) setLessonRoster(rows);
      })
      .catch((error) => {
        if (!cancelled) {
          setLessonRoster(null);
          setWorkspaceError(error instanceof Error ? error.message : "Не вдалося завантажити список учнів групи.");
        }
      })
      .finally(() => {
        if (!cancelled) setLessonRosterLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedLesson?.groupId, session?.accessToken, session?.organizationId]);

  useEffect(() => {
    if (!apiEnabled || !session || !selectedLesson?.id) return;
    let cancelled = false;
    setAttendanceLoading(true);
    loadAttendance(selectedLesson.id, session)
      .then((rows) => {
        if (cancelled) return;
        const mapped: Record<EntityId, AttendanceValue> = {};
        const mappedNotes: Record<EntityId, string> = {};
        rows.forEach((row) => {
          mapped[row.student_id] = row.status;
          if (row.note) mappedNotes[row.student_id] = row.note;
        });
        setAttendance((all) => ({ ...all, [selectedLesson.id]: mapped }));
        setAttendanceNotes((all) => ({ ...all, [selectedLesson.id]: mappedNotes }));
      })
      .catch((error) => {
        if (!cancelled) setWorkspaceError(error instanceof Error ? error.message : "Не вдалося завантажити відвідування");
      })
      .finally(() => {
        if (!cancelled) setAttendanceLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedLesson?.id, session?.accessToken, session?.organizationId]);

  const markAttendance = (studentId: EntityId, value: AttendanceValue) => {
    if (!selectedLesson) return;
    setAttendance((all) => ({
      ...all,
      [selectedLesson.id]: { ...(all[selectedLesson.id] ?? {}), [studentId]: value },
    }));
  };

  const setAttendanceNote = (studentId: EntityId, note: string) => {
    if (!selectedLesson) return;
    setAttendanceNotes((all) => ({
      ...all,
      [selectedLesson.id]: { ...(all[selectedLesson.id] ?? {}), [studentId]: note },
    }));
  };

  const markAllPresent = () => {
    if (!selectedLesson) return;
    const next: Record<EntityId, AttendanceValue> = {};
    lessonStudents.forEach((student) => { next[student.id] = "present"; });
    setAttendance((all) => ({ ...all, [selectedLesson.id]: next }));
    setAttendanceNotes((all) => ({ ...all, [selectedLesson.id]: {} }));
  };

  const markUnmarkedAbsent = () => {
    if (!selectedLesson) return;
    setAttendance((all) => {
      const current = { ...(all[selectedLesson.id] ?? {}) };
      lessonStudents.forEach((student) => {
        if (!current[student.id]) current[student.id] = "absent";
      });
      return { ...all, [selectedLesson.id]: current };
    });
  };

  const createGroupSchedule = async () => {
    if (!scheduleGroupId) return;
    if (apiEnabled && session) {
      try {
        await apiPost("/group-schedules", {
          group_id: scheduleGroupId,
          weekday: scheduleWeekday,
          start_time: scheduleTime,
          duration_minutes: scheduleDuration,
        }, session);
        await syncWorkspace(session);
        return;
      } catch {
        return;
      }
    }

    setGroups((items) => items.map((group) => group.id === scheduleGroupId ? {
      ...group,
      schedule: group.schedule === "Розклад не задано"
        ? `${SCHEDULE_DAY_NAMES[scheduleWeekday]} · ${scheduleTime}`
        : `${group.schedule}; ${SCHEDULE_DAY_NAMES[scheduleWeekday]} · ${scheduleTime}`,
    } : group));
  };

  const createLesson = async () => {
    if (!newLessonGroupId) return;
    if (apiEnabled && session) {
      try {
        const created = await apiPost<{ id: string }>("/lesson-sessions", {
          group_id: newLessonGroupId,
          starts_at: new Date(newLessonAt).toISOString(),
          duration_minutes: newLessonDuration,
          topic: newLessonTopic.trim() || "Заняття",
        }, session);
        await syncWorkspace(session);
        setSelectedLessonId(created.id);
        setActive("Відвідування");
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося створити заняття.");
        return;
      }
    }

    const newStart = new Date(newLessonAt).getTime();
    const newEnd = newStart + newLessonDuration * 60_000;
    const overlap = lessons.find((lesson) => {
      if (lesson.status === "cancelled") return false;
      const existingStart = new Date(lesson.startsAt).getTime();
      const existingEnd = existingStart + lesson.duration * 60_000;
      return lesson.groupId === newLessonGroupId && newStart < existingEnd && newEnd > existingStart;
    });
    if (overlap) {
      setWorkspaceError("Час зайнятий: у цієї групи вже є заняття, яке перетинається з вибраним часом.");
      return;
    }

    const nextId = crypto.randomUUID();
    setLessons((items) => [...items, {
      id: nextId,
      groupId: newLessonGroupId,
      startsAt: newLessonAt,
      duration: newLessonDuration,
      topic: newLessonTopic.trim() || "Заняття",
    }]);
    setSelectedLessonId(nextId);
    setActive("Відвідування");
  };

  const saveLessonDetails = async () => {
    if (!selectedLesson || lessonDetailsSaving) return;
    const topic = lessonTopicDraft.trim() || "Заняття";
    const notes = lessonNotesDraft.trim();
    setLessonDetailsSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiPatch(`/lesson-sessions/${selectedLesson.id}`, {
          topic,
          notes: notes || null,
        }, session);
        await syncWorkspace(session);
      } else {
        setLessons((items) => items.map((lesson) => lesson.id === selectedLesson.id ? { ...lesson, topic, notes: notes || undefined } : lesson));
      }
      setLessonSaveNotice("details");
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти дані заняття.");
    } finally {
      setLessonDetailsSaving(false);
    }
  };

  const saveAttendance = async () => {
    if (!selectedLesson) return;
    const nextLessonAfterSave = pendingAttendanceLessons.find((lesson) =>
      lesson.id !== selectedLesson.id && dateValue(lesson.startsAt) >= dateValue(selectedLesson.startsAt)
    ) ?? pendingAttendanceLessons.find((lesson) => lesson.id !== selectedLesson.id);
    if (lessonStudents.length === 0) {
      setWorkspaceError("У цій групі немає активних учнів, тому відвідування зберігати не потрібно. Додайте учнів до групи або відкрийте інше заняття.");
      return;
    }
    const lessonMarks = attendance[selectedLesson.id] ?? {};
    const unmarked = lessonStudents.filter((student) => !lessonMarks[student.id]);
    if (unmarked.length) {
      setWorkspaceError(`Не відмічено: ${unmarked.map((student) => student.child).join(", ")}. Позначте кожного учня.`);
      return;
    }
    if (apiEnabled && session) {
      setAttendanceSaving(true);
      try {
        await apiPut(`/lesson-sessions/${selectedLesson.id}/attendance`, {
          items: lessonStudents.map((student) => ({
            student_id: student.id,
            status: lessonMarks[student.id],
            note: attendanceNotes[selectedLesson.id]?.[student.id]?.trim() || null,
            consume_lesson: lessonMarks[student.id] === "absent" ? (attendanceConsume[selectedLesson.id]?.[student.id] ?? false) : null,
          })),
        }, session);
        await syncWorkspace(session);
        setLessonEditing(false);
        if (nextLessonAfterSave) setSelectedLessonId(nextLessonAfterSave.id);
        setLessonSaveNotice("attendance");
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти відвідування.");
        return;
      } finally {
        setAttendanceSaving(false);
      }
      return;
    }
  };

  const openGroup = async (groupId: EntityId) => {
    setSelectedGroupId(groupId);
    setGroupDetail(null);
    setShowGroupCandidatePicker(false);
    setGroupCandidateId("");
    setSelectedGroupTeacherId(groupTeacher(groupId)?.id ?? "");
    setGroupTeacherEditing(false);
    setGroupEditing(false);
    setGroupEditError("");
    if (!apiEnabled || !session) return;
    setGroupDetailLoading(true);
    try {
      setGroupDetail(await loadGroupDetail(groupId, session));
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося завантажити групу.");
    } finally {
      setGroupDetailLoading(false);
    }
  };

  const beginGroupEdit = () => {
    if (!selectedGroupId) return;
    const source = groupDetail?.group;
    setGroupEditName(source?.name ?? selectedGroup?.name ?? "");
    setGroupEditCapacity(source?.capacity ?? selectedGroup?.capacity ?? 8);
    setGroupEditLocationId(source?.location_id ?? "");
    setGroupEditTeacherId(groupTeacher(selectedGroupId)?.id ?? "");
    setGroupEditSchedule((groupDetail?.schedules ?? []).map((slot) => ({
      weekday: slot.weekday,
      start_time: slot.start_time.slice(0, 5),
      duration_minutes: slot.duration_minutes,
    })));
    setGroupEditError("");
    setGroupTeacherEditing(false);
    setGroupEditing(true);
  };

  const persistGroupTeacher = async (groupId: EntityId, teacherId: EntityId | "") => {
    if (!session) return;
    const currentlyAssigned = staff.filter((member) => member.groupIds.includes(groupId));
    for (const teacher of currentlyAssigned) {
      if (teacher.id !== teacherId) {
        await apiDelete(`/staff/${teacher.id}/groups/${groupId}`, session);
      }
    }
    if (teacherId && !currentlyAssigned.some((teacher) => teacher.id === teacherId)) {
      await apiPost(`/staff/${teacherId}/groups`, {
        group_id: groupId,
        is_primary: true,
      }, session);
    }
  };

  const saveGroupEdit = async () => {
    if (!selectedGroupId || groupEditSaving) return;
    const normalizedName = groupEditName.trim();
    const memberCount = groupDetail?.members.length ?? selectedGroup?.members.length ?? 0;
    if (!normalizedName) {
      setGroupEditError("Вкажіть назву групи.");
      return;
    }
    if (groupEditCapacity < Math.max(1, memberCount)) {
      setGroupEditError(`Місткість не може бути меншою за кількість учасників (${memberCount}).`);
      return;
    }
    if (hasDuplicateSlots(groupEditSchedule)) {
      setGroupEditError("Приберіть однакові дні та години в розкладі.");
      return;
    }

    setGroupEditSaving(true);
    setGroupEditError("");
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiPut(`/groups/${selectedGroupId}`, {
          name: normalizedName,
          capacity: groupEditCapacity,
          location_id: groupEditLocationId || null,
          min_age: groupDetail?.group.min_age ?? null,
          max_age: groupDetail?.group.max_age ?? null,
          schedule_slots: groupEditSchedule,
        }, session);
        await persistGroupTeacher(selectedGroupId, groupEditTeacherId);
        await syncWorkspace(session);
        setGroupDetail(await loadGroupDetail(selectedGroupId, session));
        setSelectedGroupTeacherId(groupEditTeacherId);
      } else {
        setGroups((items) => items.map((group) => group.id === selectedGroupId ? {
          ...group,
          name: normalizedName,
          capacity: groupEditCapacity,
          location: locations.find((location) => location.id === groupEditLocationId)?.name ?? "Локація не вказана",
          schedule: scheduleDraftLabel(groupEditSchedule),
          teacherName: staff.find((member) => member.id === groupEditTeacherId)?.fullName,
        } : group));
      }
      setGroupEditing(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Не вдалося зберегти зміни групи.";
      setGroupEditError(message);
      setWorkspaceError(message);
    } finally {
      setGroupEditSaving(false);
    }
  };

  const deleteSelectedGroup = async () => {
    if (!selectedGroupId || groupDeleteSaving) return;
    const groupName = groupDetail?.group.name ?? selectedGroup?.name ?? "Група";
    if (!window.confirm(`Видалити групу «${groupName}»? Вона зникне з активних груп, але історія занять залишиться в CRM.`)) return;

    setGroupDeleteSaving(true);
    setGroupEditError("");
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiDelete(`/groups/${selectedGroupId}`, session);
        await syncWorkspace(session);
      } else {
        setGroups((items) => items.filter((group) => group.id !== selectedGroupId));
      }
      closeGroupDetail();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Не вдалося видалити групу.";
      setGroupEditError(message);
      setWorkspaceError(message);
    } finally {
      setGroupDeleteSaving(false);
    }
  };

  const addCandidateToExistingGroup = async (candidateId?: EntityId) => {
    const targetId = candidateId || groupCandidateId;
    if (!selectedGroupId || !targetId || groupCandidateSaving) return;
    const candidate = leads.find((lead) => lead.id === targetId);
    if (!candidate) return;
    setGroupCandidateSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiPost("/enrollments", {
          student_id: targetId,
          group_id: selectedGroupId,
          started_at: localDateInput(new Date()),
        }, session);
        await syncWorkspace(session);
        setGroupDetail(await loadGroupDetail(selectedGroupId, session));
      } else {
        setGroups((items) => items.map((group) => group.id === selectedGroupId ? { ...group, members: Array.from(new Set([...group.members, targetId])) } : group));
        setLeads((items) => items.map((lead) => lead.id === targetId ? { ...lead, status: "Зарахований" } : lead));
      }
      setGroupCandidateId("");
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося додати учня до групи.");
    } finally {
      setGroupCandidateSaving(false);
    }
  };

  const assignTeacherToSelectedGroup = async () => {
    if (!selectedGroupId || groupTeacherSaving || !session) return;
    setGroupTeacherSaving(true);
    setWorkspaceError("");
    try {
      await persistGroupTeacher(selectedGroupId, selectedGroupTeacherId);
      await syncWorkspace(session);
      setGroupTeacherEditing(false);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося призначити викладача.");
    } finally {
      setGroupTeacherSaving(false);
    }
  };

  const markReminderHandled = async (reminder: ApiPaymentReminder) => {
    if (!session || reminderSavingId) return;
    setReminderSavingId(reminder.payment_id);
    try {
      await recordPaymentReminder(reminder.payment_id, reminder.stage, "phone", session);
      setPaymentReminders(await loadPaymentReminders(session));
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зафіксувати нагадування.");
    } finally {
      setReminderSavingId(null);
    }
  };

  const markPaymentPaid = async (id: EntityId) => {
    if (apiEnabled && session) {
      try {
        await apiPatch(`/payments/${id}/paid`, { method: "card" }, session);
        await syncWorkspace(session);
        return;
      } catch {
        return;
      }
    }
    setPayments((items) => items.map((item) => item.id === id ? { ...item, status: "paid", method: "Картка" } : item));
  };

  const openPaymentForm = () => {
    const nextStudentId = activeStudents.some((student) => student.id === paymentStudentId)
      ? paymentStudentId
      : (activeStudents[0]?.id ?? "");
    const nextPlanId = plans.some((plan) => plan.id === paymentPlanId && plan.isActive && plan.price > 0)
      ? paymentPlanId
      : (plans.find((plan) => plan.isActive && plan.price > 0)?.id ?? "");

    setPaymentStudentId(nextStudentId);
    setPaymentPlanId(nextPlanId);
    setPaymentDueDate((current) => current && current >= localDateInput(new Date()) ? current : defaultPaymentDueDate());
    setWorkspaceError("");
    setShowPaymentForm(true);
  };

  const goToPayment = (paymentId: EntityId) => {
    setFocusedPaymentId(paymentId);
    setActive("Оплати");
    window.setTimeout(() => {
      document.getElementById("payment-" + paymentId)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
  };

  const goToLesson = (lessonId: EntityId) => {
    const target = lessons.find((lesson) => lesson.id === lessonId);
    if (target) setAttendanceDayOffset(dayOffsetForDate(target.startsAt));
    setSelectedLessonId(lessonId);
    setFocusedAttendanceStudentId(null);
    setFocusedAttendanceGroupId(null);
    setActive("Відвідування");
  };

  const goToGroup = (groupId: EntityId) => {
    setActive("Групи");
    void openGroup(groupId);
  };

  const closeGroupDetail = () => {
    setSelectedGroupId(null);
    setGroupDetail(null);
    setShowGroupCandidatePicker(false);
    setGroupCandidateId("");
    setGroupTeacherEditing(false);
    setGroupEditing(false);
    setGroupEditError("");
  };

  const goToStudentAttendance = (studentId: EntityId, groupId: EntityId) => {
    setFocusedAttendanceStudentId(studentId);
    setFocusedAttendanceGroupId(groupId);
    closeGroupDetail();
    setActive("Відвідування");
  };

  const goToStudentPayments = (studentId: EntityId, preferredId?: EntityId) => {
    const studentPayments = payments.filter((payment) => payment.studentId === studentId).sort((a, b) => dateValue(b.dueDate) - dateValue(a.dueDate));
    const paymentId = preferredId ?? studentPayments.find((payment) => payment.balanceAmount > 0)?.id ?? studentPayments[0]?.id;
    closeGroupDetail();
    setActive("Оплати");
    if (paymentId) {
      setFocusedPaymentId(paymentId);
      window.setTimeout(() => document.getElementById("payment-" + paymentId)?.scrollIntoView({ behavior: "smooth", block: "center" }), 120);
    }
  };

  const createPayment = async () => {
    if (!paymentStudentId || !activeStudents.some((student) => student.id === paymentStudentId)) {
      setWorkspaceError("Оберіть учня для нарахування.");
      return;
    }
    const plan = plans.find((item) => item.id === paymentPlanId);
    if (!plan || !plan.isActive || plan.price <= 0) {
      setWorkspaceError("Для нарахування оберіть активний тариф із заданою ціною.");
      return;
    }
    if (apiEnabled && session) {
      if (paymentSaving) return;
      setPaymentSaving(true);
      try {
        setWorkspaceError("");
        await apiPost("/billing/charges", {
          student_id: paymentStudentId,
          plan_id: paymentPlanId,
          group_id: studentGroup(paymentStudentId)?.id ?? null,
          starts_on: localDateInput(new Date()),
          due_date: paymentDueDate || null,
          discount_minor: 0,
          note: plan.name,
          auto_renew: paymentAutoRenew,
        }, session);
        await syncWorkspace(session);
        setShowPaymentForm(false);
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося створити нарахування.");
        return;
      } finally {
        setPaymentSaving(false);
      }
    }
    const nextId = crypto.randomUUID();
    setPayments((items) => [...items, {
      id: nextId,
      studentId: paymentStudentId,
      planId: paymentPlanId,
      amount: plan.price,
      adjustedAmount: plan.price,
      paidAmount: 0,
      refundedAmount: 0,
      balanceAmount: plan.price,
      creditAmount: 0,
      dueDate: paymentDueDate,
      status: "pending",
    }]);
    setShowPaymentForm(false);
  };

  const openPaymentAction = (payment: PaymentDemo, type: "partial" | "refund" | "adjustment") => {
    setPaymentActionId(payment.id);
    setPaymentActionType(type);
    setPaymentActionReason("");
    setPaymentAdjustmentDirection("decrease");
    const maxAmount = type === "refund"
      ? Math.max(0, payment.paidAmount - payment.refundedAmount)
      : type === "partial"
        ? payment.balanceAmount
        : Math.min(payment.adjustedAmount, payment.balanceAmount || payment.adjustedAmount);
    setPaymentActionAmount(maxAmount > 0 ? String(maxAmount) : "");
  };

  const submitPaymentAction = async () => {
    if (!session || !paymentActionId || !paymentActionType || paymentActionSaving) return;
    const amount = Number(paymentActionAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setWorkspaceError("Вкажіть коректну суму.");
      return;
    }
    setPaymentActionSaving(true);
    try {
      setWorkspaceError("");
      const amount_minor = Math.round(amount * 100);
      if (paymentActionType === "partial") {
        await apiPost(`/payments/${paymentActionId}/receipts`, {
          amount_minor,
          method: paymentActionMethod,
          note: paymentActionReason.trim() || "Часткова оплата",
        }, session);
      } else if (paymentActionType === "refund") {
        await apiPost(`/payments/${paymentActionId}/refunds`, {
          amount_minor,
          note: paymentActionReason.trim() || "Повернення коштів",
          reduce_charge: true,
        }, session);
      } else {
        await apiPost(`/payments/${paymentActionId}/adjustments`, {
          direction: paymentAdjustmentDirection,
          amount_minor,
          reason: paymentActionReason.trim() || "Коригування нарахування",
        }, session);
      }
      await syncWorkspace(session);
      setPaymentActionId(null);
      setPaymentActionType(null);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося виконати фінансову операцію.");
    } finally {
      setPaymentActionSaving(false);
    }
  };

  const toggleAutoRenew = async (subscriptionId: EntityId, next: boolean) => {
    if (!session) return;
    try {
      await apiPatch(`/student-subscriptions/${subscriptionId}/auto-renew`, { auto_renew: next }, session);
      await syncWorkspace(session);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося змінити автопродовження.");
    }
  };

  const openPauseSubscription = (subscriptionId: EntityId) => {
    setPauseSubscriptionId(subscriptionId);
    setPauseStart(localDateInput(new Date()));
    setPauseResumeOn("");
    setPauseNote("");
  };

  const submitPauseSubscription = async () => {
    if (!session || !pauseSubscriptionId) return;
    try {
      await apiPost(`/student-subscriptions/${pauseSubscriptionId}/pause`, {
        starts_on: pauseStart,
        resume_on: pauseResumeOn || null,
        note: pauseNote.trim() || null,
      }, session);
      await syncWorkspace(session);
      setPauseSubscriptionId(null);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося поставити абонемент на паузу.");
    }
  };

  const resumeSubscriptionNow = async (subscriptionId: EntityId) => {
    if (!session) return;
    try {
      await apiPost(`/student-subscriptions/${subscriptionId}/resume`, { resumes_on: localDateInput(new Date()) }, session);
      await syncWorkspace(session);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося відновити абонемент.");
    }
  };

  const openPlanCreate = () => {
    setPlanEditId(null);
    setPlanName("");
    setPlanPrice("");
    setPlanDays("30");
    setPlanLessons("8");
    setPlanActive(true);
    setPlanHistory([]);
    setPlanHistoryOpen(false);
    setWorkspaceError("");
    setShowPlanForm(true);
  };

  const openPlanEdit = async (plan: PlanDemo) => {
    setPlanEditId(plan.id);
    setPlanName(plan.name);
    setPlanPrice(String(plan.price));
    setPlanDays(plan.days ? String(plan.days) : "");
    setPlanLessons(plan.lessons ? String(plan.lessons) : "");
    setPlanActive(plan.isActive);
    setPlanHistory([]);
    setPlanHistoryOpen(false);
    setWorkspaceError("");
    setShowPlanForm(true);
  };

  const loadPlanHistory = async () => {
    if (!session || !planEditId || planHistoryLoading) return;
    setPlanHistoryLoading(true);
    try {
      setPlanHistory(await loadAuditEvents("subscription_plan", planEditId, session));
      setPlanHistoryOpen(true);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося завантажити історію тарифу.");
    } finally {
      setPlanHistoryLoading(false);
    }
  };

  const savePlan = async () => {
    const parsedPrice = planPrice === "" ? Number.NaN : Number(planPrice);
    const parsedDays = planDays === "" ? null : Number(planDays);
    const parsedLessons = planLessons === "" ? null : Number(planLessons);
    if (!planName.trim() || !Number.isFinite(parsedPrice) || parsedPrice < 0) {
      setWorkspaceError("Вкажіть назву та коректну ціну тарифу.");
      return;
    }
    if (parsedDays !== null && (!Number.isInteger(parsedDays) || parsedDays < 1 || parsedDays > 366)) {
      setWorkspaceError("Кількість днів має бути цілим числом від 1 до 366.");
      return;
    }
    if (parsedLessons !== null && (!Number.isInteger(parsedLessons) || parsedLessons < 1 || parsedLessons > 365)) {
      setWorkspaceError("Кількість відвідувань має бути цілим числом від 1 до 365.");
      return;
    }
    if (parsedDays === null && parsedLessons === null) {
      setWorkspaceError("Вкажіть дні, відвідування або обидва значення.");
      return;
    }
    if (planSaving) return;
    setPlanSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        const payload = {
          name: planName.trim(),
          price_minor: Math.round(parsedPrice * 100),
          period_days: parsedDays,
          lessons_included: parsedLessons,
          ...(planEditId ? { is_active: planActive } : {}),
        };
        if (planEditId) {
          await apiPut(`/subscription-plans/${planEditId}`, payload, session);
        } else {
          await apiPost("/subscription-plans", payload, session);
        }
        await syncWorkspace(session);
      } else if (planEditId) {
        setPlans((items) => items.map((item) => item.id === planEditId ? {
          ...item,
          name: planName.trim(),
          price: parsedPrice,
          days: parsedDays,
          lessons: parsedLessons,
          isActive: planActive,
        } : item));
      } else {
        setPlans((items) => [...items, {
          id: crypto.randomUUID(),
          name: planName.trim(),
          price: parsedPrice,
          days: parsedDays,
          lessons: parsedLessons,
          isActive: true,
        }]);
      }
      setShowPlanForm(false);
      setPlanEditId(null);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти тариф.");
    } finally {
      setPlanSaving(false);
    }
  };

  const openPlanChange = (subscriptionId: EntityId) => {
    const subscription = subscriptions.find((item) => item.id === subscriptionId);
    if (!subscription) return;
    const nextPlan = plans.find((plan) => plan.isActive && plan.id !== subscription.plan_id);
    if (!nextPlan) {
      setWorkspaceError("Немає іншого активного тарифу для переходу.");
      return;
    }
    setPlanChangeSubscriptionId(subscriptionId);
    setPlanChangePlanId(nextPlan.id);
    setPlanChangeReason("");
    setPlanChangeResult("");
  };

  const submitPlanChange = async () => {
    if (!session || !planChangeSubscriptionId || !planChangePlanId || !planChangeReason.trim() || planChangeSaving) return;
    setPlanChangeSaving(true);
    setWorkspaceError("");
    try {
      const result = await apiPost<{
        current_period_charge_minor: number;
        credit_minor: number;
        debt_minor: number;
        used_lessons: number;
        old_unit_price_minor: number | null;
        new_unit_price_minor: number | null;
      }>(`/student-subscriptions/${planChangeSubscriptionId}/change-plan`, {
        plan_id: planChangePlanId,
        reason: planChangeReason.trim(),
      }, session);
      await syncWorkspace(session);
      const details = result.credit_minor > 0
        ? `Кредит на балансі: ${money(result.credit_minor / 100)}. Він автоматично піде в наступний період.`
        : result.debt_minor > 0
          ? `До доплати: ${money(result.debt_minor / 100)}.`
          : "Баланс закритий без переплати чи боргу.";
      setPlanChangeResult(`Тариф змінено. Поточний період: ${money(result.current_period_charge_minor / 100)}. ${details}`);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося змінити тариф.");
    } finally {
      setPlanChangeSaving(false);
    }
  };

  const paymentTotals = {
    paid: payments.reduce((sum, x) => sum + Math.max(0, x.paidAmount - x.refundedAmount), 0),
    pending: payments.filter((x) => x.status === "pending" || x.status === "overdue").reduce((sum, x) => sum + x.balanceAmount, 0),
    overdue: payments.filter((x) => x.status === "overdue").reduce((sum, x) => sum + x.balanceAmount, 0),
  };

  const attendanceValues = Object.values(attendance).flatMap((lesson) => Object.values(lesson));
  const attendanceStats = {
    present: attendanceValues.filter((x) => x === "present").length,
    late: attendanceValues.filter((x) => x === "late").length,
    absent: attendanceValues.filter((x) => x === "absent").length,
    excused: attendanceValues.filter((x) => x === "excused").length,
  };
  const localAttendanceRate = attendanceValues.length
    ? Math.round((attendanceStats.present + attendanceStats.late) / attendanceValues.length * 100)
    : 0;
  const attendanceRate = overviewReport?.attendance.attendance_rate ?? localAttendanceRate;
  const totalCapacity = overviewReport?.group_capacity ?? groups.reduce((sum, group) => sum + group.capacity, 0);
  const occupiedSeats = overviewReport?.enrolled_students ?? groups.reduce((sum, group) => sum + group.members.length, 0);
  const occupancy = totalCapacity ? Math.round(occupiedSeats / totalCapacity * 100) : 0;

  const selectedStaff = staff.find((item) => item.id === selectedStaffId) ?? null;
  const selectedGroup = groups.find((item) => item.id === selectedGroupId) ?? null;
  const activeTeachers = staff.filter((member) => member.canTeach && member.isActive);
  const groupTeacher = (groupId: EntityId) => activeTeachers.find((member) => member.groupIds.includes(groupId));
  const selectedTeacher = selectedGroupId ? groupTeacher(selectedGroupId) : undefined;
  const existingGroupCandidates = useMemo(() => {
    if (!selectedGroupId) return [];
    const memberIds = new Set(groupDetail?.members.map((member) => member.student_id) ?? selectedGroup?.members ?? []);
    return leads
      .filter((lead) => !memberIds.has(lead.id) && (lead.status === "Після пробного" || lead.status === "Очікує групу"))
      .sort((a, b) => {
        if (a.status !== b.status) return a.status === "Очікує групу" ? -1 : 1;
        return a.child.localeCompare(b.child, "uk-UA");
      });
  }, [leads, selectedGroupId, selectedGroup?.members, groupDetail?.members]);

  const createStaffMember = async () => {
    const nameError = personNameError(staffName, "Ім’я та прізвище");
    const mailError = emailError(staffEmail);
    const phoneError = uaPhoneError(staffPhone, false);
    if (nameError || mailError || phoneError) {
      setWorkspaceError(nameError || mailError || phoneError);
      return;
    }
    if (!staffEmail.trim() && !staffPhone.trim()) {
      setWorkspaceError("Вкажіть email або телефон працівника.");
      return;
    }
    const normalizedStaffPhone = staffPhone.trim() ? normalizeUaPhone(staffPhone) : null;
    if (apiEnabled && session) {
      try {
        await apiPost("/staff", {
          full_name: cleanSpaces(staffName),
          role: staffRoleValue(staffRole),
          can_teach: staffCanTeach || staffRole === "Викладач",
          email: staffEmail.trim().toLowerCase() || null,
          phone: normalizedStaffPhone,
          location_ids: locations[0] ? [locations[0].id] : [],
        }, session);
        await syncWorkspace(session);
        setStaffName("");
        setStaffEmail("");
        setStaffPhone("");
        setStaffCanTeach(true);
        setShowStaffForm(false);
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося додати працівника.");
        return;
      }
    }
    const nextId = crypto.randomUUID();
    setStaff((items) => [...items, {
      id: nextId,
      fullName: cleanSpaces(staffName),
      role: staffRole,
      canTeach: staffCanTeach || staffRole === "Викладач",
      email: staffEmail.trim().toLowerCase(),
      phone: normalizedStaffPhone ? formatUaPhone(normalizedStaffPhone) : "",
      locationIds: locations[0] ? [locations[0].id] : [],
      groupIds: [],
      isActive: true,
    }]);
    setStaffName("");
    setStaffEmail("");
    setStaffPhone("");
    setStaffCanTeach(true);
    setShowStaffForm(false);
  };

  const createStaffPasswordReset = async () => {
    if (!session || !selectedStaff?.email) return;
    try {
      const result = await apiPost<{ reset_token: string }>("/password-reset-links", {
        email: selectedStaff.email,
      }, session);
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("reset", result.reset_token);
      setStaffResetLink(url.toString());
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося створити посилання для скидання пароля");
    }
  };

  const createInvitation = async () => {
    if (!session) return;
    const validation = emailError(inviteEmail, true);
    if (validation) {
      setWorkspaceError(validation);
      return;
    }
    try {
      const result = await apiPost<{ invite_token: string }>("/organization-invitations", {
        email: inviteEmail.trim().toLowerCase(),
        role: staffRoleValue(inviteRole),
        can_teach: inviteCanTeach || inviteRole === "Викладач",
      }, session);
      const url = new URL(window.location.href);
      url.searchParams.set("invite", result.invite_token);
      setInviteLink(url.toString());
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося створити запрошення.");
      return;
    }
  };

  const openLocationCreation = () => {
    setLocationEditId(null);
    setLocationName("");
    setLocationAddress("");
    setLocationReturnToGroup(false);
    setWorkspaceError("");
    setShowLocationForm(true);
  };

  const openLocationEdit = (location: LocationDemo) => {
    setLocationEditId(location.id);
    setLocationName(location.name);
    setLocationAddress(location.address);
    setLocationReturnToGroup(false);
    setWorkspaceError("");
    setShowLocationForm(true);
  };

  const closeLocationForm = () => {
    setShowLocationForm(false);
    setLocationEditId(null);
    setLocationName("");
    setLocationAddress("");
    if (locationReturnToGroup) {
      setLocationReturnToGroup(false);
      setShowGroupForm(true);
    }
  };

  const saveLocationDemo = async () => {
    if (!locationName.trim() || locationSaving) return;
    setLocationSaving(true);
    try {
      if (apiEnabled && session) {
        setWorkspaceError("");
        if (locationEditId) {
          await apiPatch(`/locations/${locationEditId}`, {
            name: locationName.trim(),
            address: locationAddress.trim() || null,
          }, session);
          await syncWorkspace(session);
          closeLocationForm();
          return;
        }

        const created = await apiPost<{ id: EntityId; name: string }>("/locations", {
          name: locationName.trim(),
          address: locationAddress.trim() || null,
        }, session);
        await syncWorkspace(session);
        setLocationName("");
        setLocationAddress("");
        setShowLocationForm(false);
        if (locationReturnToGroup) {
          setGroupLocationId(created.id);
          setLocationReturnToGroup(false);
          setShowGroupForm(true);
        }
        return;
      }

      if (locationEditId) {
        setLocations((items) => items.map((item) => item.id === locationEditId ? {
          ...item,
          name: locationName.trim(),
          address: locationAddress.trim(),
        } : item));
        closeLocationForm();
        return;
      }

      const nextId = crypto.randomUUID();
      setLocations((items) => [...items, {
        id: nextId,
        name: locationName.trim(),
        address: locationAddress.trim(),
        isActive: true,
      }]);
      setLocationName("");
      setLocationAddress("");
      setShowLocationForm(false);
      if (locationReturnToGroup) {
        setGroupLocationId(nextId);
        setLocationReturnToGroup(false);
        setShowGroupForm(true);
      }
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : locationEditId ? "Не вдалося зберегти локацію." : "Не вдалося створити локацію.");
    } finally {
      setLocationSaving(false);
    }
  };

  const deleteLocationDemo = async () => {
    if (!locationEditId || locationDeleteSaving) return;
    const location = locations.find((item) => item.id === locationEditId);
    if (!window.confirm(`Видалити локацію «${location?.name ?? "Локація"}»? Історичні дані залишаться в CRM.`)) return;

    setLocationDeleteSaving(true);
    setWorkspaceError("");
    try {
      if (apiEnabled && session) {
        await apiDelete(`/locations/${locationEditId}`, session);
        await syncWorkspace(session);
      } else {
        setLocations((items) => items.filter((item) => item.id !== locationEditId));
        setStaff((items) => items.map((member) => ({ ...member, locationIds: member.locationIds.filter((id) => id !== locationEditId) })));
      }
      closeLocationForm();
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося видалити локацію.");
    } finally {
      setLocationDeleteSaving(false);
    }
  };

  const toggleStaffLocation = async (staffId: EntityId, locationId: EntityId) => {
    const member = staff.find((item) => item.id === staffId);
    if (!member) return;
    const nextIds = member.locationIds.includes(locationId)
      ? member.locationIds.filter((id) => id !== locationId)
      : [...member.locationIds, locationId];

    if (apiEnabled && session) {
      try {
        await apiPut(`/staff/${staffId}/locations`, { location_ids: nextIds }, session);
        await syncWorkspace(session);
        return;
      } catch {
        return;
      }
    }

    setStaff((items) => items.map((item) => item.id !== staffId ? item : { ...item, locationIds: nextIds }));
  };

  const toggleStaffGroup = async (staffId: EntityId, groupId: EntityId) => {
    const member = staff.find((item) => item.id === staffId);
    if (!member) return;
    const hasGroup = member.groupIds.includes(groupId);

    if (apiEnabled && session) {
      try {
        if (hasGroup) {
          await apiDelete(`/staff/${staffId}/groups/${groupId}`, session);
        } else {
          await apiPost(`/staff/${staffId}/groups`, { group_id: groupId, is_primary: false }, session);
        }
        await syncWorkspace(session);
        return;
      } catch {
        return;
      }
    }

    setStaff((items) => items.map((item) => item.id !== staffId ? item : {
      ...item,
      groupIds: hasGroup
        ? item.groupIds.filter((id) => id !== groupId)
        : [...item.groupIds, groupId],
    }));
  };

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem("aerokids-crm-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.style.setProperty("--ak-ui-scale", String(uiScale));
    window.localStorage.setItem("aerokids-crm-ui-scale", String(uiScale));
  }, [uiScale]);

  const changeUiScale = (direction: -1 | 1) => {
    setUiScale((current) => {
      const index = UI_SCALE_LEVELS.indexOf(current);
      const next = Math.max(0, Math.min(UI_SCALE_LEVELS.length - 1, index + direction));
      return UI_SCALE_LEVELS[next];
    });
  };

  useEffect(() => {
    if (!window.matchMedia("(max-width: 720px)").matches) return;
    const nav = document.querySelector<HTMLElement>(".appNav");
    const activeButton = nav?.querySelector<HTMLElement>("button.active");
    if (!nav || !activeButton) return;
    const left = activeButton.offsetLeft - (nav.clientWidth - activeButton.clientWidth) / 2;
    nav.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
  }, [active]);


  if (apiEnabled && !session) {
    return <LoginView onAuthenticated={setSession} theme={theme} onToggleTheme={() => setTheme((current) => current === "dark" ? "light" : "dark")} />;
  }

  const currentMembership = session?.user.memberships.find((item) => item.organization_id === session.organizationId);
  const money = (value: number): string => formatMoney(
    value,
    currentMembership?.organization_locale ?? "uk-UA",
    currentMembership?.organization_currency ?? "UAH",
  );
  const headerContext = locations[0]
    ? `${currentMembership?.organization_name ?? "AeroKids CRM"} · ${locations[0].name}`
    : currentMembership?.organization_name ?? "AeroKids CRM";
  const navigation = visibleNavigation(currentMembership?.role);
  const managerRole = ["owner", "admin", "manager"].includes(currentMembership?.role ?? "");
  const canManageRecurringSchedule = !apiEnabled || managerRole;
  const canManageLeads = !apiEnabled || managerRole;
  const canManageStudents = !apiEnabled || managerRole;
  const canDeleteStudents = !apiEnabled || managerRole;
  const canManageLocations = !apiEnabled || ["owner", "admin"].includes(currentMembership?.role ?? "");
  const canManageStaff = !apiEnabled || ["owner", "admin"].includes(currentMembership?.role ?? "");
  const canEditGroups = !apiEnabled || managerRole;
  const canManagePlans = !apiEnabled || ["owner", "admin", "accountant"].includes(currentMembership?.role ?? "");
  const todayKey = localDateInput(new Date());
  const scheduleWeekStart = startOfLocalWeek(addLocalDays(new Date(), scheduleWeekOffset * 7));
  const scheduleWeekDays = Array.from({ length: 7 }, (_, index) => addLocalDays(scheduleWeekStart, index));
  const scheduleWeekEnd = addLocalDays(scheduleWeekStart, 6);
  const lessonsThisWeek = lessons
    .filter((lesson) => {
      if (lesson.status === "cancelled") return false;
      if (scheduleFilterGroupId !== "all" && lesson.groupId !== scheduleFilterGroupId) return false;
      const lessonDate = localDateInput(new Date(lesson.startsAt));
      return lessonDate >= localDateInput(scheduleWeekStart) && lessonDate <= localDateInput(scheduleWeekEnd);
    })
    .sort((a, b) => dateValue(a.startsAt) - dateValue(b.startsAt));
  const trialsThisWeek = scheduleFilterGroupId === "all" ? leads
    .filter((lead) => {
      if (!lead.trialAt || lead.status !== "Пробне заплановано") return false;
      const trialDate = localDateInput(new Date(lead.trialAt));
      return trialDate >= localDateInput(scheduleWeekStart) && trialDate <= localDateInput(scheduleWeekEnd);
    })
    .sort((a, b) => dateValue(a.trialAt) - dateValue(b.trialAt)) : [];
  const completedThisWeek = lessonsThisWeek.filter((lesson) => lesson.status === "completed").length;
  const unfinishedPastThisWeek = lessonsThisWeek.filter((lesson) => lesson.status !== "completed" && dateValue(lesson.startsAt) < Date.now()).length;
  const canSeeLeads = navigation.includes("Заявки");
  const canSeePayments = navigation.includes("Оплати");
  const canSeeSchedule = navigation.includes("Розклад") || navigation.includes("Відвідування");
  const todayLessons = lessons
    .filter((lesson) => localDateInput(new Date(lesson.startsAt)) === todayKey && lesson.status !== "cancelled")
    .sort((a, b) => dateValue(a.startsAt) - dateValue(b.startsAt));
  const todayTrials = leads
    .filter((lead) => lead.trialAt && localDateInput(new Date(lead.trialAt)) === todayKey && lead.status === "Пробне заплановано")
    .sort((a, b) => dateValue(a.trialAt) - dateValue(b.trialAt));
  const dashboardLeadTasks = canSeeLeads ? leads
    .filter((lead) => {
      if (leadIsDeferred(lead)) return false;
      if (["Відмовились", "Не відповідає", "Неактуально", "Зарахований"].includes(lead.status)) return false;
      if (lead.status === "Нова" || lead.status === "Після пробного") return true;
      if (lead.trialResult === "no_show" || lead.trialResult === "cancelled") return true;
      return Boolean(lead.nextContactAt && localDateInput(new Date(lead.nextContactAt)) <= todayKey);
    })
    .sort((a, b) => {
      const priority = leadActionPriority(a) - leadActionPriority(b);
      if (priority !== 0) return priority;
      return dateValue(a.nextContactAt, dateValue(a.createdAt)) - dateValue(b.nextContactAt, dateValue(b.createdAt));
    }) : [];
  const dashboardPaymentTasks = canSeePayments ? payments
    .filter((payment) => payment.balanceAmount > 0 && payment.status !== "cancelled" && Boolean(payment.dueDate) && payment.dueDate <= todayKey)
    .sort((a, b) => a.dueDate.localeCompare(b.dueDate) || b.balanceAmount - a.balanceAmount) : [];
  const renewalSubscriptionTasks = canSeePayments ? subscriptions.filter((item) => item.status === "active" && item.needs_renewal) : [];
  const dashboardTaskCount = dashboardLeadTasks.length + dashboardPaymentTasks.length + renewalSubscriptionTasks.length;
  const searchTerm = normalizedSearch(searchQuery);
  const searchLeads = searchTerm ? leads.filter((item) =>
    [item.child, item.parent, item.phone, item.childPhone, item.source, item.status, studentGroup(item.id)?.name]
      .some((value) => searchMatches(searchTerm, value))
  ).slice(0, 10) : [];
  const searchGroups = searchTerm ? groups.filter((item) =>
    [item.name, item.ages, item.location, item.teacherName].some((value) => searchMatches(searchTerm, value))
  ).slice(0, 6) : [];
  const searchStaff = searchTerm ? staff.filter((item) =>
    [item.fullName, item.email, item.phone, item.role].some((value) => searchMatches(searchTerm, value))
  ).slice(0, 6) : [];
  const searchPayments = searchTerm ? payments.filter((payment) => {
    const student = leads.find((lead) => lead.id === payment.studentId);
    const plan = plans.find((item) => item.id === payment.planId);
    return [student?.child, student?.parent, student?.phone, student?.childPhone, plan?.name]
      .some((value) => searchMatches(searchTerm, value));
  }).slice(0, 6) : [];

  return (
    <div className="shell">
      <aside className="appSidebar">
        <div className="brand"><img className="brandLogo" src="/aerokids-logo-master-v1.png" alt="AeroKids" /><div><b>AeroKids CRM</b><small>{currentMembership?.organization_name ?? "Керування школою"}</small></div></div>
        <nav className="appNav" aria-label="Основна навігація">{navigation.map((item) => <button title={item} aria-label={item} onClick={() => {
          if (item === "Налаштування" && currentMembership) {
            setOrganizationName(currentMembership.organization_name);
            setOrganizationTimezone(currentMembership.organization_timezone);
            setOrganizationCurrency(currentMembership.organization_currency);
            setOrganizationLocale(currentMembership.organization_locale);
          }
          setActive(item);
        }} className={active === item ? "active" : ""} key={item}><UiIcon name={navigationIcon(item)} size={17} /><span className="navLabel">{item}</span></button>)}</nav>
        <div className="asideFooter">
          <small>crm.aerokids.space</small>
        </div>
      </aside>

      <main>
        <header>
          <div className="headerTitleBar">
            <div><p className="eyebrow">{headerContext}</p><h1>{active}</h1></div>
            <div className="mobileTopIcons">
              {session && <button className="search iconButton mobileLogoutButton" aria-label="Вийти" title="Вийти" onClick={() => { clearSession(); setSession(null); }}><UiIcon name="logout" size={19} /></button>}
            </div>
          </div>
          <div className="headerActions">
            {session && <div className={"orgSwitcher " + (session.user.memberships.length === 1 ? "singleOrg" : "multiOrg")}>
              <select value={session.organizationId} onChange={(e) => { setSession(changeOrganization(session, e.target.value)); setActive("Дашборд"); }}>
                {session.user.memberships.map((membership) => <option value={membership.organization_id} key={membership.organization_id}>{membership.organization_name}</option>)}
              </select>
              <span>{roleLabel(currentMembership?.role)}</span>
            </div>}
            <div
              className={"globalSearchShell " + (showSearch ? "open" : "")}
              onBlur={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
                  setShowSearch(false);
                }
              }}
            >
              {showSearch ? <>
                <div className="globalSearchBar">
                  <span aria-hidden="true"><UiIcon name="search" size={16} /></span>
                  <input
                    autoFocus
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Пошук у CRM…"
                    aria-label="Глобальний пошук"
                  />
                  <button type="button" aria-label="Закрити пошук" title="Закрити пошук" onClick={() => { setShowSearch(false); setSearchQuery(""); }}><UiIcon name="x" size={16} /></button>
                </div>
                <div className="globalSearchDropdown">
                  {!searchTerm && <div className="searchHint compact">Ім’я, прізвище, телефон, відповідальний, група…</div>}
                  {searchTerm && searchLeads.length + searchGroups.length + searchStaff.length + searchPayments.length === 0 && <div className="searchHint compact">Нічого не знайдено.</div>}
                  {searchLeads.length > 0 && <div className="searchResults compactResults"><h3>Діти та заявки</h3>{searchLeads.map((item) => <button key={item.id} onClick={() => { if (item.status === "Зарахований") { setActive("Учні"); setSelectedStudentId(item.id); } else { setActive("Заявки"); setSelectedId(item.id); } setShowSearch(false); setSearchQuery(""); }}><span><b>{item.child}</b><small>{item.age} років · {item.parent}{item.phone ? " · " + formatUaPhone(item.phone) : ""}{item.childPhone ? " · дитина " + formatUaPhone(item.childPhone) : ""}</small></span><i>{item.status}</i></button>)}</div>}
                  {searchGroups.length > 0 && <div className="searchResults compactResults"><h3>Групи</h3>{searchGroups.map((item) => <button key={item.id} onClick={() => { setActive("Групи"); setShowSearch(false); setSearchQuery(""); void openGroup(item.id); }}><span><b>{item.name}</b><small>{item.ages} · {item.location}{item.teacherName ? " · " + item.teacherName : ""}</small></span><i>{item.members.length}/{item.capacity}</i></button>)}</div>}
                  {searchPayments.length > 0 && <div className="searchResults compactResults"><h3>Оплати</h3>{searchPayments.map((payment) => { const student = leads.find((lead) => lead.id === payment.studentId); const plan = plans.find((item) => item.id === payment.planId); return <button key={payment.id} onClick={() => { setShowSearch(false); setSearchQuery(""); goToPayment(payment.id); }}><span><b>{student?.child ?? "Учень"} · {plan?.name ?? "Оплата"}</b><small>{student?.parent ?? "Відповідальний не вказаний"}{student?.phone ? " · " + formatUaPhone(student.phone) : ""}</small></span><i>{payment.balanceAmount > 0 ? "Залишок " + money(payment.balanceAmount) : "Сплачено"}</i></button>; })}</div>}
                  {searchStaff.length > 0 && <div className="searchResults compactResults"><h3>Працівники</h3>{searchStaff.map((item) => <button key={item.id} onClick={() => { setActive("Працівники"); setSelectedStaffId(item.id); setShowSearch(false); setSearchQuery(""); }}><span><b>{item.fullName}</b><small>{item.role} · {item.email || item.phone}</small></span><i>{item.isActive ? "Активний" : "Неактивний"}</i></button>)}</div>}
                </div>
              </> : <button className="search globalSearchTrigger" aria-label="Пошук" title="Пошук" onClick={() => { setSearchQuery(""); setShowSearch(true); }}><UiIcon name="search" size={17} /><span>Пошук</span></button>}
            </div>
            {canManageLeads && <button className="primary headerPrimaryAction" onClick={() => setShowLeadForm(true)}><UiIcon name="plus" size={17} /><span>Нова заявка</span></button>}
            
            {session && <button className="search iconButton logoutButton" aria-label="Вийти" title="Вийти" onClick={() => { clearSession(); setSession(null); }}><UiIcon name="logout" size={18} /></button>}
          </div>
        </header>

        {apiEnabled && workspaceLoading && <div className="syncBanner syncing"><span className="syncPulse" />Оновлення даних…</div>}
        {apiEnabled && workspaceError && <div className="globalErrorToast" role="alert" aria-live="assertive">
          <span className="globalErrorIcon">!</span>
          <div><b>Не вдалося виконати дію</b><p>{workspaceError}</p></div>
          <button type="button" aria-label="Закрити повідомлення" onClick={() => setWorkspaceError("")}>×</button>
        </div>}
        {apiEnabled && workspaceLoaded && !workspaceLoading && !workspaceError && workspaceRefreshing && <div className="syncStatus refreshing"><span className="syncPulse" />Оновлення даних…</div>}
        {saveToastTick > 0 && <div className="saveToast" role="status" aria-live="polite"><span>✓</span><b>Збережено</b></div>}

        {active === "Дашборд" && <section className="todayDashboard">
          <div className="todayIntro">
            <div>
              <p className="eyebrow">Сьогодні · {new Date().toLocaleDateString("uk-UA", { weekday: "long", day: "numeric", month: "long" })}</p>
              <h2>{dashboardTaskCount > 0 ? "Що потребує уваги" : "Усе важливе на сьогодні під контролем"}</h2>
            </div>
            {dashboardTaskCount > 0 && <span className="todayTaskCount">{dashboardTaskCount} {dashboardTaskCount === 1 ? "дія" : dashboardTaskCount < 5 ? "дії" : "дій"}</span>}
          </div>

          {canSeeSchedule && <article className="panel todayLessonsPanel">
            <div className="todaySectionHead">
              <div><p className="eyebrow">Розклад</p><h2>Заняття сьогодні</h2></div>
              <button className="link" onClick={() => setActive("Розклад")}>Розклад →</button>
            </div>
            <div className="todayLessonList">
              {todayLessons.map((lesson) => {
                const group = groups.find((item) => item.id === lesson.groupId);
                return <div className="todayLessonRow" key={lesson.id}>
                  <button className="todayLessonMain" onClick={() => goToLesson(lesson.id)}>
                    <time>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time>
                    <span><b>{group?.name ?? "Заняття"}</b><small>{lesson.topic || "Тема не вказана"} · {lesson.duration} хв{group?.location ? " · " + group.location : ""}</small></span>
                    <em>Журнал →</em>
                  </button>
                  {group && <button className="todayGroupLink" onClick={() => goToGroup(group.id)}>Група</button>}
                </div>;
              })}
              {todayTrials.map((lead) => <button className="todayLessonRow todayTrialRow" key={"trial-" + lead.id} onClick={() => openLead(lead.id)}>
                <span className="todayLessonMain">
                  <time>{new Date(lead.trialAt!).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time>
                  <span><b>{lead.child} · пробне</b><small>{lead.parent}{lead.trialLocation ? " · " + lead.trialLocation : ""}</small></span>
                  <em>Заявка →</em>
                </span>
              </button>)}
              {todayLessons.length === 0 && todayTrials.length === 0 && <div className="todayEmpty">На сьогодні занять не заплановано.</div>}
            </div>
          </article>}

          <article className="panel todayActionsPanel">
            <div className="todaySectionHead">
              <div><p className="eyebrow">Дії</p><h2>Потрібно зробити сьогодні</h2></div>
            </div>
            <div className="todayActionList">
              {dashboardLeadTasks.map((lead) => {
                const kind = lead.status === "Нова"
                  ? "Нова заявка"
                  : lead.status === "Після пробного"
                    ? "Після пробного"
                    : lead.trialResult === "no_show"
                      ? "Не прийшов на пробне"
                      : lead.trialResult === "cancelled"
                        ? "Пробне скасовано"
                        : "Зв’язатися";
                const detail = lead.nextContactAt && localDateInput(new Date(lead.nextContactAt)) <= todayKey
                  ? "Контакт запланований " + new Date(lead.nextContactAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
                  : lead.parent + " · " + formatUaPhone(lead.phone);
                return <button className="todayActionRow" key={"lead-" + lead.id} onClick={() => openLead(lead.id)}>
                  <span className={"todayActionType lead action-" + leadActionMeta(lead).type}>{leadActionMeta(lead).icon} {leadActionMeta(lead).label}</span>
                  <span className="todayActionText"><b>{lead.child}, {lead.age} років</b><small>{kind} · {detail}</small></span>
                  <span className="todayActionArrow">→</span>
                </button>;
              })}
              {renewalSubscriptionTasks.map((subscription) => {
                const student = leads.find((lead) => lead.id === subscription.student_id);
                const plan = plans.find((item) => item.id === subscription.plan_id);
                return <button className="todayActionRow" key={"renewal-" + subscription.id} onClick={() => { setSelectedStudentId(subscription.student_id); setActive("Учні"); }}>
                  <span className="todayActionType payment">Абонемент</span>
                  <span className="todayActionText"><b>{student?.child ?? "Учень"} · залишилось 1 заняття</b><small>{plan?.name ?? "Абонемент"} · скоро продовження</small></span>
                  <span className="todayActionArrow">→</span>
                </button>;
              })}
              {dashboardPaymentTasks.map((payment) => {
                const student = leads.find((lead) => lead.id === payment.studentId);
                const isOverdue = payment.dueDate < todayKey || payment.status === "overdue";
                return <button className="todayActionRow" key={"payment-" + payment.id} onClick={() => goToPayment(payment.id)}>
                  <span className={"todayActionType payment " + (isOverdue ? "urgent" : "")}>{isOverdue ? "Борг" : "Оплата"}</span>
                  <span className="todayActionText"><b>{student?.child ?? "Учень"} · {money(payment.balanceAmount)}</b><small>{isOverdue ? "Прострочено" : "Оплатити сьогодні"} · термін {new Date(payment.dueDate + "T00:00:00").toLocaleDateString("uk-UA")}</small></span>
                  <span className="todayActionArrow">→</span>
                </button>;
              })}
              {dashboardTaskCount === 0 && <div className="todayEmpty done">На сьогодні немає невиконаних важливих дій.</div>}
            </div>
          </article>
        </section>}

        {active === "Заявки" && <section className="panel leadsPage">
          <div className="panelHead leadsHead">
            <div className="leadsTitleBlock"><p className="eyebrow">Робота із заявками</p><h2>Від звернення до зарахування</h2><span>Перетягуйте картки між етапами. Для етапів із додатковими даними CRM одразу відкриє потрібну дію.</span></div>
            <div className="leadControls">
              <label className="leadSort">Джерело<select value={leadSourceFilter} onChange={(e) => setLeadSourceFilter(e.target.value)}>
                <option value="all">Усі джерела</option>
                {Array.from(new Set(leads.map((lead) => canonicalLeadSource(lead.source)).filter(Boolean))).sort().map((source) => <option value={source} key={source}>{leadSourceLabel(source)}</option>)}
              </select></label>
              <label className="leadSort">Порядок карток<select value={leadSort} onChange={(e) => setLeadSort(e.target.value as typeof leadSort)}>
                <option value="priority">Термінові спочатку</option>
                <option value="next_action">Найближча дія</option>
                <option value="newest">Нові заявки</option>
              </select></label>
            </div>
          </div>
          <div className="kanbanSummary kanbanSummarySimple">
            <div className="kanbanSummaryStat"><span>Активні заявки</span><strong>{leadActiveCount}</strong></div>
            <div className="kanbanSummaryStat attention"><span>Потребують дії</span><strong>{leadActionCount}</strong></div>
            <span className="kanbanHint">Картки впорядковуються всередині кожного етапу. Відкладені заявки з’являться знову у вибрану дату.</span>
          </div>
          <details className="mobileLeadTools">
            <summary><UiIcon name="settings" size={16} /><span>Фільтри</span>{(leadSourceFilter !== "all" || leadSort !== "priority") && <i>●</i>}</summary>
            <div className="mobileLeadToolsBody">
              <label>Джерело<select value={leadSourceFilter} onChange={(e) => setLeadSourceFilter(e.target.value)}>
                <option value="all">Усі джерела</option>
                {Array.from(new Set(leads.map((lead) => canonicalLeadSource(lead.source)).filter(Boolean))).sort().map((source) => <option value={source} key={source}>{leadSourceLabel(source)}</option>)}
              </select></label>
              <label>Порядок<select value={leadSort} onChange={(e) => setLeadSort(e.target.value as typeof leadSort)}>
                <option value="priority">Термінові спочатку</option>
                <option value="next_action">Найближча дія</option>
                <option value="newest">Нові заявки</option>
              </select></label>
              <div className="mobileLeadStats"><span>В роботі <b>{leadActiveCount}</b></span><span>Потрібна дія <b>{leadActionCount}</b></span></div>
            </div>
          </details>
          <LeadKanban leads={visibleLeads.filter((lead) => lead.status !== "Зарахований")} onOpen={openLead} onMove={moveLeadOnBoard} movingId={leadMoveSavingId} />
        </section>}

        {active === "Учні" && <section className="studentsLayout">
          <article className="panel studentsPanel">
            <div className="panelHead">
              <div><p className="eyebrow">База учнів</p><h2>Активні учні</h2></div>
              <div className="filters">
                <button className={"chip " + (studentFilter === "all" ? "active" : "")} onClick={() => setStudentFilter("all")}>Усі</button>
                <button className={"chip " + (studentFilter === "active" ? "active" : "")} onClick={() => setStudentFilter("active")}>Активні</button>
                <button className={"chip " + (studentFilter === "paused" ? "active" : "")} onClick={() => setStudentFilter("paused")}>Пауза</button>
                <button className={"chip " + (studentFilter === "archived" ? "active" : "")} onClick={() => setStudentFilter("archived")}>Архів</button>
              </div>
            </div>
            <div className="studentTable">
              <div className="studentRow studentHead"><span>Учень</span><span>Група</span><span>Контакт</span><span>Статус</span></div>
              {visibleStudents.length === 0 && <div className="emptyState">За цим фільтром учнів немає.</div>}
              {visibleStudents.map((student) => {
                const group = studentGroup(student.id);
                const state = studentStates[student.id] ?? "Активний";
                return <button className="studentRow studentButton" key={student.id} onClick={() => { setSelectedStudentId(student.id); setTransferGroupId(group?.id ?? null); }}>
                  <span className="studentIdentity"><i>{student.child[0]}</i><b>{student.child}<small>{student.age} років</small></b></span>
                  <span>{group?.name ?? "Без групи"}</span>
                  <span>{student.parent}<small>{student.phone}</small></span>
                  <span className={"studentState " + state.toLowerCase()}>{state}</span>
                </button>;
              })}
            </div>
          </article>
          <aside className="studentSummary panel">
            <p className="eyebrow">Огляд</p><h2>{activeStudents.length} учнів</h2>
            <div className="summaryMetric"><span>У групах</span><strong>{activeStudents.filter((x) => studentGroup(x.id)).length}</strong></div>
            <div className="summaryMetric"><span>На паузі</span><strong>{Object.values(studentStates).filter((x) => x === "Пауза").length}</strong></div>
            <div className="summaryMetric"><span>Груп</span><strong>{groups.length}</strong></div>
          </aside>
        </section>}

        {active === "Розклад" && <section className="scheduleWorkspace">
          <article className="panel schedulePanel scheduleCalendar">
            <div className="scheduleToolbar scheduleToolbarClear">
              <div>
                <p className="eyebrow">Календар</p>
                <h2>{scheduleWeekStart.toLocaleDateString("uk-UA", { day: "numeric", month: "long" })} — {scheduleWeekEnd.toLocaleDateString("uk-UA", { day: "numeric", month: "long", year: "numeric" })}</h2>
                <div className="scheduleWeekSummary">
                  <span><b>{lessonsThisWeek.length}</b> занять</span>
                  <span className="done"><b>{completedThisWeek}</b> проведено</span>
                  {unfinishedPastThisWeek > 0 && <span className="attention"><b>{unfinishedPastThisWeek}</b> не завершено</span>}
                  {trialsThisWeek.length > 0 && <span className="trial"><b>{trialsThisWeek.length}</b> пробних</span>}
                </div>
              </div>
              <div className="scheduleToolbarActions">
                <label className="scheduleGroupFilter">Показати<select value={scheduleFilterGroupId} onChange={(e) => setScheduleFilterGroupId(e.target.value)}>
                  <option value="all">Усі групи + пробні</option>
                  {groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}
                </select></label>
                <div className="scheduleNav">
                  <button className="search" aria-label="Попередній тиждень" onClick={() => setScheduleWeekOffset((value) => value - 1)}>←</button>
                  <button className="search" onClick={() => setScheduleWeekOffset(0)} disabled={scheduleWeekOffset === 0}>Цей тиждень</button>
                  <button className="search" aria-label="Наступний тиждень" onClick={() => setScheduleWeekOffset((value) => value + 1)}>→</button>
                </div>
              </div>
            </div>
            <div className="scheduleLegend">
              <span className="planned"><i></i>Заплановано</span>
              <span className="completed"><i></i>Проведено</span>
              <span className="missed"><i></i>Не проведено</span>
              {scheduleFilterGroupId === "all" && <span className="trial"><i></i>Пробне</span>}
            </div>
            <div className="mobileScheduleAgenda">
              {scheduleWeekDays.map((date) => {
                const dayKey = localDateInput(date);
                const dayLessons = lessonsThisWeek.filter((lesson) => localDateInput(new Date(lesson.startsAt)) === dayKey);
                const dayTrials = trialsThisWeek.filter((lead) => lead.trialAt && localDateInput(new Date(lead.trialAt)) === dayKey);
                const items = [...dayLessons.map((lesson) => ({ kind: "lesson" as const, at: lesson.startsAt, lesson })), ...dayTrials.map((lead) => ({ kind: "trial" as const, at: lead.trialAt!, lead }))].sort((a,b)=>dateValue(a.at)-dateValue(b.at));
                if (items.length === 0) return null;
                const isToday = dayKey === todayKey;
                return <section className={"mobileScheduleDay " + (isToday ? "today" : "")} key={"mobile-"+dayKey}>
                  <div className="mobileScheduleDayHead"><b>{date.toLocaleDateString("uk-UA",{weekday:"short",day:"2-digit",month:"2-digit"})}</b>{isToday && <span>Сьогодні</span>}</div>
                  <div className="mobileScheduleRows">
                    {items.map((item) => {
                      if(item.kind === "trial"){
                        return <button className="mobileScheduleRow trial" key={"mtrial-"+item.lead.id} onClick={() => openLead(item.lead.id)}>
                          <time>{new Date(item.at).toLocaleTimeString("uk-UA",{hour:"2-digit",minute:"2-digit"})}</time>
                          <span><b>{item.lead.child}</b><small>Пробне</small></span>
                          <i>›</i>
                        </button>;
                      }
                      const group = groups.find((g)=>g.id===item.lesson.groupId);
                      const isPast = dateValue(item.lesson.startsAt) < Date.now();
                      const state = item.lesson.status === "completed" ? "completed" : isPast ? "missed" : "planned";
                      const label = state === "completed" ? "Проведено" : state === "missed" ? "Не проведено" : "Заплановано";
                      return <button className={"mobileScheduleRow "+state} key={"mlesson-"+item.lesson.id} onClick={()=>goToLesson(item.lesson.id)}>
                        <time>{new Date(item.at).toLocaleTimeString("uk-UA",{hour:"2-digit",minute:"2-digit"})}</time>
                        <span><b>{group?.name ?? "Група"}</b><small>{label}</small></span>
                        <i>›</i>
                      </button>;
                    })}
                  </div>
                </section>;
              })}
              {lessonsThisWeek.length === 0 && trialsThisWeek.length === 0 && <div className="mobileScheduleEmpty">На цей тиждень подій немає.</div>}
            </div>
            <div className="weekGrid weekGridConcrete scheduleWeekClear">
              {scheduleWeekDays.map((date) => {
                const dayKey = localDateInput(date);
                const dayLessons = lessonsThisWeek.filter((lesson) => localDateInput(new Date(lesson.startsAt)) === dayKey);
                const dayTrials = trialsThisWeek.filter((lead) => lead.trialAt && localDateInput(new Date(lead.trialAt)) === dayKey);
                const isToday = dayKey === todayKey;
                return <div className={"dayColumn scheduleDay " + (isToday ? "today" : "")} key={dayKey}>
                  <div className="scheduleDayHead">
                    <div><b>{date.toLocaleDateString("uk-UA", { weekday: "long" })}</b>{isToday && <em>Сьогодні</em>}</div>
                    <span>{date.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })}</span>
                  </div>
                  <div className="scheduleDayLessons">
                    {[...dayLessons].sort((a,b)=>dateValue(a.startsAt)-dateValue(b.startsAt)).map((lesson) => {
                      const group = groups.find((item) => item.id === lesson.groupId);
                      const teacher = group ? (group.teacherName ?? groupTeacher(group.id)?.fullName) : undefined;
                      const marked = lesson.attendanceTotal ?? Object.keys(attendance[lesson.id] ?? {}).length;
                      const total = group?.members.length ?? 0;
                      const isPast = dateValue(lesson.startsAt) < Date.now();
                      const state = lesson.status === "completed" ? "completed" : isPast ? "missed" : "planned";
                      const statusText = state === "completed" ? "Проведено" : state === "missed" ? "Не проведено" : "Заплановано";
                      return <button className={"scheduleCard concreteLessonCard " + state} key={lesson.id} onClick={() => goToLesson(lesson.id)}>
                        <div className="scheduleCardTop"><time>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time><span className={"scheduleStatus " + state}>{statusText}</span></div>
                        <strong>{group?.name ?? "Група"}</strong>
                        <small>{lesson.topic || "Тема ще не вказана"}</small>
                        <div className="scheduleCardMeta">{teacher && <span>{teacher}</span>}{total > 0 && <span>{marked}/{total} відмічено</span>}</div>
                      </button>;
                    })}
                    {dayTrials.map((lead) => <button className="scheduleCard trialCalendarCard" key={"trial-"+lead.id} onClick={() => openLead(lead.id)}>
                      <div className="scheduleCardTop"><time>{new Date(lead.trialAt!).toLocaleTimeString("uk-UA", { hour:"2-digit", minute:"2-digit" })}</time><span className="scheduleStatus trial">Пробне</span></div>
                      <strong>{lead.child}</strong>
                      <small>{lead.age} років{lead.trialLocation ? " · " + lead.trialLocation : ""}</small>
                      <div className="scheduleCardMeta"><span>Відкрити заявку →</span></div>
                    </button>)}
                    {dayLessons.length === 0 && dayTrials.length === 0 && <div className="scheduleDayEmpty">Вільний день</div>}
                  </div>
                </div>;
              })}
            </div>
          </article>

          <section className="scheduleTools">
            <article className="panel lessonCreate">
              <div className="scheduleToolHead"><div><p className="eyebrow">Разове</p><h2>Додати заняття</h2></div><span>Для переносу, додаткового або індивідуального заняття</span></div>
              <label>Група<select value={newLessonGroupId} onChange={(e) => setNewLessonGroupId(e.target.value)}><option value="">Оберіть групу</option>{groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label>
              <DateTimeEditor label="Дата і час" value={newLessonAt} onChange={setNewLessonAt} />
              <DurationSelect value={newLessonDuration} onChange={setNewLessonDuration} />
              <label>Тема<input value={newLessonTopic} onChange={(e) => setNewLessonTopic(e.target.value)} placeholder="Можна заповнити пізніше в журналі" /></label>
              <button className="primary full" disabled={!newLessonGroupId} onClick={createLesson}>Створити заняття</button>
            </article>
            {canManageRecurringSchedule && <article className="panel lessonCreate recurringSettings">
              <div className="scheduleToolHead"><div><p className="eyebrow">Регулярний</p><h2>Додати час групи</h2></div><span>Постійний день і час для автоматичного календаря</span></div>
              <label>Група<select value={scheduleGroupId} onChange={(e) => setScheduleGroupId(e.target.value)}><option value="">Оберіть групу</option>{groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label>
              <div className="formTwo">
                <label>День<select value={scheduleWeekday} onChange={(e) => setScheduleWeekday(Number(e.target.value))}>{["Понеділок","Вівторок","Середа","Четвер","П’ятниця","Субота","Неділя"].map((day,index) => <option value={index} key={day}>{day}</option>)}</select></label>
                <TimeSelect label="Час" value={scheduleTime} onChange={setScheduleTime} />
              </div>
              <DurationSelect value={scheduleDuration} onChange={setScheduleDuration} />
              <button className="search full" disabled={!scheduleGroupId} onClick={createGroupSchedule}>Додати регулярний час</button>
            </article>}
          </section>
        </section>}

        {active === "Відвідування" && <section className="attendanceLayout">
          <article className="panel lessonListPanel">
            <div className="attendanceWeekHead attendanceDayHead">
              <div>
                <p className="eyebrow">{attendanceDayOffset === 0 ? "Сьогодні" : "Журнал за день"}</p>
                <h2>{attendanceDay.toLocaleDateString("uk-UA", { weekday: "long", day: "numeric", month: "long" })}</h2>
              </div>
              <span className="counter">{journalLessons.length}</span>
            </div>
            <div className="attendanceWeekNav attendanceDayNav">
              <button className="search" aria-label="Попередній день" title="Попередній день" onClick={() => setAttendanceDayOffset((value) => value - 1)}>←</button>
              <button className="search" disabled={attendanceDayOffset === 0} onClick={() => setAttendanceDayOffset(0)}>Сьогодні</button>
              <button className="search" aria-label="Наступний день" title="Наступний день" onClick={() => setAttendanceDayOffset((value) => value + 1)}>→</button>
            </div>
            <div className="lessonList attendanceDailyList">
              {journalLessons.map((lesson) => {
                const group = groups.find((g) => g.id === lesson.groupId);
                const start = dateValue(lesson.startsAt);
                const end = start + lesson.duration * 60_000;
                const completed = lesson.status === "completed";
                const inProgress = !completed && attendanceDayKey === attendanceTodayKey && start <= attendanceNow && attendanceNow <= end;
                const overdue = !completed && end < attendanceNow;
                const nearest = !completed && lesson.id === nearestAttendanceLesson?.id;
                const rowState = completed ? "completed" : inProgress ? "current" : overdue ? "missed" : nearest ? "nearest" : "planned";
                const endTime = new Date(end).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
                const summary = completed
                  ? `Відмічено · ${lesson.attendancePresent ?? 0} є · ${lesson.attendanceAbsent ?? 0} нема`
                  : inProgress
                    ? `Зараз · до ${endTime}`
                    : overdue
                      ? "Потрібно відмітити відвідування"
                      : nearest
                        ? "Найближче заняття"
                        : "Заплановано";
                return <button className={"lessonRow attendanceDailyRow " + rowState + " " + (lesson.id === selectedLessonId ? "active" : "")} key={lesson.id} onClick={() => setSelectedLessonId(lesson.id)}>
                  <time>
                    <strong>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</strong>
                    <small>до {endTime}</small>
                  </time>
                  <span><b>{group?.name ?? "Група"}</b><small>{summary}</small></span>
                  <i className={"lessonStateBadge " + rowState}>{completed ? "✓ Відмічено" : inProgress ? "Зараз" : overdue ? "! Відмітити" : nearest ? "Найближче" : "Заплановано"}</i>
                </button>;
              })}
              {journalLessons.length === 0 && <div className="emptyState compactEmpty">На цей день занять немає.</div>}
            </div>
            {completedAttendanceLessons.length > 0 && pendingAttendanceLessons.length > 0 && <div className="attendanceCompletedHint">Відмічені заняття автоматично переходять униз списку.</div>}
          </article>
          <article className="panel attendancePanel">
            {lessonSaveNotice && <div className="lessonSaveNotice">✓ Збережено</div>}
            {focusedAttendanceStudentId ? <div className="studentAttendanceOverview">
              <div className="studentAttendanceHero">
                <button className="lessonBackButton" onClick={() => { setFocusedAttendanceStudentId(null); setFocusedAttendanceGroupId(null); }}><UiIcon name="back" size={16} /><span>До журналу занять</span></button>
                <div className="studentAttendanceTitle">
                  <span>{focusedAttendanceStudent?.child?.[0] ?? "?"}</span>
                  <div><p className="eyebrow">Відвідування учня</p><h2>{focusedAttendanceStudent?.child ?? "Учень"}</h2><small>{focusedAttendanceGroup?.name ?? "Усі групи"}{focusedAttendanceStudent?.parent ? " · " + focusedAttendanceStudent.parent : ""}</small></div>
                </div>
              </div>
              <div className="studentAttendanceStats">
                <article><small>Відвідуваність</small><strong>{focusedAttendanceRate}%</strong><span>{focusedAttendanceCounts.total} занять</span></article>
                <article><small>Був</small><strong>{focusedAttendanceCounts.present}</strong><span>занять</span></article>
                <article><small>Запізнився</small><strong>{focusedAttendanceCounts.late}</strong><span>занять</span></article>
                <article><small>Пропуски</small><strong>{focusedAttendanceCounts.absent + focusedAttendanceCounts.excused}</strong><span>{focusedAttendanceCounts.excused} поважних</span></article>
              </div>
              <div className="studentAttendanceHistory">
                <div className="studentAttendanceHistoryHead"><span>Дата</span><span>Заняття</span><span>Статус</span><span>Коментар</span><span></span></div>
                {studentAttendanceHistoryLoading && <div className="emptyState compactEmpty">Завантажуємо історію…</div>}
                {!studentAttendanceHistoryLoading && focusedAttendanceRows.length === 0 && <div className="emptyState">У цього учня ще немає відмічених занять у цій групі.</div>}
                {focusedAttendanceRows.map((row) => <div className="studentAttendanceHistoryRow" key={row.session_id}>
                  <time><b>{weekdayLong(row.starts_at)}</b><span>{new Date(row.starts_at).toLocaleDateString("uk-UA")}</span><small>{new Date(row.starts_at).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</small></time>
                  <span><b>{row.topic || "Заняття"}</b><small>{row.group_name} · {row.duration_minutes} хв</small></span>
                  <span><b className={"protocolStatus " + row.status}>{attendanceStatusLabel(row.status)}</b></span>
                  <span className="protocolNote">{row.note || "—"}</span>
                  <button className="link" onClick={() => goToLesson(row.session_id)}>Заняття →</button>
                </div>)}
              </div>
            </div> : selectedLesson && <>
              <div className="lessonJournalHead">
                <button className="lessonBackButton" onClick={() => setActive("Розклад")}><UiIcon name="back" size={16} /><span>До розкладу</span></button>
                <div className="panelHead">
                  <div>
                    <p className="eyebrow">{selectedLesson.status === "completed" ? "Проведене заняття" : "Конкретне заняття"}</p>
                    <h2>{lessonGroup?.name}</h2>
                    <p className="lessonMeta"><b>{weekdayLong(selectedLesson.startsAt)}</b> · {new Date(selectedLesson.startsAt).toLocaleDateString("uk-UA")} · {new Date(selectedLesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })} · {selectedLesson.duration} хв</p>
                  </div>
                  {selectedLesson.status === "completed" && !lessonEditing
                    ? <button className="lessonEditButton" onClick={() => setLessonEditing(true)}>Редагувати</button>
                    : <div className="attendanceQuickActions"><button className="search" onClick={markAllPresent}>Усі присутні</button><button className="search" onClick={markUnmarkedAbsent}>Непозначені → відсутні</button></div>}
                </div>
              </div>

              {lessonEditing ? <>
                <div className="lessonDetailsEditor">
                  <label>Тема заняття<input value={lessonTopicDraft} onChange={(e) => setLessonTopicDraft(e.target.value)} maxLength={240} placeholder="Що вивчаємо на занятті" /></label>
                  <label>Домашнє завдання / примітки<textarea value={lessonNotesDraft} onChange={(e) => setLessonNotesDraft(e.target.value)} maxLength={4000} placeholder="Наприклад: 3 кола в симуляторі без падіння. Або внутрішня примітка викладача." /></label>
                  <div className="lessonDetailsActions"><small>Ці дані належать конкретному заняттю.</small><button className="search" disabled={lessonDetailsSaving} onClick={saveLessonDetails}>{lessonDetailsSaving ? "Зберігаємо…" : "Зберегти тему і завдання"}</button></div>
                </div>
                <div className="attendanceTable">
                  {lessonStudents.map((student) => {
                    const value = attendance[selectedLesson.id]?.[student.id];
                    return <div id={"attendance-student-" + student.id} className={"attendanceRow " + (!value ? "unmarked " : "") + (focusedAttendanceStudentId === student.id ? "focusedStudent" : "")} key={student.id}>
                      <span className="studentIdentity"><i>{student.child[0]}</i><b>{student.child}<small>{student.age} років{student.parent ? " · " + student.parent : ""}</small></b>{!value && <em className="unmarkedBadge">Не відмічено</em>}</span>
                      <div className="attendanceButtons">
                        <button className={value === "present" ? "active present" : ""} onClick={() => markAttendance(student.id, "present")}>✓ Є</button>
                        <button className={value === "absent" ? "active absent" : ""} onClick={() => markAttendance(student.id, "absent")}>Нема</button>
                        <button className={value === "excused" ? "active excused" : ""} onClick={() => markAttendance(student.id, "excused")}>Поважна причина</button>
                      </div>
                      {(value === "absent" || value === "excused") && <input className="attendanceReasonInput" value={attendanceNotes[selectedLesson.id]?.[student.id] ?? ""} onChange={(e) => setAttendanceNote(student.id, e.target.value)} maxLength={300} placeholder={value === "excused" ? "Причина / коментар (за потреби)" : "Причина відсутності (за потреби)"} />}
                    </div>;
                  })}
                  {lessonStudents.length === 0 && <div className="emptyState">У цій групі поки немає активних учнів. Додайте учнів до групи, щоб відмічати відвідування.</div>}
                </div>
                <div className="attendanceFooter">
                  <span>{attendanceLoading ? "Завантажуємо…" : <>Позначено: <b>{Object.keys(attendance[selectedLesson.id] ?? {}).length}/{lessonStudents.length}</b>{lessonStudents.length > Object.keys(attendance[selectedLesson.id] ?? {}).length && <small> · ще {lessonStudents.length - Object.keys(attendance[selectedLesson.id] ?? {}).length}</small>}</>}</span>
                  <div className="attendanceFooterActions">
                    {selectedLesson.status === "completed" && <button className="search" onClick={() => setLessonEditing(false)}>Скасувати</button>}
                    <button className="primary" disabled={attendanceSaving || attendanceLoading || lessonStudents.length === 0 || Object.keys(attendance[selectedLesson.id] ?? {}).length !== lessonStudents.length} onClick={saveAttendance}>{attendanceSaving ? "Зберігаємо…" : lessonStudents.length === 0 ? "Немає учнів для відмітки" : selectedLesson.status === "completed" ? "Зберегти зміни" : "Зберегти відвідування"}</button>
                  </div>
                </div>
              </> : <div className="lessonProtocol">
                <section className="lessonProtocolSummary">
                  <div><small>Тема заняття</small><strong>{selectedLesson.topic || "Не вказано"}</strong></div>
                  <div><small>Домашнє завдання / примітки</small><strong>{selectedLesson.notes || "Немає"}</strong></div>
                </section>
                <div className="lessonProtocolTable">
                  <div className="lessonProtocolRow lessonProtocolHead"><span>Учень</span><span>Статус</span><span>Причина / коментар</span></div>
                  {lessonStudents.map((student) => {
                    const value = attendance[selectedLesson.id]?.[student.id];
                    const note = attendanceNotes[selectedLesson.id]?.[student.id]?.trim();
                    return <div id={"attendance-student-" + student.id} className={"lessonProtocolRow " + (focusedAttendanceStudentId === student.id ? "focusedStudent" : "")} key={student.id}>
                      <span className="protocolStudent"><i>{student.child[0]}</i><b>{student.child}<small>{student.age} років{student.parent ? " · " + student.parent : ""}</small></b></span>
                      <span><b className={"protocolStatus " + (value ?? "unmarked")}>{attendanceStatusLabel(value)}</b></span>
                      <span className="protocolNote">{note || "—"}</span>
                    </div>;
                  })}
                </div>
                <div className="lessonProtocolFooter">
                  <span><b>{selectedLesson.attendancePresent ?? 0}</b> були</span>
                  <span><b>{selectedLesson.attendanceLate ?? 0}</b> запізнились</span>
                  <span><b>{selectedLesson.attendanceAbsent ?? 0}</b> не були</span>
                  <span><b>{selectedLesson.attendanceExcused ?? 0}</b> поважна причина</span>
                </div>
              </div>}
            </>}
          </article>
        </section>}

        {active === "Оплати" && <section className="paymentsLayout">
          <div className="paymentsMain">
            <section className="paymentStats">
              <article><span>Сплачено</span><strong>{money(paymentTotals.paid)}</strong><small>{payments.filter((x) => x.status === "paid").length} платежів</small></article>
              <article><span>Очікується</span><strong>{money(paymentTotals.pending)}</strong><small>{payments.filter((x) => x.balanceAmount > 0 && x.status !== "cancelled").length} рахунків</small></article>
              <article><span>Прострочено</span><strong>{money(paymentTotals.overdue)}</strong><small>{payments.filter((x) => x.status === "overdue").length} боргів</small></article>
            </section>
            {paymentReminders.length > 0 && <article className="panel reminderPanel">
              <div className="panelHead"><div><p className="eyebrow">Контроль оплат</p><h2>Потрібно нагадати</h2></div><span className="counter">{paymentReminders.length}</span></div>
              <p className="reminderIntro">CRM показує лише актуальний етап нагадування. Після фіксації дзвінка цей етап зникає і не дублюється; наступне нагадування з’явиться лише на наступному етапі прострочення.</p>
              <div className="reminderList">{paymentReminders.map((reminder) => <div className="reminderRow" key={reminder.payment_id + reminder.stage}>
                <div><b>{reminder.student_name}</b><small>{reminder.contact_name ?? "Контакт не вказано"}{reminder.contact_phone ? " · " + reminder.contact_phone : ""}</small></div>
                <span><b>{money(reminder.amount_minor / 100)}</b><small>до {new Date(reminder.due_date + "T00:00:00").toLocaleDateString("uk-UA")}</small></span>
                <span className={"reminderStage " + (reminder.days_from_due > 0 ? "overdue" : "upcoming")}>{reminder.label}</span>
                <div className="reminderActions">{reminder.contact_phone && <a className="link" href={"tel:" + reminder.contact_phone.replace(/\s/g, "")}>Подзвонити</a>}<button className="search" disabled={reminderSavingId === reminder.payment_id} onClick={() => markReminderHandled(reminder)}>{reminderSavingId === reminder.payment_id ? "Зберігаємо…" : "Дзвінок зроблено"}</button></div>
              </div>)}</div>
            </article>}
            <article className="panel paymentsPanel">
              <div className="panelHead"><div><p className="eyebrow">Фінанси</p><h2>Оплати учнів</h2></div><button className="primary" onClick={openPaymentForm}>+ Нарахування</button></div>
              <div className="paymentTable">
                <div className="paymentRow paymentHead"><span>Дитина / відповідальний</span><span>Абонемент</span><span>Нараховано / залишок</span><span>До дати</span><span>Статус</span><span>Дії</span></div>
                {payments.map((payment) => {
                  const student = leads.find((lead) => lead.id === payment.studentId);
                  const plan = plans.find((item) => item.id === payment.planId);
                  const subscription = payment.subscriptionId ? subscriptions.find((item) => item.id === payment.subscriptionId) : undefined;
                  const statusLabel = payment.status === "paid" ? "Сплачено" : payment.status === "overdue" ? "Прострочено" : payment.status === "refunded" ? "Повернено" : payment.status === "cancelled" ? "Скасовано" : "Очікується";
                  return <div id={"payment-" + payment.id} className={"paymentRow " + (focusedPaymentId === payment.id ? "paymentFocused" : "")} key={payment.id}>
                    <span className="paymentIdentity"><b>{student?.child ?? "Учень"}</b><small>Дитина{student?.childPhone ? " · " + formatUaPhone(student.childPhone) : ""}</small><small><strong>Відповідальний:</strong> {student?.parent ?? "Не вказано"}{student?.phone ? " · " + formatUaPhone(student.phone) : ""}</small></span>
                    <span className="paymentPlanCell"><b>{plan?.name ?? "—"}{plan && !plan.isActive ? <em className="inactivePlanInline">Неактивний</em> : null}</b>{subscription && <small>{subscription.status === "paused" ? "Пауза" : subscription.auto_renew ? "Автопродовження увімкнено" : "Без автопродовження"}</small>}</span>
                    <span className="paymentAmountCell"><b>{money(payment.adjustedAmount)}</b><small>{payment.balanceAmount > 0 ? <>Залишок: {money(payment.balanceAmount)}</> : payment.creditAmount > 0 ? <>Кредит: {money(payment.creditAmount)}</> : <>Внесено: {money(Math.max(0, payment.paidAmount - payment.refundedAmount))}</>}{payment.refundedAmount > 0 ? " · повернено " + money(payment.refundedAmount) : ""}</small>{payment.creditAmount > 0 && <em className="paymentCreditHint">Буде враховано в наступному періоді</em>}</span>
                    <span>{payment.dueDate ? new Date(payment.dueDate + "T00:00:00").toLocaleDateString("uk-UA") : "—"}</span>
                    <span className={"paymentStatus " + payment.status}>{statusLabel}</span>
                    <span className="paymentActions">
                      {payment.balanceAmount > 0 && payment.status !== "cancelled" && <button className="link payAction" onClick={() => markPaymentPaid(payment.id)}>Сплатити повністю</button>}
                      {payment.balanceAmount > 0 && payment.status !== "cancelled" && <button className="link" onClick={() => openPaymentAction(payment, "partial")}>Часткова</button>}
                      {payment.paidAmount - payment.refundedAmount > 0 && payment.status !== "cancelled" && <button className="link" onClick={() => openPaymentAction(payment, "refund")}>Повернення</button>}
                      {payment.status !== "cancelled" && <button className="link" onClick={() => openPaymentAction(payment, "adjustment")}>Коригувати</button>}
                      {subscription && subscription.status !== "cancelled" && <button className="link" onClick={() => toggleAutoRenew(subscription.id, !subscription.auto_renew)}>{subscription.auto_renew ? "Вимкнути авто" : "Увімкнути авто"}</button>}
                      {subscription && ["active","paused"].includes(subscription.status) && plans.some((item) => item.isActive && item.id !== subscription.plan_id) && <button className="link" onClick={() => openPlanChange(subscription.id)}>Змінити тариф зараз</button>}
                      {subscription?.status === "paused" ? <button className="link" onClick={() => resumeSubscriptionNow(subscription.id)}>Відновити</button> : subscription && subscription.status === "active" ? <button className="link" onClick={() => openPauseSubscription(subscription.id)}>Пауза</button> : null}
                    </span>
                  </div>;
                })}
              </div>
            </article>
          </div>
          <aside className="paymentsSide">
            <article className="panel tariffPanel">
              <div className="panelHead"><div><p className="eyebrow">Тарифи</p><h2>Абонементи</h2></div><div className="miniActions"><span className="counter">{plans.filter((plan) => plan.isActive).length}</span>{canManagePlans && <button className="link" onClick={openPlanCreate}>+ Тариф</button>}</div></div>
              <div className="planCards">
                {plans.filter((plan) => plan.isActive).map((plan) => <div className="planCard tariffCard" key={plan.id}>
                  <div><b>{plan.name}</b><span>{[plan.days ? plan.days + " днів" : "", plan.lessons ? plan.lessons + " відвідувань" : ""].filter(Boolean).join(" · ")}</span></div>
                  <div className="tariffCardRight"><strong>{plan.price ? money(plan.price) : "Індивідуально"}</strong>{canManagePlans && <button className="tariffEditButton" type="button" title="Редагувати тариф" aria-label={"Редагувати " + plan.name} onClick={() => void openPlanEdit(plan)}><UiIcon name="edit" size={13} /></button>}</div>
                </div>)}
                {plans.filter((plan) => plan.isActive).length === 0 && <div className="emptyState compactEmpty">Активних тарифів немає.</div>}
              </div>
              {plans.some((plan) => !plan.isActive) && <div className="inactiveTariffs">
                <button className="inactiveTariffsToggle" type="button" onClick={() => setShowInactivePlans((value) => !value)}><span>Неактивні</span><small>{plans.filter((plan) => !plan.isActive).length}</small><i>{showInactivePlans ? "↑" : "↓"}</i></button>
                {showInactivePlans && <div className="planCards inactivePlanCards">{plans.filter((plan) => !plan.isActive).map((plan) => <div className="planCard tariffCard inactive" key={plan.id}>
                  <div><b>{plan.name}<em>Неактивний</em></b><span>{[plan.days ? plan.days + " днів" : "", plan.lessons ? plan.lessons + " відвідувань" : ""].filter(Boolean).join(" · ")}</span></div>
                  <div className="tariffCardRight"><strong>{plan.price ? money(plan.price) : "Індивідуально"}</strong>{canManagePlans && <button className="tariffEditButton" type="button" title="Редагувати тариф" aria-label={"Редагувати " + plan.name} onClick={() => void openPlanEdit(plan)}><UiIcon name="edit" size={13} /></button>}</div>
                </div>)}</div>}
              </div>}
            </article>
            <article className="panel financeHint"><p className="eyebrow">MVP</p><h2>Що вже враховано</h2><p>Оплата зберігається окремо від абонемента. Це дозволить пізніше підключити LiqPay, WayForPay чи інший еквайринг без зміни ядра.</p></article>
          </aside>
        </section>}

        {active === "Працівники" && <section className="staffLayout">
          <article className="panel staffPanel">
            <div className="panelHead">
              <div><p className="eyebrow">Команда</p><h2>Працівники</h2></div>
              <div className="staffActions"><button className="search" onClick={() => { setInviteLink(""); setShowInviteForm(true); }}>Запросити в CRM</button><button className="primary" onClick={() => setShowStaffForm(true)}>+ Працівник</button></div>
            </div>
            <div className="staffTable">
              <div className="staffRow staffHead"><span>Працівник</span><span>Роль</span><span>Локації</span><span>Групи</span><span>Статус</span></div>
              {staff.map((member) => <button className="staffRow staffButton" key={member.id} onClick={() => setSelectedStaffId(member.id)}>
                <span className="staffIdentity"><i>{member.fullName[0]}</i><b>{member.fullName}<small>{member.email || member.phone || "Контакти не вказано"}</small></b></span>
                <span>{member.role}</span>
                <span>{member.locationIds.map((id) => locations.find((loc) => loc.id === id)?.name).filter(Boolean).join(", ") || "—"}</span>
                <span>{member.groupIds.length}</span>
                <span className={"staffStatus " + (member.isActive ? "active" : "inactive")}>{member.isActive ? "Активний" : "Неактивний"}</span>
              </button>)}
            </div>
          </article>
          <aside className="panel staffSummary">
            <p className="eyebrow">Команда</p><h2>{staff.filter((x) => x.isActive).length} активних</h2>
            <div className="summaryMetric"><span>Викладачі</span><strong>{staff.filter((x) => x.role === "Викладач" && x.isActive).length}</strong></div>
            <div className="summaryMetric"><span>Адміністрація</span><strong>{staff.filter((x) => ["Власник","Адміністратор","Менеджер"].includes(x.role) && x.isActive).length}</strong></div>
            <div className="summaryMetric"><span>Локацій</span><strong>{locations.filter((x) => x.isActive).length}</strong></div>
          </aside>
        </section>}

        {active === "Локації" && <section className="locationsLayout">
          <div className="panelHead locationsHead">
            <div><p className="eyebrow">Мережа</p><h2>Локації школи</h2></div>
            {canManageLocations && <button className="primary" onClick={openLocationCreation}>+ Додати локацію</button>}
          </div>
          <div className="locationCards">
            {locations.map((location) => {
              const locationStaff = staff.filter((member) => member.locationIds.includes(location.id) && member.isActive);
              const locationGroups = groups.filter((group) => group.location === location.name);
              return <article className="panel locationCard" key={location.id}>
                <div className="locationTop"><span className="locationIcon">⌂</span><div className="locationTopActions"><span className={"staffStatus " + (location.isActive ? "active" : "inactive")}>{location.isActive ? "Активна" : "Неактивна"}</span>{canManageLocations && <button className="locationEditIcon" type="button" aria-label={"Редагувати " + location.name} title="Редагувати локацію" onClick={() => openLocationEdit(location)}><UiIcon name="edit" size={14} /></button>}</div></div>
                <h2>{location.name}</h2>
                <p>{location.address || "Адресу ще не вказано"}</p>
                <div className="locationMetrics"><span><b>{locationStaff.length}</b> працівників</span><span><b>{locationGroups.length}</b> груп</span></div>
                <div className="locationPeople">{locationStaff.slice(0,4).map((member) => <i title={member.fullName} key={member.id}>{member.fullName[0]}</i>)}</div>
              </article>;
            })}
          </div>
        </section>}

                {active === "Налаштування" && <section className="settingsLayout">
          <div className="settingsPrimaryColumn">
            <article className="panel settingsPanel">
              <div className="panelHead"><div><p className="eyebrow">Організація</p><h2>Основні налаштування</h2></div></div>
              <p className="settingsIntro">Ці значення належать конкретній школі або гуртку й не впливають на інші організації в CRM.</p>
              <label>Назва організації<input value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} /></label>
              <div className="formTwo">
                <label>Часовий пояс<input value={organizationTimezone} onChange={(e) => setOrganizationTimezone(e.target.value)} placeholder="Europe/Kyiv" /></label>
                <label>Валюта<input value={organizationCurrency} maxLength={3} onChange={(e) => setOrganizationCurrency(e.target.value.toUpperCase())} placeholder="UAH" /></label>
              </div>
              <label>Локаль<input value={organizationLocale} onChange={(e) => setOrganizationLocale(e.target.value)} placeholder="uk-UA" /></label>
              <button className="primary" disabled={organizationSaving || !organizationName.trim()} onClick={saveOrganizationSettings}>{organizationSaving ? "Зберігаємо…" : "Зберегти налаштування"}</button>
            </article>

            <article className="panel settingsPanel appearanceSettings">
              <div className="panelHead"><div><p className="eyebrow">Інтерфейс</p><h2>Вигляд інтерфейсу</h2></div></div>
              <p className="settingsIntro">Тема та масштаб зберігаються для цього браузера. Це зручно, якщо потрібно зробити CRM контрастнішою або збільшити всі елементи для кращої читабельності.</p>
              <div className="appearanceSettingRow">
                <div><b>Тема</b><small>Світла або темна схема</small></div>
                <div className="appearanceThemeSwitch" role="group" aria-label="Тема інтерфейсу">
                  <button type="button" className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")}>Світла</button>
                  <button type="button" className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")}>Темна</button>
                </div>
              </div>
              <div className="appearanceSettingRow">
                <div><b>Масштаб</b><small>Пропорційно збільшує текст, кнопки, поля та відступи</small></div>
                <div className="uiScaleControl settingsScaleControl" aria-label="Масштаб інтерфейсу">
                  <button type="button" aria-label="Зменшити масштаб" title="Зменшити" disabled={uiScale === UI_SCALE_LEVELS[0]} onClick={() => changeUiScale(-1)}>A−</button>
                  <span><b>{Math.round(uiScale * 100)}%</b><small>масштаб</small></span>
                  <button type="button" aria-label="Збільшити масштаб" title="Збільшити" disabled={uiScale === UI_SCALE_LEVELS[UI_SCALE_LEVELS.length - 1]} onClick={() => changeUiScale(1)}>A+</button>
                </div>
              </div>
            </article>
          </div>
          <aside className="panel settingsHelp">
            <p className="eyebrow">SaaS</p><h2>Налаштування tenant</h2>
            <p>Часовий пояс використовується для дат і розкладу, валюта — для фінансів, локаль — для форматування чисел та дат.</p>
            <div className="summaryMetric"><span>Slug</span><strong>{currentMembership?.organization_slug ?? "—"}</strong></div>
            <div className="summaryMetric"><span>Ваша роль</span><strong>{roleLabel(currentMembership?.role)}</strong></div>
          </aside>
        </section>}

        {active === "Звіти" && <section className="reportsPage">
          <section className="reportStats">
            <article><span>Конверсія в учні</span><strong>{leads.length ? Math.round(activeStudents.length / leads.length * 100) : 0}%</strong><small>{activeStudents.length} з {leads.length} записів</small></article>
            <article><span>Заповненість груп</span><strong>{occupancy}%</strong><small>{occupiedSeats} з {totalCapacity} місць</small></article>
            <article><span>Відвідуваність</span><strong>{attendanceRate}%</strong><small>{overviewReport?.attendance.total ?? attendanceValues.length} відміток</small></article>
            <article><span>Сплачено</span><strong>{money(overviewReport ? overviewReport.payments.paid_minor / 100 : paymentTotals.paid)}</strong><small>зафіксовані платежі</small></article>
          </section>

          <section className="reportsGrid">
            <article className="panel">
              <div className="panelHead"><div><p className="eyebrow">Воронка</p><h2>Заявка → учень</h2></div></div>
              <div className="funnelBars">
                {[
                  ["Нова", overviewFunnelCount(overviewReport, "new", leads.filter((x) => x.status === "Нова").length)],
                  ["Пробне", overviewFunnelCount(overviewReport, "trial_scheduled", leads.filter((x) => x.status === "Пробне заплановано").length)],
                  ["Очікує групу", overviewFunnelCount(overviewReport, "waiting_for_group", waiting.length)],
                  ["Зарахований", overviewFunnelCount(overviewReport, "enrolled", activeStudents.length)],
                ].map(([label,count]) => {
                  const numeric = Number(count);
                  const max = Math.max(1, overviewReport ? overviewReport.funnel.reduce((sum, item) => sum + item.count, 0) : leads.length);
                  return <div className="funnelBar" key={String(label)}><span><b>{label}</b><i>{numeric}</i></span><div><em style={{width: Math.max(4, numeric / max * 100) + "%"}} /></div></div>;
                })}
              </div>
            </article>

            <article className="panel">
              <div className="panelHead"><div><p className="eyebrow">Навчання</p><h2>Відвідування</h2></div><strong className="reportBig">{attendanceRate}%</strong></div>
              <div className="attendanceSummary">
                <span><i className="dot present"></i>Був <b>{overviewReport?.attendance.present ?? attendanceStats.present}</b></span>
                <span><i className="dot late"></i>Запізнився <b>{overviewReport?.attendance.late ?? attendanceStats.late}</b></span>
                <span><i className="dot absent"></i>Відсутній <b>{overviewReport?.attendance.absent ?? attendanceStats.absent}</b></span>
                <span><i className="dot excused"></i>Поважна <b>{overviewReport?.attendance.excused ?? attendanceStats.excused}</b></span>
              </div>
            </article>

            <article className="panel">
              <div className="panelHead"><div><p className="eyebrow">Фінанси</p><h2>Оплати</h2></div></div>
              <div className="financeRows">
                <span><i>Сплачено</i><b>{money(overviewReport ? overviewReport.payments.paid_minor / 100 : paymentTotals.paid)}</b></span>
                <span><i>Очікується</i><b>{money(overviewReport ? overviewReport.payments.pending_minor / 100 : paymentTotals.pending)}</b></span>
                <span><i>Прострочено</i><b>{money(overviewReport ? overviewReport.payments.overdue_minor / 100 : paymentTotals.overdue)}</b></span>
              </div>
            </article>

            <article className="panel">
              <div className="panelHead"><div><p className="eyebrow">Масштаб</p><h2>Організація</h2></div></div>
              <div className="organizationReport">
                <span><strong>{overviewReport?.active_locations ?? locations.filter((x) => x.isActive).length}</strong><small>локацій</small></span>
                <span><strong>{overviewReport?.active_staff ?? staff.filter((x) => x.isActive).length}</strong><small>працівників</small></span>
                <span><strong>{overviewReport?.active_groups ?? groups.length}</strong><small>груп</small></span>
                <span><strong>{overviewReport?.active_students ?? activeStudents.length}</strong><small>учнів</small></span>
              </div>
            </article>
          </section>
        </section>}

                {active === "Групи" && <section className="groupsPage">
          <article className="panel groupsPrimary">
            <div className="panelHead groupsPrimaryHead">
              <div><p className="eyebrow">Основне</p><h2>Активні групи</h2><p className="sectionLead">Відкрийте групу, щоб побачити учасників, відвідування, пропуски, оплати та історію.</p></div>
              <div className="groupsHeadActions"><span className="counter">{groups.length}</span>{waiting.length > 0 && <button className="search" onClick={() => document.getElementById("waiting-groups")?.scrollIntoView({ behavior: "smooth" })}>Очікують: {waiting.length}</button>}<button className="primary compact" onClick={() => openGroupCreation("groups")}>+ Нова група</button></div>
            </div>
            {groups.length === 0 ? <div className="groupsEmptyPrimary">
              <strong>Ще немає створених груп</strong>
              <span>Створіть групу наперед, задайте локацію та регулярний час. Учнів можна додати пізніше.</span><button className="primary compact" onClick={() => openGroupCreation("groups")}>+ Створити групу</button>
            </div> : <div className="groupCards groupCardsPrimary">
              {groups.map((group) => {
                const teacherName = group.teacherName ?? groupTeacher(group.id)?.fullName;
                return <button className="groupCard groupCardButton groupCardPrimary groupCardWide" key={group.id} onClick={() => openGroup(group.id)}>
                  <div className="groupCardTitleBlock">
                    <span className="groupCardIcon">{group.name.slice(0,1)}</span>
                    <div><b>{group.name}</b><small>{teacherName ? "Викладач: " + teacherName : "Викладач не призначений"}</small></div>
                  </div>
                  <div className="groupCardFact"><small>Розклад</small><b>{group.schedule}</b></div>
                  <div className="groupCardFact"><small>Локація</small><b>{group.location}</b></div>
                  <div className="groupCardFact groupCardStudents"><small>Учні</small><b>{group.members.length}/{group.capacity}</b></div>
                  <strong className="groupCardOpen">Відкрити групу →</strong>
                </button>;
              })}
            </div>}
          </article>

          <section className="waitingSecondary" id="waiting-groups">
            <div className="waitingSecondaryHead">
              <div><p className="eyebrow">Формування нових груп</p><h2>Очікують групу <span>{waiting.length}</span></h2><p>Допоміжний список кандидатів. Використовуйте його, коли потрібно сформувати нову групу або дозаповнити існуючу.</p></div>

            </div>
            <article className="panel waitingPanel">
              <div className="candidateControls">
                <label className="candidateSelect">Вік<select value={candidateAgeFilter} onChange={(e) => setCandidateAgeFilter(e.target.value as typeof candidateAgeFilter)}>
                  <option value="all">Усі віки</option>
                  <option value="8-10">8–10 років</option>
                  <option value="11-13">11–13 років</option>
                </select></label>
                <label className="candidateSelect">Рівень<select value={candidateLevelFilter} onChange={(e) => setCandidateLevelFilter(e.target.value)}>
                  <option value="all">Усі рівні</option>
                  {candidateLevels.map((level) => <option value={level} key={level}>{level}</option>)}
                </select></label>
                <label className="candidateSelect">Бажана локація<select value={candidateLocationFilter} onChange={(e) => setCandidateLocationFilter(e.target.value)}>
                  <option value="all">Усі локації</option>
                  <option value="none">Не вказано</option>
                  {locations.filter((location) => location.isActive).map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
                </select></label>
                <label className="candidateSelect">Сортування<select value={candidateSort} onChange={(e) => setCandidateSort(e.target.value as typeof candidateSort)}>
                  <option value="match">Найкращий збіг</option>
                  <option value="age">За віком</option>
                  <option value="name">За ім’ям</option>
                </select></label>
              </div>
              <div className="candidateFilters" aria-label="Фільтр за збігом графіка">
                {([['all','Усі збіги'],['match','Підходить'],['partial','Частково'],['conflict','Узгодити'],['unknown','Невідомо']] as const).map(([value,label]) => <button className={"chip " + (candidateMatchFilter === value ? "active" : "")} onClick={() => setCandidateMatchFilter(value)} key={value}>{label}</button>)}
              </div>
              <div className="candidateList candidateListSecondary">
                {visibleWaiting.length === 0 && <div className="emptyState">За цим фільтром кандидатів немає.</div>}
                {visibleWaiting.map((lead) => { const match = candidateCompatibility(lead, groupSchedule, groupLocationId || null); return <label className={"candidate " + (selectedCandidates.includes(lead.id) ? "selected" : "")} key={lead.id}>
                  <input type="checkbox" checked={selectedCandidates.includes(lead.id)} onChange={() => toggleCandidate(lead.id)} />
                  <span className="candidateAvatar">{lead.child[0]}</span>
                  <span className="candidateMain"><b>{lead.child}</b><small>{lead.age} років · {lead.recommendedLevel ?? "Рівень не вказано"}</small><small>{availabilityLabel(lead.availability ?? [])}{lead.preferredLocationName ? " · " + lead.preferredLocationName : ""}</small><MatchExplanation match={match} /></span>
                  <MatchBadge match={match} />
                </label>})}
              </div>
              <div className="selectionBar">
                <span>Вибрано: <b>{selectedCandidates.length}</b></span>
                <button className="primary" onClick={() => openGroupCreation("candidates")}>{selectedCandidates.length ? "Створити групу з вибраними" : "Створити порожню групу"}</button>
              </div>
            </article>
          </section>
        </section>}

        {active !== "Дашборд" && active !== "Заявки" && active !== "Учні" && active !== "Групи" && active !== "Розклад" && active !== "Відвідування" && active !== "Оплати" && active !== "Працівники" && active !== "Локації" && active !== "Звіти" && <section className="panel placeholder">
          <p className="eyebrow">Наступний модуль</p>
          <h2>{active}</h2>
          <p>Каркас модуля вже передбачений у навігації. Реалізуємо після завершення наскрізного сценарію «заявка → пробне → група → учень».</p>
        </section>}
      </main>

      {showLeadForm && <div className="modalBackdrop">
        <div className="groupModal leadCreateModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => { setShowLeadForm(false); setLeadDuplicateMatches([]); }}>×</button>
          <p className="eyebrow">Нова заявка</p><h2>Додати дитину</h2>
          <div className="formTwo leadCreatePair">
            <label>Ім’я дитини *<input className={leadChildName && personNameError(leadChildName, "Ім’я дитини") ? "inputInvalid" : ""} value={leadChildName} maxLength={120} onChange={(e) => setLeadChildName(e.target.value)} placeholder="Максим" />{leadChildName && personNameError(leadChildName, "Ім’я дитини") && <small className="fieldError">{personNameError(leadChildName, "Ім’я дитини")}</small>}</label>
            <label>Прізвище дитини<input className={leadChildLastName && personNameError(leadChildLastName, "Прізвище дитини") ? "inputInvalid" : ""} value={leadChildLastName} maxLength={120} onChange={(e) => setLeadChildLastName(e.target.value)} placeholder="Коваль" /><small className="leadFormHint">Необов’язково · можна дописати пізніше</small>{leadChildLastName && personNameError(leadChildLastName, "Прізвище дитини") && <small className="fieldError">{personNameError(leadChildLastName, "Прізвище дитини")}</small>}</label>
          </div>
          <div className="formTwo leadCreatePair">
            <label>Вік<input type="number" min={3} max={25} value={leadAge} onChange={(e) => setLeadAge(Number(e.target.value))} /></label>
            <label>Телефон дитини<input type="tel" inputMode="tel" maxLength={19} className={leadChildPhone && uaPhoneError(leadChildPhone, false) ? "inputInvalid" : ""} value={leadChildPhone} onChange={(e) => setLeadChildPhone(e.target.value)} onBlur={() => { if (normalizeUaPhone(leadChildPhone)) setLeadChildPhone(formatUaPhone(leadChildPhone)); void checkManualLeadDuplicates(); }} placeholder="+380 67 123 45 67" /><small className="leadFormHint">Необов’язково</small>{leadChildPhone && uaPhoneError(leadChildPhone, false) && <small className="fieldError">{uaPhoneError(leadChildPhone, false)}</small>}</label>
          </div>
          <label>Ім’я відповідальної особи *<input className={leadContactName && personNameError(leadContactName, "Відповідальна особа") ? "inputInvalid" : ""} value={leadContactName} maxLength={160} autoComplete="name" onChange={(e) => setLeadContactName(e.target.value)} placeholder="Оксана або Оксана Петренко" /><small className="leadFormHint">Прізвище можна дописати пізніше</small>{leadContactName && personNameError(leadContactName, "Відповідальна особа") && <small className="fieldError">{personNameError(leadContactName, "Відповідальна особа")}</small>}</label>
          <label>Телефон відповідального *<input type="tel" inputMode="tel" autoComplete="tel" maxLength={19} className={leadPhone && uaPhoneError(leadPhone) ? "inputInvalid" : ""} value={leadPhone} onChange={(e) => setLeadPhone(e.target.value)} onBlur={() => { if (normalizeUaPhone(leadPhone)) setLeadPhone(formatUaPhone(leadPhone)); void checkManualLeadDuplicates(); }} placeholder="+380 67 123 45 67" />{leadPhone && uaPhoneError(leadPhone) && <small className="fieldError">{uaPhoneError(leadPhone)}</small>}</label>
          {leadDuplicateChecking && <div className="duplicateCheck pending"><span className="syncPulse" />Перевіряємо номер у CRM…</div>}
          {!leadDuplicateChecking && leadDuplicateMatches.length > 0 && <div className={"duplicateCheck " + (leadDuplicateMatches.some((item) => item.likely_same_student) ? "blocked" : "warning")}>
            <b>{leadDuplicateMatches.some((item) => item.likely_same_student) ? "Такий номер уже зареєстровано" : "Цей номер уже є в CRM"}</b>
            <small>{leadDuplicateMatches.some((item) => item.likely_same_student) ? "Схоже, це вже існуюча дитина. Перевірте картку, щоб не створювати дубль." : "Можливо, це інша дитина з тієї самої сім’ї. Створення дозволено, але перевірте збіг."}</small>
            <div className="duplicateMatches">{leadDuplicateMatches.slice(0,4).map((match) => <button type="button" className="duplicateMatch" key={match.student_id} onClick={() => openDuplicateStudent(match)}>
              <span><b>{match.first_name} {match.last_name ?? ""}</b><small>{match.age ?? "—"} років · {crmStatusLabel(match.crm_status)}</small><small>{match.contact_name ?? "Контакт не вказано"}{match.contact_phone ? " · " + formatUaPhone(match.contact_phone) : ""}</small></span>
              <strong>Перейти та перевірити →</strong>
            </button>)}</div>
          </div>}
          <label>Джерело<select value={leadSource} onChange={(e) => setLeadSource(e.target.value)}>
            <option value="phone">Телефон</option>
            <option value="website">Сайт</option>
            <option value="instagram">Instagram</option>
            <option value="recommendation">Рекомендація</option>
            <option value="walk-in">Зайшли особисто</option>
          </select></label>
          <label>Коментар<textarea value={leadComment} onChange={(e) => setLeadComment(e.target.value)} placeholder="Що цікавить, бажаний час, примітки…" /></label>
          <button className="primary full" disabled={leadDuplicateChecking || leadDuplicateMatches.some((item) => item.likely_same_student) || Boolean(personNameError(leadChildName, "Ім’я дитини") || (leadChildLastName.trim() ? personNameError(leadChildLastName, "Прізвище дитини") : "") || uaPhoneError(leadChildPhone, false) || personNameError(leadContactName, "Відповідальна особа") || uaPhoneError(leadPhone))} onClick={createManualLead}>{leadDuplicateChecking ? "Перевіряємо номер…" : leadDuplicateMatches.some((item) => item.likely_same_student) ? "Перевірте існуючу картку" : "Створити заявку"}</button>
        </div>
      </div>}

      {showInviteForm && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowInviteForm(false)}>×</button>
          <p className="eyebrow">Доступ до CRM</p><h2>Запросити працівника</h2>
          {!inviteLink ? <>
            <label>Email *<input type="email" autoComplete="email" maxLength={255} className={inviteEmail && emailError(inviteEmail, true) ? "inputInvalid" : ""} value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="teacher@example.com" />{inviteEmail && emailError(inviteEmail, true) && <small className="fieldError">{emailError(inviteEmail, true)}</small>}</label>
            <label>Роль<select value={inviteRole} onChange={(e) => { const role = e.target.value as StaffRoleDemo; setInviteRole(role); if (role === "Викладач") setInviteCanTeach(true); }}>{["Адміністратор","Менеджер","Викладач","Бухгалтер"].map((role) => <option key={role}>{role}</option>)}</select></label>
            <label className="toggleRow responsibilityToggle"><input type="checkbox" checked={inviteCanTeach || inviteRole === "Викладач"} disabled={inviteRole === "Викладач"} onChange={(e) => setInviteCanTeach(e.target.checked)} /><span><b>Може викладати</b><small>Дозволяє призначати цього працівника викладачем груп незалежно від його ролі в CRM.</small></span></label>
            <button className="primary full" disabled={Boolean(emailError(inviteEmail, true))} onClick={createInvitation}>Створити запрошення</button>
          </> : <>
            <div className="inviteSuccess"><b>Запрошення готове</b><p>Надішліть це посилання працівнику. Воно одноразове та діє 7 днів.</p><code>{inviteLink}</code></div>
            <button className="primary full" onClick={() => navigator.clipboard?.writeText(inviteLink)}>Копіювати посилання</button>
          </>}
        </div>
      </div>}

            {showStaffForm && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowStaffForm(false)}>×</button>
          <p className="eyebrow">Команда</p><h2>Новий працівник</h2>
          <label>Ім’я та прізвище *<input autoComplete="name" maxLength={160} className={staffName && personNameError(staffName, "Ім’я та прізвище") ? "inputInvalid" : ""} value={staffName} onChange={(e) => setStaffName(e.target.value)} placeholder="Іван Петренко" />{staffName && personNameError(staffName, "Ім’я та прізвище") && <small className="fieldError">{personNameError(staffName, "Ім’я та прізвище")}</small>}</label>
          <label>Роль<select value={staffRole} onChange={(e) => { const role = e.target.value as StaffRoleDemo; setStaffRole(role); if (role === "Викладач") setStaffCanTeach(true); }}>{["Власник","Адміністратор","Менеджер","Викладач","Бухгалтер"].map((role) => <option key={role}>{role}</option>)}</select></label>
          <label className="toggleRow responsibilityToggle"><input type="checkbox" checked={staffCanTeach || staffRole === "Викладач"} disabled={staffRole === "Викладач"} onChange={(e) => setStaffCanTeach(e.target.checked)} /><span><b>Може викладати</b><small>Працівника можна буде призначати викладачем груп.</small></span></label>
          <div className="formTwo"><label>Email<input type="email" autoComplete="email" maxLength={255} className={staffEmail && emailError(staffEmail) ? "inputInvalid" : ""} value={staffEmail} onChange={(e) => setStaffEmail(e.target.value)} />{staffEmail && emailError(staffEmail) && <small className="fieldError">{emailError(staffEmail)}</small>}</label><label>Телефон<input type="tel" inputMode="tel" autoComplete="tel" maxLength={19} className={staffPhone && uaPhoneError(staffPhone, false) ? "inputInvalid" : ""} value={staffPhone} onChange={(e) => setStaffPhone(e.target.value)} onBlur={() => { if (normalizeUaPhone(staffPhone)) setStaffPhone(formatUaPhone(staffPhone)); }} placeholder="+380 67 123 45 67" />{staffPhone && uaPhoneError(staffPhone, false) && <small className="fieldError">{uaPhoneError(staffPhone, false)}</small>}</label></div><div className="formNotice">Для працівника потрібно вказати хоча б email або телефон.</div>
          <button className="primary full" disabled={Boolean(personNameError(staffName, "Ім’я та прізвище") || emailError(staffEmail) || uaPhoneError(staffPhone, false) || (!staffEmail.trim() && !staffPhone.trim()))} onClick={createStaffMember}>Додати працівника</button>
        </div>
      </div>}

      {showLocationForm && <div className="modalBackdrop">
        <div className="groupModal locationEditModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={closeLocationForm}>×</button>
          <p className="eyebrow">Мережа</p><h2>{locationEditId ? "Редагувати локацію" : "Нова локація"}</h2>
          {locationReturnToGroup && <p className="modalIntro">Після збереження повернемо вас до створення групи й виберемо нову локацію автоматично.</p>}
          <label>Назва<input autoFocus value={locationName} onChange={(e) => setLocationName(e.target.value)} placeholder="AeroKids Центр" /></label>
          <label>Адреса<input value={locationAddress} onChange={(e) => setLocationAddress(e.target.value)} placeholder="Івано-Франківськ" /></label>
          <button className="primary full" disabled={!locationName.trim() || locationSaving || locationDeleteSaving} onClick={saveLocationDemo}>{locationSaving ? "Зберігаємо…" : locationEditId ? "Зберегти зміни" : "Створити локацію"}</button>
          {locationEditId && <div className="subtleDeleteRow"><button className="subtleDangerAction" type="button" disabled={locationSaving || locationDeleteSaving} onClick={deleteLocationDemo}>{locationDeleteSaving ? "Видаляємо…" : "Видалити локацію"}</button></div>}
        </div>
      </div>}

      {selectedGroupId && <div className="drawerBackdrop groupPageBackdrop" onClick={closeGroupDetail}>
        <aside className="drawer groupDetailDrawer" onClick={(e) => e.stopPropagation()}>
          <div className="groupPageTopbar">
            <button className="groupBackButton" aria-label="До списку груп" title="До списку груп" onClick={() => { setSelectedGroupId(null); setGroupDetail(null); setShowGroupCandidatePicker(false); setGroupCandidateId(""); setGroupTeacherEditing(false); }}><UiIcon name="back" size={16} /><span>До списку груп</span></button>
            <button className="groupPageClose" aria-label="Закрити групу" title="Закрити" onClick={() => { setSelectedGroupId(null); setGroupDetail(null); setShowGroupCandidatePicker(false); setGroupCandidateId(""); setGroupTeacherEditing(false); }}><UiIcon name="x" size={18} /></button>
          </div>
          <p className="eyebrow">Група</p>
          <div className="groupDetailHero">
            <div className="groupDetailIdentity">
              <div className="groupDetailTitleRow">
                <h2>{groupDetail?.group.name ?? selectedGroup?.name ?? "Група"}</h2>
                {canEditGroups && <button className="groupEditIcon" type="button" aria-label="Редагувати групу" title="Редагувати групу" onClick={beginGroupEdit}><UiIcon name="edit" size={15} /></button>}
              </div>
              <div className="groupDetailMeta">
                <span>{selectedGroup?.location ?? "Локація не вказана"}</span>
                <span>{selectedGroup?.schedule ?? "Розклад не вказаний"}</span>
                {canManageStaff
                  ? <button className="groupTeacherLink" onClick={() => { setSelectedGroupTeacherId(groupTeacher(selectedGroupId)?.id ?? ""); setGroupTeacherEditing(true); }}>
                      {selectedGroup?.teacherName ?? selectedTeacher?.fullName ? "Викладач: " + (selectedGroup?.teacherName ?? selectedTeacher?.fullName) : "+ Призначити викладача"}
                    </button>
                  : <span>{selectedGroup?.teacherName ?? selectedTeacher?.fullName ? "Викладач: " + (selectedGroup?.teacherName ?? selectedTeacher?.fullName) : "Викладач не призначений"}</span>}
              </div>
            </div>
            <div className="groupDetailHeroActions"><strong>{groupDetail?.members.length ?? selectedGroup?.members.length ?? 0}/{groupDetail?.group.capacity ?? selectedGroup?.capacity ?? "—"}</strong>{canManageLeads && <button className="primary compact" onClick={() => { setShowGroupCandidatePicker((value) => !value); setGroupCandidateId(existingGroupCandidates[0]?.id ?? ""); }}>+ Додати учня</button>}</div>
          </div>
          {groupEditing && <div className="groupEditPanel">
            <div className="groupEditPanelHead">
              <div><b>Редагування групи</b><small>Назва, місткість, локація, викладач і регулярний розклад.</small></div>
              <button className="groupEditPanelClose" type="button" aria-label="Закрити редагування" onClick={() => { setGroupEditing(false); setGroupEditError(""); }}><UiIcon name="x" size={16} /></button>
            </div>
            <label>Назва групи<input autoFocus value={groupEditName} maxLength={160} onChange={(e) => { setGroupEditName(e.target.value); setGroupEditError(""); }} /></label>
            <div className="formTwo">
              <label>Місткість<input type="number" min={Math.max(1, groupDetail?.members.length ?? selectedGroup?.members.length ?? 0)} max={100} value={groupEditCapacity} onChange={(e) => { setGroupEditCapacity(Number(e.target.value)); setGroupEditError(""); }} /></label>
              <label>Локація <small>(необов’язково)</small><select value={groupEditLocationId} onChange={(e) => setGroupEditLocationId(e.target.value)}>
                <option value="">Без локації</option>
                {activeLocations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
              </select></label>
            </div>
            {canManageStaff && <label>Викладач <small>(необов’язково)</small><select value={groupEditTeacherId} onChange={(e) => setGroupEditTeacherId(e.target.value)}>
              <option value="">Не призначено</option>
              {activeTeachers.map((teacher) => <option value={teacher.id} key={teacher.id}>{teacher.fullName}</option>)}
            </select></label>}
            <div className="groupCreateScheduleHead"><div><b>Регулярний розклад</b><small>Можна змінити день, годину, тривалість, додати або прибрати заняття.</small></div></div>
            <ScheduleSlotEditor value={groupEditSchedule} onChange={(slots) => { setGroupEditSchedule(slots); setGroupEditError(""); }} />
            {groupEditSchedule.length === 0 && <div className="groupEditHint">Розклад можна залишити порожнім і додати пізніше.</div>}
            {groupEditError && <div className="groupCreateError">{groupEditError}</div>}
            <div className="groupEditFooter">
              <button className="subtleDangerAction" type="button" disabled={groupEditSaving || groupDeleteSaving} onClick={deleteSelectedGroup}>{groupDeleteSaving ? "Видаляємо…" : "Видалити групу"}</button>
              <div className="groupEditActions">
                <button className="search" type="button" disabled={groupEditSaving || groupDeleteSaving} onClick={() => { setGroupEditing(false); setGroupEditError(""); }}>Скасувати</button>
                <button className="primary" type="button" disabled={groupEditSaving || groupDeleteSaving || !groupEditName.trim() || hasDuplicateSlots(groupEditSchedule)} onClick={saveGroupEdit}>{groupEditSaving ? "Зберігаємо…" : "Зберегти зміни"}</button>
              </div>
            </div>
          </div>}
          {canManageStaff && groupTeacherEditing && <div className="groupTeacherAssign">
            <label>Викладач<select autoFocus value={selectedGroupTeacherId} onChange={(e) => setSelectedGroupTeacherId(e.target.value)}>
              <option value="">Не призначено</option>
              {activeTeachers.map((teacher) => <option value={teacher.id} key={teacher.id}>{teacher.fullName}</option>)}
            </select></label>
            <div className="groupTeacherAssignActions"><button className="search" onClick={() => setGroupTeacherEditing(false)}>Скасувати</button><button className="primary" disabled={groupTeacherSaving} onClick={assignTeacherToSelectedGroup}>{groupTeacherSaving ? "Зберігаємо…" : "Зберегти"}</button></div>
          </div>}
          {showGroupCandidatePicker && <div className="groupCandidatePicker">
            <div className="groupCandidatePickerHead"><div><b>Нові учасники</b><small>Кандидати, яких можна додати до цієї групи.</small></div><span>{existingGroupCandidates.length} кандидатів</span></div>
            {existingGroupCandidates.length === 0 ? <div className="emptyState compactEmpty">Немає кандидатів після пробного, яких можна додати до цієї групи.</div> : <div className="groupCandidateRows">
              {existingGroupCandidates.map((candidate) => {
                const slots = (groupDetail?.schedules ?? []).map((slot) => ({ weekday: slot.weekday, start_time: slot.start_time.slice(0,5), duration_minutes: slot.duration_minutes }));
                const match = candidateCompatibility(candidate, slots, groupDetail?.group.location_id ?? null);
                return <article className="groupMemberCard groupCandidateMemberRow" key={candidate.id}>
                  <div className="groupMemberTop"><span className="candidateAvatar">{candidate.child[0]}</span><div><b>{candidate.child}</b><small>{candidate.age} років · {candidate.recommendedLevel ?? "рівень не вказано"} · {candidate.status}</small><small>{candidate.parent}{candidate.phone ? " · " + formatUaPhone(candidate.phone) : ""}</small></div></div>
                  <div className="candidateRowMatch"><MatchBadge match={match} /><small>{availabilityLabel(candidate.availability ?? [])}</small></div>
                  <button className="primary compact" disabled={groupCandidateSaving && groupCandidateId === candidate.id} onClick={() => addCandidateToExistingGroup(candidate.id)}>{groupCandidateSaving && groupCandidateId === candidate.id ? "Додаємо…" : "Додати до групи"}</button>
                </article>;
              })}
            </div>}
            <div className="groupCandidatePickerActions"><button className="search" onClick={() => { setShowGroupCandidatePicker(false); setGroupCandidateId(""); }}>Закрити</button></div>
          </div>}
          {groupDetailLoading && <div className="emptyState">Завантажуємо дані групи…</div>}
          {!apiEnabled && selectedGroup && <div className="groupMemberList">{selectedGroup.members.map((studentId) => {
            const student = leads.find((item) => item.id === studentId);
            const studentPayments = payments.filter((item) => item.studentId === studentId);
            const due = studentPayments.find((item) => item.status === "overdue") ?? studentPayments.find((item) => item.status === "pending");
            return <article className="groupMemberCard" key={studentId}>
              <div className="groupMemberTop"><span className="candidateAvatar">{student?.child?.[0] ?? "?"}</span><div><b>{student?.child ?? "Учень"}</b><small>{student?.age ?? "—"} років · {student?.parent ?? "Контакт не вказано"}</small></div></div>
              <div className="groupMemberMetrics"><span>Оплата <b>{due ? (due.status === "overdue" ? "прострочена" : "очікується") : "✓"}</b></span><span>До дати <b>{due?.dueDate ? new Date(due.dueDate).toLocaleDateString("uk-UA") : "—"}</b></span></div>
              <button className="link" onClick={() => { setSelectedStudentId(studentId); setSelectedGroupId(null); }}>Відкрити учня →</button>
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
                      <small className="groupRosterContact">{member.contact_name ?? "Відповідальний не вказаний"}{member.contact_phone ? " · " + formatUaPhone(member.contact_phone) : ""}</small>
                    </div>
                  </div>
                  <button className="groupRosterStudentLink" onClick={() => { setSelectedStudentId(member.student_id); closeGroupDetail(); setActive("Учні"); }}>Картка учня →</button>
                </div>

                <button className="groupMemberMetricButton attendanceMetric groupRosterMetric" onClick={() => goToStudentAttendance(member.student_id, groupDetail.group.id)}>
                  <span className="groupRosterMetricHead"><small>Відвідування</small><b>{member.attendance.attendance_rate}%</b></span>
                  <span className="groupRosterProgress"><i style={{ width: Math.max(0, Math.min(100, member.attendance.attendance_rate)) + "%" }} /></span>
                  <em>{member.attendance.present} був · {member.attendance.late} запізн. · {member.attendance.absent} нема · {member.attendance.excused} поважн.</em>
                  <span className="groupRosterOpen">Журнал →</span>
                </button>

                {member.billing ? <div className="groupMemberFinanceCell groupRosterFinance">
                  <button className="groupMemberMetricButton paymentMetric groupRosterPayment" onClick={() => goToStudentPayments(member.student_id, latestPayment?.id)}>
                    <span className="groupRosterMetricHead">
                      <small>Оплата</small>
                      <b className={"groupPaymentBadge " + member.billing.status}>{billingLabel}</b>
                    </span>
                    <span className="groupRosterPlan">
                      <b>{member.billing.plan_name ?? "Тариф не вказано"}</b>
                      {usage && <small>{usage} занять{remaining != null ? " · залишилось " + remaining : ""}</small>}
                    </span>
                    <span className="groupRosterPaymentFooter">
                      <small>{member.billing.subscription_ends_on ? "До " + new Date(member.billing.subscription_ends_on + "T00:00:00").toLocaleDateString("uk-UA") : "Без дати завершення"}</small>
                      <b className={member.billing.amount_due_minor > 0 ? "debt" : "paid"}>{member.billing.amount_due_minor > 0 ? "Борг " + money(member.billing.amount_due_minor / 100) : "Оплачено"}</b>
                    </span>
                  </button>
                  {member.payments.length > 0 && <details className="memberPayments memberPaymentsInline groupRosterHistory">
                    <summary>Історія оплат ({member.payments.length})</summary>
                    <div>{member.payments.map((payment) => <button className="memberPaymentHistoryRow" key={payment.id} onClick={() => goToStudentPayments(member.student_id, payment.id)}><span>{payment.note ?? "Нарахування"}<small>{payment.due_date ? "До " + new Date(payment.due_date + "T00:00:00").toLocaleDateString("uk-UA") : "Без дати"}</small></span><b>{money(payment.adjusted_amount_minor / 100)}<small>{payment.balance_minor > 0 ? "Залишок " + money(payment.balance_minor / 100) : payment.status === "cancelled" ? "Скасовано" : payment.status === "refunded" ? "Повернено" : "Сплачено"}</small></b></button>)}</div>
                  </details>}
                </div> : <div className="groupMemberFinanceCell groupRosterFinance"><span className="groupMemberMetricStatic"><small>Оплата</small><b>Приховано для ролі</b><em>Фінансові дані недоступні</em></span></div>}
              </article>;
            })}
          </div>}
        </aside>
      </div>}

      {selectedStaff && <div className="drawerBackdrop" onClick={() => setSelectedStaffId(null)}>
        <aside className="drawer studentDrawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setSelectedStaffId(null)}>×</button>
          <p className="eyebrow">Працівник</p>
          <div className="studentHero"><span>{selectedStaff.fullName[0]}</span><div><h2>{selectedStaff.fullName}</h2><p>{selectedStaff.role}{selectedStaff.canTeach ? " · Викладає" : ""}</p></div></div>
          <div className="contactCard"><span>Контакти</span><b>{selectedStaff.email || "Email не вказано"}</b><a href={"tel:" + selectedStaff.phone.replace(/\s/g,"")}>{selectedStaff.phone || "Телефон не вказано"}</a></div>
          <div className="studentSection"><h3>Обов’язки</h3><label className="toggleRow responsibilityToggle"><input type="checkbox" checked={selectedStaff.canTeach || selectedStaff.role === "Викладач"} disabled={selectedStaff.role === "Викладач"} onChange={async (e) => {
            const next = e.target.checked;
            if (apiEnabled && session) {
              try {
                await apiPatch(`/staff/${selectedStaff.id}`, { can_teach: next }, session);
                await syncWorkspace(session);
              } catch (error) {
                setWorkspaceError(error instanceof Error ? error.message : "Не вдалося змінити обов’язки працівника.");
              }
              return;
            }
            setStaff((items) => items.map((item) => item.id === selectedStaff.id ? { ...item, canTeach: next } : item));
          }} /><span><b>Може викладати</b><small>Можна призначати викладачем груп незалежно від ролі доступу.</small></span></label></div>
          <div className="studentSection"><h3>Локації</h3><div className="assignmentList">{locations.map((location) => <label key={location.id}><input type="checkbox" checked={selectedStaff.locationIds.includes(location.id)} onChange={() => toggleStaffLocation(selectedStaff.id, location.id)} /><span>{location.name}<small>{location.address}</small></span></label>)}</div></div>
          <div className="studentSection"><h3>Групи</h3>{!selectedStaff.canTeach && selectedStaff.role !== "Викладач" && <div className="formNotice">Щоб призначати групи, увімкніть обов’язок «Може викладати».</div>}<div className="assignmentList">{groups.map((group) => <label key={group.id} className={!selectedStaff.canTeach && selectedStaff.role !== "Викладач" ? "assignmentDisabled" : ""}><input type="checkbox" disabled={!selectedStaff.canTeach && selectedStaff.role !== "Викладач"} checked={selectedStaff.groupIds.includes(group.id)} onChange={() => toggleStaffGroup(selectedStaff.id, group.id)} /><span>{group.name}<small>{group.schedule}</small></span></label>)}</div></div>
          <div className="studentSection"><h3>Статус</h3><button className="search full" onClick={async () => {
            if (apiEnabled && session) {
              try {
                await apiPatch(`/staff/${selectedStaff.id}`, { is_active: !selectedStaff.isActive }, session);
                await syncWorkspace(session);
                return;
              } catch {
                return;
              }
            }
            setStaff((items) => items.map((item) => item.id === selectedStaff.id ? {...item,isActive:!item.isActive} : item));
          }}>{selectedStaff.isActive ? "Деактивувати працівника" : "Активувати працівника"}</button></div>
          {apiEnabled && selectedStaff.email && <div className="studentSection">
            <h3>Доступ до CRM</h3>
            {!staffResetLink ? <button className="search full" onClick={createStaffPasswordReset}>Створити посилання для нового пароля</button> : <div className="inviteSuccess">
              <b>Посилання готове</b>
              <p>Воно одноразове та діє 1 годину. Надішліть його працівнику приватно.</p>
              <code>{staffResetLink}</code>
              <button className="primary full" onClick={() => navigator.clipboard?.writeText(staffResetLink)}>Копіювати посилання</button>
            </div>}
          </div>}
        </aside>
      </div>}

            {showPlanForm && <div className="modalBackdrop">
        <div className="groupModal tariffEditModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => { setShowPlanForm(false); setPlanEditId(null); }}>×</button>
          <p className="eyebrow">Тарифи</p><h2>{planEditId ? "Редагувати тариф" : "Новий тариф"}</h2>
          <p className="modalIntro">Тариф — шаблон для нових і наступних періодів. Уже створені абонементи зберігають свої умови до завершення.</p>
          <label>Назва<input value={planName} onChange={(e) => setPlanName(e.target.value)} placeholder="8 занять / 30 днів" /></label>
          <div className="formTwo">
            <label>Ціна, грн<input type="text" inputMode="numeric" pattern="[0-9]*" placeholder="2000" value={planPrice} onChange={(e) => setPlanPrice(e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, ""))} /></label>
            <label>Днів<input type="text" inputMode="numeric" pattern="[0-9]*" placeholder="30" value={planDays} onChange={(e) => setPlanDays(e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, ""))} /><small className="fieldHint">Можна залишити порожнім, якщо обмеження тільки за відвідуваннями.</small></label>
          </div>
          <label>Відвідувань<input type="text" inputMode="numeric" pattern="[0-9]*" placeholder="8" value={planLessons} onChange={(e) => setPlanLessons(e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, ""))} /><small className="fieldHint">Можна залишити порожнім для необмежених відвідувань у межах днів.</small></label>
          <div className="formNotice tariffRuleNotice">Потрібно заповнити хоча б одне: <b>дні</b> або <b>відвідування</b>. Якщо заповнені обидва — період завершується за правилом, що настане раніше.</div>
          {planEditId && <label className="toggleRow"><input type="checkbox" checked={planActive} onChange={(e) => setPlanActive(e.target.checked)} /><span><b>Активний тариф</b><small>Неактивний тариф не можна призначити новому учню, але чинні абонементи залишаються в історії та довикористовуються.</small></span></label>}
          <button className="primary full" disabled={planSaving || !planName.trim() || planPrice === "" || (!planDays && !planLessons)} onClick={savePlan}>{planSaving ? "Зберігаємо…" : planEditId ? "Зберегти зміни" : "Створити тариф"}</button>
          {planEditId && <div className="tariffHistoryWrap">
            <button className="subtleHistoryAction" type="button" disabled={planHistoryLoading} onClick={() => planHistoryOpen ? setPlanHistoryOpen(false) : void loadPlanHistory()}>{planHistoryLoading ? "Завантажуємо…" : planHistoryOpen ? "Сховати історію змін" : "Історія змін тарифу"}</button>
            {planHistoryOpen && <div className="tariffHistoryList">
              {planHistory.length === 0 && <small>Змін цього тарифу ще не було.</small>}
              {planHistory.map((event) => <div key={event.id}><span>{new Date(event.created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" })}</span><b>{event.event_type === "subscription_plan.created" ? "Створено" : "Змінено"}</b><small>{tariffHistoryDetail(event)}</small></div>)}
            </div>}
          </div>}
        </div>
      </div>}

            {showPaymentForm && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowPaymentForm(false)}>×</button>
          <p className="eyebrow">Нарахування</p><h2>Створити оплату</h2>
          <label>Учень<select value={paymentStudentId} onChange={(e) => setPaymentStudentId(e.target.value)}>{activeStudents.map((student) => <option value={student.id} key={student.id}>{student.child} · відповідальний: {student.parent}</option>)}</select></label>
          <label>Абонемент<select value={paymentPlanId} onChange={(e) => setPaymentPlanId(e.target.value)}>{plans.filter((plan) => plan.isActive && plan.price > 0).map((plan) => <option value={plan.id} key={plan.id}>{plan.name} · {money(plan.price)}</option>)}</select></label>
          <label>Оплатити до<input type="date" value={paymentDueDate} min={localDateInput(new Date())} onChange={(e) => setPaymentDueDate(e.target.value)} /></label>
          <label className="toggleRow"><input type="checkbox" checked={paymentAutoRenew} onChange={(e) => setPaymentAutoRenew(e.target.checked)} /><span><b>Автопродовження</b><small>Наступне нарахування створиться автоматично перед завершенням цього періоду.</small></span></label>
          {activeStudents.length === 0 && <div className="formNotice">Спочатку зарахуйте хоча б одного учня.</div>}
          {!plans.some((plan) => plan.isActive && plan.price > 0) && <div className="formNotice">Створіть або активуйте тариф із ціною, щоб зробити нарахування.</div>}
          <button className="primary full" disabled={paymentSaving || !paymentStudentId || !paymentPlanId || !plans.some((plan) => plan.id === paymentPlanId && plan.isActive && plan.price > 0)} onClick={createPayment}>{paymentSaving ? "Створюємо…" : "Створити нарахування"}</button>
        </div>
      </div>}

      {paymentActionId && paymentActionType && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => { setPaymentActionId(null); setPaymentActionType(null); }}>×</button>
          <p className="eyebrow">Фінансова операція</p>
          <h2>{paymentActionType === "partial" ? "Часткова оплата" : paymentActionType === "refund" ? "Повернення коштів" : "Коригування нарахування"}</h2>
          <label>Сума<input type="text" inputMode="decimal" value={paymentActionAmount} onChange={(e) => setPaymentActionAmount(e.target.value.replace(/[^0-9.,]/g, "").replace(",", "."))} placeholder="0" /></label>
          {paymentActionType === "partial" && <label>Спосіб<select value={paymentActionMethod} onChange={(e) => setPaymentActionMethod(e.target.value as typeof paymentActionMethod)}><option value="card">Картка</option><option value="cash">Готівка</option><option value="bank">Переказ</option></select></label>}
          {paymentActionType === "adjustment" && <label>Тип коригування<select value={paymentAdjustmentDirection} onChange={(e) => setPaymentAdjustmentDirection(e.target.value as typeof paymentAdjustmentDirection)}><option value="decrease">Зменшити нарахування</option><option value="increase">Збільшити нарахування</option></select></label>}
          <label>{paymentActionType === "refund" ? "Причина повернення" : paymentActionType === "adjustment" ? "Причина коригування" : "Коментар"}<textarea value={paymentActionReason} onChange={(e) => setPaymentActionReason(e.target.value)} placeholder={paymentActionType === "refund" ? "Наприклад: перерахунок за невикористані заняття" : "Необов’язково"} /></label>
          {paymentActionType === "refund" && <div className="formNotice">Повернення одночасно зменшує суму нарахування на цю ж величину, тому після коректного повернення новий борг автоматично не виникає.</div>}
          <button className="primary full" disabled={paymentActionSaving || !paymentActionAmount} onClick={submitPaymentAction}>{paymentActionSaving ? "Зберігаємо…" : "Підтвердити"}</button>
        </div>
      </div>}

      {planChangeSubscriptionId && <div className="modalBackdrop">
        <div className="groupModal tariffChangeModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => { setPlanChangeSubscriptionId(null); setPlanChangeResult(""); }}>×</button>
          <p className="eyebrow">Абонемент</p><h2>Змінити тариф зараз</h2>
          {!planChangeResult ? <>
            <div className="formNotice">Вже використані заняття залишаться за старою ціною. Лише невикористані заняття поточного періоду перерахуються за новою ціною. Різниця стане кредитом або боргом.</div>
            <label>Новий тариф<select value={planChangePlanId} onChange={(e) => setPlanChangePlanId(e.target.value)}>{plans.filter((plan) => plan.isActive && plan.id !== subscriptions.find((item) => item.id === planChangeSubscriptionId)?.plan_id).map((plan) => <option value={plan.id} key={plan.id}>{plan.name} · {money(plan.price)} · {[plan.days ? plan.days + " днів" : "", plan.lessons ? plan.lessons + " відв." : ""].filter(Boolean).join(" / ")}</option>)}</select></label>
            <label>Причина зміни<textarea value={planChangeReason} onChange={(e) => setPlanChangeReason(e.target.value)} maxLength={300} placeholder="Коротко: чому тариф змінюється з поточного періоду" /></label>
            <button className="primary full" disabled={planChangeSaving || !planChangePlanId || !planChangeReason.trim()} onClick={submitPlanChange}>{planChangeSaving ? "Перераховуємо…" : "Змінити і перерахувати"}</button>
          </> : <div className="tariffChangeSuccess"><b>✓ Перераховано</b><p>{planChangeResult}</p><button className="primary full" onClick={() => { setPlanChangeSubscriptionId(null); setPlanChangeResult(""); }}>Закрити</button></div>}
        </div>
      </div>}

      {pauseSubscriptionId && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setPauseSubscriptionId(null)}>×</button>
          <p className="eyebrow">Абонемент</p><h2>Поставити на паузу</h2>
          <label>Пауза з<input type="date" value={pauseStart} onChange={(e) => setPauseStart(e.target.value)} /></label>
          <label>Відновити з<input type="date" value={pauseResumeOn} min={pauseStart} onChange={(e) => setPauseResumeOn(e.target.value)} /><small className="fieldHint">Можна залишити порожнім і відновити вручну пізніше.</small></label>
          <label>Причина<textarea value={pauseNote} onChange={(e) => setPauseNote(e.target.value)} placeholder="Канікули, хвороба, поїздка…" /></label>
          <div className="formNotice">Після відновлення кінець абонемента автоматично посунеться на фактичну кількість днів паузи.</div>
          <button className="primary full" onClick={submitPauseSubscription}>Поставити на паузу</button>
        </div>
      </div>}

      {selectedStudent && <div className="drawerBackdrop" onClick={() => setSelectedStudentId(null)}>
        <aside className="drawer studentDrawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setSelectedStudentId(null)}>×</button>
          <p className="eyebrow">Картка учня</p>
          <div className="studentHero">
            <span>{selectedStudent.child[0]}</span>
            <div><h2>{selectedStudent.child}</h2><p>{selectedStudent.age} років · {studentStates[selectedStudent.id] ?? "Активний"}</p></div>
          </div>
          <div className="studentInfoGrid">
            <div><span>Група</span><b>{studentGroup(selectedStudent.id)?.name ?? "Без групи"}</b><small>{studentGroup(selectedStudent.id)?.schedule ?? "Розклад не задано"}</small></div>
            <div><span>Локація</span><b>{studentGroup(selectedStudent.id)?.location ?? "Без локації"}</b></div>
          </div>
          <div className="contactCard"><span>Контакт</span><b>{selectedStudent.parent}</b><a href={"tel:" + selectedStudent.phone.replace(/\s/g, "")}>{selectedStudent.phone}</a></div>

          {canManageStudents && <>
            <div className="studentSection">
              <h3>Статус учня</h3>
              <div className="segmented">
                {(["Активний","Пауза","Архів"] as const).map((state) => <button className={(studentStates[selectedStudent.id] ?? "Активний") === state ? "active" : ""} onClick={() => setStudentLifecycle(selectedStudent.id, state)} key={state}>{state}</button>)}
              </div>
            </div>

            <div className="studentSection">
              <h3>{studentGroup(selectedStudent.id) ? "Перевести в іншу групу" : "Додати до групи"}</h3>
              <select className="transferSelect" value={transferGroupId ?? ""} onChange={(e) => setTransferGroupId(e.target.value || null)}>
                <option value="">Оберіть групу</option>
                {groups.map((group) => <option value={group.id} key={group.id}>{group.name} · {group.members.length}/{group.capacity}</option>)}
              </select>
              <button className="primary full" disabled={transferGroupId === null || transferGroupId === studentGroup(selectedStudent.id)?.id} onClick={transferStudent}>{studentGroup(selectedStudent.id) ? "Перевести учня" : "Додати учня до групи"}</button>
            </div>
          </>}

          {canDeleteStudents && <div className="recordDangerZone">
            <span>Службова дія</span>
            <button className="subtleDangerAction" type="button" disabled={studentDeleteSaving} onClick={deleteSelectedStudent}>{studentDeleteSaving ? "Видаляємо…" : "Видалити учня"}</button>
          </div>}
          {apiEnabled ? <AuditHistory title="Історія учня" events={entityEvents} loading={historyLoading} labelForEvent={auditEventLabel} detailForEvent={auditEventDetail} /> : <div className="history">
            <h3>Історія учня</h3>
            <div><i></i><p><b>Пробне заняття</b><span>{selectedStudent.recommendedLevel ?? "Рівень не вказано"}</span></p></div>
            <div><i></i><p><b>Зараховано</b><span>{studentGroup(selectedStudent.id)?.name ?? "Групу не вказано"}</span></p></div>
          </div>}
        </aside>
      </div>}

      {showGroupForm && <div className="modalBackdrop">
        <div className="groupModal groupCreateModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowGroupForm(false)}>×</button>
          <p className="eyebrow">Нова група</p>
          <h2>Створити групу</h2>
          <p className="modalIntro">{selectedCandidates.length
            ? `Буде зараховано ${selectedCandidates.length} ${selectedCandidates.length === 1 ? "учня" : "учнів"}. Їх можна змінити пізніше.`
            : "Групу можна створити наперед без учнів. Розклад, викладача й учасників можна змінювати пізніше."}</p>
          <label>Назва групи<input autoFocus value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="Наприклад: FPV Start 8–10" /></label>
          <div className="formTwo">
            <label>Місткість<input type="number" min={1} max={100} value={groupCapacity} onChange={(e) => setGroupCapacity(Number(e.target.value))} /></label>
            {activeLocations.length === 0
              ? <div className="groupLocationOptional">
                  <b>Локація <small>(необов’язково)</small></b>
                  <small>Групу можна створити без локації та вказати її пізніше.</small>
                  <button className="search" type="button" onClick={createLocationFromGroup}>+ Створити локацію</button>
                </div>
              : activeLocations.length === 1
                ? <label>Локація <small>(необов’язково)</small><select value={groupLocationId} onChange={(e) => setGroupLocationId(e.target.value)}>
                    <option value="">Без локації</option>
                    <option value={activeLocations[0].id}>{activeLocations[0].name}</option>
                  </select></label>
                : <label>Локація <small>(необов’язково)</small><select value={groupLocationId} onChange={(e) => { setGroupLocationId(e.target.value); setGroupCreateError(""); }}>
                    <option value="">Без локації</option>
                    {activeLocations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
                  </select></label>}
          </div>
          {canManageStaff && <label>Викладач <small>(необов’язково)</small><select value={newGroupTeacherId} onChange={(e) => setNewGroupTeacherId(e.target.value)}>
            <option value="">Призначити пізніше</option>
            {activeTeachers.map((teacher) => <option value={teacher.id} key={teacher.id}>{teacher.fullName}</option>)}
          </select></label>}
          <div className="groupCreateScheduleHead"><div><b>Регулярний розклад</b><small>Це шаблон: конкретні заняття з’являтимуться в календарі автоматично.</small></div></div>
          <ScheduleSlotEditor value={groupSchedule} onChange={setGroupSchedule} />
          {selectedCandidates.length > 0 && <div className="selectedNames">{leads.filter((x) => selectedCandidates.includes(x.id)).map((x) => {
            const compatibility = candidateCompatibility(x, groupSchedule, groupLocationId || null);
            return <span className={"candidateCompatibility " + compatibility.state} key={x.id}>
              <b>{x.child} · {x.age}</b><small>{compatibility.icon} {compatibility.label}</small><small>{compatibility.detail}</small>
            </span>;
          })}</div>}
          {groupCreateError && <div className="groupCreateError">{groupCreateError}</div>}
          <button className="primary full" disabled={!groupName.trim() || selectedCandidates.length > groupCapacity || hasDuplicateSlots(groupSchedule)} onClick={createGroupFromCandidates}>
            {!groupName.trim() ? "Вкажіть назву групи" : selectedCandidates.length > groupCapacity ? "Збільште місткість групи" : hasDuplicateSlots(groupSchedule) ? "Приберіть однакові слоти" : selectedCandidates.length ? "Створити групу і зарахувати" : "Створити групу"}
          </button>
        </div>
      </div>}

      {selected && <div className="drawerBackdrop leadDrawerBackdrop" onClick={() => { setSelectedId(null); setLeadEditing(false); setLeadActionsOpen(false); setLeadStatusMenuOpen(false); }}>
        <aside className="drawer leadDrawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" aria-label="Закрити картку заявки" onClick={() => { setSelectedId(null); setLeadEditing(false); setLeadActionsOpen(false); setLeadStatusMenuOpen(false); }}>×</button>
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
          {selected.nextContactAt && (() => { const action = leadActionMeta(selected); const overdue = dateValue(selected.nextContactAt) < Date.now(); return <div className={"noteBox followUpBox actionReminder " + action.type + (overdue ? " overdue" : "")}><span className="actionReminderLabel"><i>{overdue ? "!" : action.icon}</i>{overdue ? "Прострочений контакт" : action.label}</span><p>{new Date(selected.nextContactAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</p></div>; })()}
          {["Відмовились","Не відповідає","Неактуально"].includes(selected.status) && <div className="noteBox closedLeadBox"><span>Заявку закрито</span><p><b>{selected.status}</b>{selected.closeReason ? " · " + closeReasonLabel(selected.closeReason) : ""}</p>{selected.closeNote && <p>{selected.closeNote}</p>}<button className="search reopenLead" onClick={reopenLead}>Повернути в роботу</button></div>}
          <div className={"noteBox leadCommentBox" + (!selected.comment ? " empty" : "")}><span>Коментар</span><p>{selected.comment || "Коментар ще не додано."}</p>{canManageLeads && !leadEditing && <button type="button" className="inlineEditLink" onClick={beginLeadEdit}>{selected.comment ? "Редагувати" : "+ Додати"}</button>}</div>
          {selected.trialAt && <div className="trialSummary"><span>Коли і де</span><b>{new Date(selected.trialAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</b><small>{selected.trialLocation ?? "Локацію не вказано"}</small></div>}
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
            {activeLocations.length === 1
              ? <label>Локація<div className="singleLocationField">{activeLocations[0].name}</div></label>
              : <label>Локація<select value={trialLocationId} onChange={(e) => { setTrialLocationId(e.target.value); setTrialLocation(locations.find((location) => location.id === e.target.value)?.name ?? ""); }}>
                  <option value="">Без локації</option>
                  {activeLocations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
                </select></label>}
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

          {leadProcedureTarget === "waiting" && <div id="lead-enrollment-workflow" className="workflowBox leadWorkflowBox leadDirectEnrollmentStep">
            <div className="workflowHead"><h3>Зарахувати учня</h3><button onClick={() => { setLeadProcedureTarget(null); setLeadEnrollmentGroupId(""); }}>×</button></div>
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
            <button className="primary full" disabled={!deferAt || !deferReason} onClick={saveDeferredLead}>Відкласти заявку</button>
          </div>}

          {leadIsDeferred(selected) && <div className="deferredLeadNotice">
            <span>Повернутись пізніше</span>
            <b>{selected.deferredUntil ? new Date(selected.deferredUntil).toLocaleString("uk-UA", { day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}</b>
            <small>{deferReasonLabel(selected.deferredReason)}{selected.deferredNote ? " · " + selected.deferredNote : ""}</small>
            <button className="search" type="button" onClick={resumeDeferredLead}>Повернути в роботу зараз</button>
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
            <button className="primary full" onClick={closeLead}>Закрити заявку</button>
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
      </div>}
    </div>
  );
}

function leadIsDeferred(lead: Lead): boolean {
  return Boolean(lead.deferredUntil && dateValue(lead.deferredUntil) > Date.now());
}

function deferReasonLabel(reason: string | null | undefined): string {
  const labels: Record<string, string> = {
    later: "Зараз не можуть, хочуть пізніше",
    age: "Ще замала дитина",
    schedule: "Зараз не підходить графік",
    finance: "Фінанси / тимчасово не готові",
    school: "Навчання / завантаженість",
    move: "Переїзд / тимчасово не в місті",
    other: "Інше",
  };
  return reason ? (labels[reason] ?? reason) : "Причину не вказано";
}

function leadKanbanColumn(lead: Lead): LeadKanbanColumnId {
  if (["Відмовились", "Не відповідає", "Неактуально"].includes(lead.status)) return "closed";
  if (leadIsDeferred(lead)) return "deferred";
  if (lead.trialResult === "no_show" && lead.status === "Зв'язались") return "no_show";
  if (lead.status === "Після пробного") return "after_trial";
  if (lead.status === "Пробне заплановано") return "trial";
  if (lead.status === "Очікує групу") return "waiting";
  if (lead.status === "Нова") return "new";
  return "contacted";
}

function leadUrgency(lead: Lead): "overdue" | "today" | "planned" | "none" {
  const now = new Date();
  if (lead.nextContactAt) {
    const action = new Date(lead.nextContactAt);
    if (action.getTime() < now.getTime()) return "overdue";
    if (action.toDateString() === now.toDateString()) return "today";
    return "planned";
  }
  if (lead.trialResult === "no_show" || lead.status === "Після пробного" || lead.status === "Нова") return "today";
  if (lead.status === "Пробне заплановано") return "planned";
  return "none";
}

function LeadKanban({
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

function LeadTable({ leads, onOpen }: { leads: Lead[]; onOpen: (id: EntityId) => void }) {
  return <div className="table leadTable">
    <div className="row tableHead"><span>Дитина</span><span>Вік</span><span>Батьки</span><span>Джерело</span><span>Статус</span><span>Наступна дія</span></div>
    {leads.length === 0 && <div className="emptyState">За цим фільтром заявок немає.</div>}
    {leads.map((lead) => <button className="row rowButton" key={lead.id} onClick={() => onOpen(lead.id)}>
      <b>{lead.child}</b><span>{lead.age}</span><span>{lead.parent}</span><span>{leadSourceLabel(lead.source)}</span><span className="pill">{leadDisplayStatus(lead)}</span>{(() => { const action = leadActionMeta(lead); const overdue = Boolean(lead.nextContactAt && dateValue(lead.nextContactAt) < Date.now()); return <span className={"nextAction actionTag action-" + action.type + (overdue ? " overdue" : "")}><i>{overdue ? "!" : action.icon}</i><span>{leadNextAction(lead)}</span></span>; })()}
    </button>)}
  </div>;
}

function applyTeaching(
  bundle: TeachingBundle,
  setLessons: Dispatch<SetStateAction<LessonItem[]>>,
  setGroups: Dispatch<SetStateAction<GroupItem[]>>,
) {
  setLessons(bundle.lessons.map((item) => ({
    id: item.id,
    groupId: item.group_id,
    startsAt: item.starts_at,
    duration: item.duration_minutes,
    topic: item.topic ?? "Заняття",
    notes: item.notes ?? undefined,
    status: item.status,
    attendancePresent: item.attendance_present,
    attendanceAbsent: item.attendance_absent,
    attendanceLate: item.attendance_late,
    attendanceExcused: item.attendance_excused,
    attendanceTotal: item.attendance_total,
  })));

  const byGroup = new Map<EntityId, TeachingBundle["schedules"]>();
  bundle.schedules.forEach((item) => {
    const list = byGroup.get(item.group_id) ?? [];
    list.push(item);
    byGroup.set(item.group_id, list);
  });

  setGroups((items) => items.map((group) => {
    const schedules = byGroup.get(group.id) ?? [];
    return {
      ...group,
      schedule: schedules.length ? scheduleLabel(schedules) : "Розклад не задано",
    };
  }));
}

function scheduleLabel(items: TeachingBundle["schedules"]) {
  return [...items]
    .sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time))
    .map((item) => `${SCHEDULE_DAY_NAMES[item.weekday] ?? "Невідомий день"} · ${item.start_time.slice(0, 5)}`)
    .join("; ");
}

function applyOperations(
  bundle: OperationsBundle,
  setLocations: Dispatch<SetStateAction<LocationDemo[]>>,
  setStaff: Dispatch<SetStateAction<StaffDemo[]>>,
  setPlans: Dispatch<SetStateAction<PlanDemo[]>>,
  setPayments: Dispatch<SetStateAction<PaymentDemo[]>>,
  setSubscriptions: Dispatch<SetStateAction<ApiStudentSubscription[]>>,
) {
  setLocations(bundle.locations.map((item) => ({
    id: item.id,
    name: item.name,
    address: item.address ?? "",
    isActive: item.is_active,
  })));

  setStaff(bundle.staff.map((item) => ({
    id: item.id,
    fullName: item.full_name,
    role: staffRoleLabel(item.role),
    canTeach: item.can_teach,
    email: item.email ?? "",
    phone: item.phone ?? "",
    locationIds: item.assignments.location_ids,
    groupIds: item.assignments.group_ids,
    isActive: item.is_active,
  })));

  setPlans(bundle.plans.map((item) => ({
    id: item.id,
    name: item.name,
    price: item.price_minor / 100,
    days: item.period_days,
    lessons: item.lessons_included,
    isActive: item.is_active,
    usageMode: item.usage_mode,
    absentRule: item.absent_rule,
    excusedRule: item.excused_rule,
    endRule: item.end_rule,
  })));

  const today = new Date().toISOString().slice(0, 10);
  setPayments(bundle.payments.map((item) => ({
    id: item.id,
    studentId: item.student_id,
    planId: item.plan_id ?? "",
    subscriptionId: item.subscription_id ?? undefined,
    amount: item.amount_minor / 100,
    adjustedAmount: item.adjusted_amount_minor / 100,
    paidAmount: item.paid_minor / 100,
    refundedAmount: item.refunded_minor / 100,
    balanceAmount: item.balance_minor / 100,
    creditAmount: item.credit_minor / 100,
    dueDate: item.due_date ?? "",
    status: item.status === "pending" && item.due_date && item.due_date < today ? "overdue" : item.status,
    method: paymentMethodLabel(item.method),
  })));
  setSubscriptions(bundle.subscriptions);
}

function staffRoleLabel(role: string): StaffRoleDemo {
  const labels: Record<string, StaffRoleDemo> = {
    owner: "Власник",
    admin: "Адміністратор",
    manager: "Менеджер",
    teacher: "Викладач",
    accountant: "Бухгалтер",
  };
  return labels[role] ?? "Викладач";
}

function staffRoleValue(role: StaffRoleDemo) {
  const values: Record<StaffRoleDemo, string> = {
    "Власник": "owner",
    "Адміністратор": "admin",
    "Менеджер": "manager",
    "Викладач": "teacher",
    "Бухгалтер": "accountant",
  };
  return values[role];
}

function dateValue(value?: string, fallback = 0) {
  if (!value) return fallback;
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : fallback;
}

function lessonWeekdayLabel(value: string) {
  const names = ["Нд", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : names[date.getDay()];
}

function leadActionPriority(lead: Lead) {
  const now = Date.now();
  if (lead.nextContactAt && dateValue(lead.nextContactAt) <= now) return 0;
  if (lead.trialResult === "no_show") return 1;
  if (lead.trialResult === "cancelled") return 2;
  if (lead.status === "Після пробного" && !lead.nextContactAt) return 3;
  if (lead.status === "Нова") return 4;
  if (lead.status === "Пробне заплановано") return 5;
  if (lead.nextContactAt) return 6;
  if (lead.status === "Зв'язались") return 7;
  if (lead.status === "Очікує групу") return 8;
  return 9;
}

function leadDisplayStatus(lead: Lead) {
  if (lead.trialResult === "no_show" && lead.status === "Зв'язались") return "Не прийшов";
  if (lead.trialResult === "cancelled" && lead.status === "Зв'язались") return "Скасували пробне";
  return lead.status;
}

function leadPrimaryActionLabel(lead: Lead) {
  if (["Відмовились", "Не відповідає", "Неактуально"].includes(lead.status)) return "Повернути в роботу";
  if (lead.status === "Зарахований") return "Відкрити картку учня";
  if (lead.status === "Нова") return "Позначити «Зв'язались»";
  if (lead.trialResult === "no_show" || lead.trialResult === "cancelled") return "Перезаписати на пробне";
  if (lead.status === "Пробне заплановано") return "Внести результат пробного";
  if (lead.status === "Після пробного") return "Рішення після пробного";
  if (lead.status === "Очікує групу") return "Зарахувати учня";
  return "Записати на пробне";
}

function leadNextAction(lead: Lead) {
  if (leadIsDeferred(lead) && lead.deferredUntil) {
    const when = new Date(lead.deferredUntil);
    return `Повернутись: ${when.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit", year: "2-digit" })}`;
  }
  if (lead.status === "Відмовились") return "Закрито: відмовились";
  if (lead.status === "Не відповідає") return "Закрито: не відповідає";
  if (lead.status === "Неактуально") return "Закрито: неактуально";
  if (lead.status === "Зарахований") return "Учень зарахований";
  if (lead.nextContactAt) {
    const when = new Date(lead.nextContactAt);
    const overdue = when.getTime() < Date.now();
    return `${overdue ? "Прострочено: " : "Зв'язатися: "}${when.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })} · ${when.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}`;
  }
  if (lead.trialResult === "no_show") return "Зателефонувати / перезаписати";
  if (lead.trialResult === "cancelled") return "Узгодити нову дату";
  if (lead.status === "Після пробного") return "Уточнити рішення";
  if (lead.status === "Нова") return "Перший контакт";
  if (lead.status === "Пробне заплановано" && lead.trialAt) {
    const when = new Date(lead.trialAt);
    return `Пробне ${when.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })} · ${when.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}`;
  }
  if (lead.status === "Очікує групу") return "Підібрати групу";
  return "Продовжити контакт";
}

function leadActionMeta(lead: Lead): { type: "call" | "trial" | "decision" | "group" | "closed" | "general"; icon: string; label: string } {
  if (leadIsDeferred(lead)) return { type: "general", icon: "◷", label: "Пізніше" };
  if (["Відмовились", "Не відповідає", "Неактуально"].includes(lead.status)) return { type: "closed", icon: "×", label: "Закрито" };
  if (lead.status === "Пробне заплановано") return { type: "trial", icon: "◷", label: "Пробне" };
  if (lead.trialResult === "no_show" || lead.trialResult === "cancelled" || lead.nextContactAt || lead.status === "Нова" || lead.status === "Зв'язались") return { type: "call", icon: "☎", label: "Контакт" };
  if (lead.status === "Після пробного") return { type: "decision", icon: "?", label: "Рішення" };
  if (lead.status === "Очікує групу") return { type: "group", icon: "→", label: "Група" };
  return { type: "general", icon: "•", label: "Дія" };
}

function closeReasonLabel(reason: string | null | undefined) {
  const labels: Record<string, string> = {
    price: "Ціна",
    schedule: "Не підходить графік",
    child_not_interested: "Дитині не цікаво",
    parents_changed_mind: "Батьки передумали",
    location: "Не підходить локація",
    other_club: "Обрали інший гурток",
    other: "Інше",
  };
  return reason ? (labels[reason] ?? reason) : "Не вказано";
}

function canonicalLeadSource(source: string | null | undefined) {
  const value = (source ?? "").trim().toLowerCase();
  const aliases: Record<string, string> = {
    iphone: "phone",
    телефон: "phone",
    дзвінок: "phone",
    site: "website",
    сайт: "website",
    insta: "instagram",
    referral: "recommendation",
    рекомендація: "recommendation",
    "walk_in": "walk-in",
    "walk in": "walk-in",
    "google maps": "maps",
  };
  return aliases[value] ?? value;
}

function leadMissingDetails(lead: Lead): string[] {
  const missing: string[] = [];
  if (!lead.lastName?.trim()) missing.push("прізвище дитини");
  const contactName = cleanSpaces(lead.parent ?? "");
  if (!contactName || contactName === "Контакт не вказано") {
    missing.push("ім’я відповідальної особи");
  } else if (contactName.split(" ").filter(Boolean).length < 2) {
    missing.push("прізвище відповідальної особи");
  }
  return missing;
}

function leadSourceLabel(source: string | null | undefined) {
  const labels: Record<string, string> = {
    phone: "Телефон",
    website: "Сайт",
    instagram: "Instagram",
    recommendation: "Рекомендація",
    "walk-in": "Зайшли особисто",
    walk_in: "Зайшли особисто",
    facebook: "Facebook",
    tiktok: "TikTok",
    google: "Google",
    maps: "Google Maps",
    other: "Інше",
  };
  if (!source) return "Не вказано";
  const canonical = canonicalLeadSource(source);
  return labels[canonical] ?? source;
}


function paymentMethodLabel(method: string | null | undefined): PaymentDemo["method"] {
  const labels: Record<string, PaymentDemo["method"]> = {
    cash: "Готівка",
    card: "Картка",
    bank: "Переказ",
    other: "Переказ",
  };
  return method ? labels[method] : undefined;
}

function applyWorkspace(
  bundle: WorkspaceBundle,
  setLeads: Dispatch<SetStateAction<Lead[]>>,
  setGroups: Dispatch<SetStateAction<GroupItem[]>>,
  setStudentStates: Dispatch<SetStateAction<Record<EntityId, "Активний" | "Пауза" | "Архів">>>,
) {
  const prospects: Lead[] = bundle.leads.map((item) => ({
    id: item.student_id,
    createdAt: item.created_at,
    firstName: item.first_name,
    lastName: item.last_name ?? undefined,
    child: [item.first_name, item.last_name].filter(Boolean).join(" "),
    age: item.age ?? 0,
    parent: item.contact_name ?? "Контакт не вказано",
    phone: item.contact_phone ?? "",
    childPhone: item.student_phone ?? undefined,
    source: item.source ?? "CRM",
    comment: item.comment ?? undefined,
    preferredLocationId: item.preferred_location_id ?? undefined,
    preferredLocationName: item.preferred_location_name ?? undefined,
    availability: item.availability.map((slot) => ({
      weekday: slot.weekday,
      start_time: slot.start_time.slice(0, 5),
      end_time: slot.end_time.slice(0, 5),
      preference: slot.preference ?? "preferred",
      note: slot.note,
    })),
    status: crmStatusLabel(item.crm_status),
    trialId: item.latest_trial_id ?? undefined,
    trialAt: item.latest_trial_at ?? undefined,
    trialLocationId: item.trial_location_id ?? undefined,
    trialLocation: item.trial_location_name ?? undefined,
    recommendedLevel: item.recommended_level ?? undefined,
    teacherNotes: item.teacher_notes ?? undefined,
    trialResult: item.latest_trial_status ?? undefined,
    nextContactAt: item.next_contact_at ?? undefined,
    deferredUntil: item.deferred_until ?? undefined,
    deferredReason: item.deferred_reason ?? undefined,
    deferredNote: item.deferred_note ?? undefined,
    closeReason: item.close_reason ?? undefined,
    closeNote: item.close_note ?? undefined,
  }));

  const students: Lead[] = bundle.students.map((item) => ({
    id: item.student_id,
    firstName: item.first_name,
    lastName: item.last_name ?? undefined,
    child: [item.first_name, item.last_name].filter(Boolean).join(" "),
    age: item.age ?? 0,
    parent: item.contact_name ?? "Контакт не вказано",
    phone: item.contact_phone ?? "",
    childPhone: item.student_phone ?? undefined,
    source: item.source ?? "CRM",
    status: "Зарахований",
  }));

  const states: Record<EntityId, "Активний" | "Пауза" | "Архів"> = {};
  bundle.students.forEach((item) => {
    states[item.student_id] = item.student_status === "paused" ? "Пауза" : item.student_status === "archived" ? "Архів" : "Активний";
  });

  const groups: GroupItem[] = bundle.groups.map((group) => ({
    id: group.group_id,
    name: group.name,
    ages: ageLabel(group.min_age, group.max_age),
    schedule: "Розклад не задано",
    location: group.location_name ?? "Локацію не вказано",
    capacity: group.capacity ?? Math.max(group.enrolled_count, 1),
    members: bundle.students.filter((student) => student.group_id === group.group_id).map((student) => student.student_id),
    teacherName: group.primary_teacher_name ?? undefined,
  }));

  setLeads([...prospects, ...students]);
  setGroups(groups);
  setStudentStates(states);
}

function crmStatusValue(status: LeadStatus) {
  const values: Record<LeadStatus, string> = {
    "Нова": "new",
    "Зв'язались": "contacted",
    "Пробне заплановано": "trial_scheduled",
    "Після пробного": "trial_completed",
    "Очікує групу": "waiting_for_group",
    "Зарахований": "enrolled",
    "Не відповідає": "no_response",
    "Відмовились": "declined",
    "Неактуально": "not_relevant",
  };
  return values[status];
}

function crmStatusLabel(status: WorkspaceBundle["leads"][number]["crm_status"]): LeadStatus {
  const labels: Record<WorkspaceBundle["leads"][number]["crm_status"], LeadStatus> = {
    new: "Нова",
    contacted: "Зв'язались",
    trial_scheduled: "Пробне заплановано",
    trial_completed: "Після пробного",
    waiting_for_group: "Очікує групу",
    enrolled: "Зарахований",
    no_response: "Не відповідає",
    declined: "Відмовились",
    not_relevant: "Неактуально",
  };
  return labels[status];
}

function ageLabel(min: number | null, max: number | null) {
  if (min == null && max == null) return "—";
  if (min != null && max != null) return min === max ? String(min) : `${min}–${max}`;
  return String(min ?? max);
}

function auditEventLabel(type: string) {
  const labels: Record<string, string> = {
    "lead.created": "Заявка створена",
    "lead.duplicate_intake": "Повторна заявка",
    "lead.details_updated": "Дані заявки змінено",
    "student.crm_status_changed": "Статус заявки змінено",
    "trial.scheduled": "Пробне заплановано",
    "trial.rescheduled": "Пробне перенесено",
    "trial.completed": "Пробне пройдено",
    "trial.no_show": "Не прийшов на пробне",
    "trial.cancelled": "Пробне скасовано",
    "lead.outcome_updated": "Рішення по заявці",
    "lead.deferred": "Повернутись пізніше",
    "lead.deferred_cleared": "Повернуто в роботу",
    "student.enrolled": "Зараховано до групи",
    "student.enrolled_without_group": "Зараховано без групи",
    "student.transferred": "Переведено в іншу групу",
    "student.status_changed": "Статус учня змінено",
    "payment.created": "Створено нарахування",
    "payment.paid": "Оплату отримано",
  };
  return labels[type] ?? type;
}

function auditEventDetail(event: ApiAuditEvent) {
  const payload = event.payload ?? {};
  if (typeof payload["group_name"] === "string") return payload["group_name"];
  if (typeof payload["to_group_name"] === "string") return payload["to_group_name"];
  if (typeof payload["crm_status"] === "string") {
    const labels: Record<string, string> = {
      contacted: "Зв'язались",
      trial_completed: "Після пробного",
      waiting_for_group: "Очікує групу",
      declined: "Відмовились",
      no_response: "Не відповідає",
      not_relevant: "Неактуально",
    };
    const status = labels[String(payload["crm_status"])] ?? String(payload["crm_status"]);
    const reason = typeof payload["close_reason"] === "string" ? ` · ${closeReasonLabel(String(payload["close_reason"]))}` : "";
    return status + reason;
  }
  if (typeof payload["student_status"] === "string") return String(payload["student_status"]);
  if (typeof payload["recommended_level"] === "string") return String(payload["recommended_level"]);
  if (typeof payload["amount_minor"] === "number") return formatMoney(Number(payload["amount_minor"]) / 100);
  return "CRM";
}

function overviewFunnelCount(report: OverviewReport | null, status: WorkspaceBundle["leads"][number]["crm_status"], fallback: number) {
  return report?.funnel.find((item) => item.status === status)?.count ?? fallback;
}

function visibleNavigation(role?: string) {
  if (!apiEnabled || !role) return allNav;
  const byRole: Record<string, string[]> = {
    owner: allNav,
    admin: allNav,
    manager: ["Дашборд", "Заявки", "Учні", "Групи", "Розклад", "Відвідування", "Локації", "Звіти"],
    teacher: ["Дашборд", "Учні", "Групи", "Розклад", "Відвідування"],
    accountant: ["Дашборд", "Оплати", "Звіти"],
  };
  return byRole[role] ?? ["Дашборд"];
}

function roleLabel(role?: string) {
  const labels: Record<string,string> = {
    owner: "Власник",
    admin: "Адміністратор",
    manager: "Менеджер",
    teacher: "Викладач",
    accountant: "Бухгалтер",
  };
  return role ? labels[role] ?? role : "Demo";
}

function addLocalDays(value: Date, amount: number) {
  const next = new Date(value);
  next.setHours(12, 0, 0, 0);
  next.setDate(next.getDate() + amount);
  return next;
}

function startOfLocalWeek(value: Date) {
  const next = new Date(value);
  next.setHours(12, 0, 0, 0);
  const mondayOffset = (next.getDay() + 6) % 7;
  next.setDate(next.getDate() - mondayOffset);
  return next;
}

function localDateInput(value: Date) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function defaultPaymentDueDate() {
  const now = new Date();
  return localDateInput(new Date(now.getFullYear(), now.getMonth() + 1, 0));
}

function toLocalDateTimeInput(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function formatMoney(value: number, locale = "uk-UA", currency = "UAH") {
  return new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

type CandidateMatch = {
  state: "match" | "partial" | "conflict" | "unknown";
  icon: string;
  label: string;
  detail: string;
};

function candidateCompatibility(
  lead: Lead,
  schedule: Array<{ weekday: number; start_time: string; duration_minutes: number }>,
  locationId: string | null,
): CandidateMatch {
  if (!schedule.length || !(lead.availability?.length)) {
    return { state: "unknown", icon: "?", label: "Побажаний час не вказаний", detail: "Уточнити графік у батьків" };
  }
  let full = 0, partial = 0, conflicts = 0, preferred = 0;
  const details: string[] = [];
  schedule.forEach((lesson) => {
    const lessonStart = timeToMinutes(lesson.start_time);
    const lessonEnd = lessonStart + lesson.duration_minutes;
    const sameDay = lead.availability!.filter((x) => x.weekday === lesson.weekday);
    const acceptable = sameDay.filter((x) => (x.preference ?? "preferred") !== "avoid");
    const avoided = sameDay.filter((x) => (x.preference ?? "preferred") === "avoid");
    const fits = acceptable.filter((x) => timeToMinutes(x.start_time) <= lessonStart && timeToMinutes(x.end_time) >= lessonEnd);
    const avoidOverlap = avoided.some((x) => lessonStart < timeToMinutes(x.end_time) && lessonEnd > timeToMinutes(x.start_time));
    if (avoidOverlap && !fits.length) {
      conflicts++;
      details.push(`${DAY_NAMES[lesson.weekday]} ${lesson.start_time} — потрапляє в небажаний час`);
      return;
    }
    if (fits.length) {
      full++;
      if (fits.some((x) => (x.preference ?? "preferred") === "preferred")) preferred++;
      details.push(`${DAY_NAMES[lesson.weekday]} ${lesson.start_time} — підходить`);
      if (avoidOverlap) {
        partial++;
        details.push(`${DAY_NAMES[lesson.weekday]} ${lesson.start_time} — також перетинає небажаний час`);
      }
      return;
    }
    const close = acceptable.find((x) => {
      const start = timeToMinutes(x.start_time), end = timeToMinutes(x.end_time);
      return (lessonStart < end && lessonEnd > start) || Math.max(start - lessonEnd, lessonStart - end, 0) <= 60;
    });
    if (close) {
      partial++;
      details.push(`${DAY_NAMES[lesson.weekday]}: сім’я бажає ${close.start_time.slice(0, 5)}–${close.end_time.slice(0, 5)}`);
    } else conflicts++;
  });
  const locationMismatch = Boolean(lead.preferredLocationId && locationId && lead.preferredLocationId !== locationId);
  const locationDetail = locationMismatch ? "Бажана локація відрізняється" : "";
  const explanation = [...details, locationDetail].filter(Boolean).join("; ");
  if (!full && !partial) return { state: "conflict", icon: "!", label: "Потрібне узгодження", detail: explanation || "Збігів немає" };
  if (partial || conflicts || locationMismatch || preferred === 0) {
    const possibleOnly = matchingOnlyPossible(full, preferred) ? "Час позначений лише як можливий" : "";
    return { state: "partial", icon: "⚠", label: "Частковий збіг", detail: [explanation, possibleOnly].filter(Boolean).join("; ") || "Потрібне уточнення" };
  }
  return { state: "match", icon: "✓", label: "Графік підходить", detail: explanation };
}

function matchingOnlyPossible(full: number, preferred: number) {
  return full > 0 && preferred === 0;
}

function MatchBadge({ match }: { match: CandidateMatch }) {
  return <span className={"candidateSource candidateCompatibility " + match.state}>{match.icon} {match.label}</span>;
}

function MatchExplanation({ match }: { match: CandidateMatch }) {
  return <small className={"matchExplanation " + match.state}>{match.detail}</small>;
}

function timeToMinutes(value: string) {
  const [hours, minutes] = value.slice(0, 5).split(":").map(Number);
  return hours * 60 + minutes;
}

function groupAvailabilitySlots(slots: AvailabilitySlot[]): AvailabilityWindowDraft[] {
  const grouped = new Map<string, AvailabilityWindowDraft>();
  slots.forEach((slot) => {
    const preference = slot.preference ?? "preferred";
    const note = slot.note ?? null;
    const key = [slot.start_time.slice(0, 5), slot.end_time.slice(0, 5), preference, note ?? ""].join("|");
    const existing = grouped.get(key);
    if (existing) {
      if (!existing.weekdays.includes(slot.weekday)) existing.weekdays.push(slot.weekday);
      return;
    }
    grouped.set(key, {
      id: `availability-${grouped.size + 1}-${slot.weekday}`,
      weekdays: [slot.weekday],
      start_time: slot.start_time.slice(0, 5),
      end_time: slot.end_time.slice(0, 5),
      preference,
      note,
    });
  });
  return [...grouped.values()].map((window) => ({ ...window, weekdays: [...window.weekdays].sort((a, b) => a - b) }));
}

function flattenAvailabilityWindows(windows: AvailabilityWindowDraft[]): AvailabilitySlot[] {
  return windows.flatMap((window) =>
    [...new Set(window.weekdays)].sort((a, b) => a - b).map((weekday) => ({
      weekday,
      start_time: window.start_time,
      end_time: window.end_time,
      preference: window.preference,
      note: window.note ?? null,
    }))
  );
}

function availabilityLabel(slots: AvailabilitySlot[]) {
  if (!slots.length) return "Не вказано";
  const dayNames = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];
  const groups = new Map<string, string[]>();
  slots.forEach((slot) => {
    const key = `${slot.start_time.slice(0, 5)}–${slot.end_time.slice(0, 5)}`;
    const days = groups.get(key) ?? [];
    days.push(dayNames[slot.weekday] ?? "?");
    groups.set(key, days);
  });
  return [...groups.entries()].map(([time, days]) => `${days.join("/")} · ${time}`).join("; ");
}

const SCHEDULE_DAY_NAMES = ["Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя"];
function scheduleDraftLabel(slots: DraftScheduleSlot[]) { return slots.map((slot) => `${SCHEDULE_DAY_NAMES[slot.weekday] ?? "Невідомий день"} · ${slot.start_time.slice(0, 5)}`).join("; "); }
function hasDuplicateSlots(slots: DraftScheduleSlot[]) { return new Set(slots.map((slot) => `${slot.weekday}:${slot.start_time}`)).size !== slots.length; }

function scheduleSlots(group: GroupItem) {
  if (!group.schedule || group.schedule === "Розклад не задано") return [];
  return group.schedule.split(";").flatMap((part) => {
    const [daysPart, timePart] = part.split("·").map((x) => x.trim());
    const time = timePart || "—";
    return (daysPart || "").split("/").map((day) => ({ day: day.trim(), time })).filter((item) => item.day);
  });
}

function ageRange(items: Lead[]) {
  const ages = items.map((x) => x.age);
  if (!ages.length) return "—";
  const min = Math.min(...ages);
  const max = Math.max(...ages);
  return min === max ? String(min) : min + "–" + max;
}

export default App;
