import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { acceptInvite, apiDelete, apiEnabled, apiPatch, apiPost, apiPut, bootstrapOwner, changeOrganization, clearSession, getBootstrapStatus, loadAttendance, loadAuditEvents, loadGroupDetail, loadGroupRoster, loadOperations, loadOverviewReport, loadPaymentReminders, loadSession, loadStudentAttendanceHistory, loadTeaching, loadWorkspace, login, recordPaymentReminder, refreshMe, resetPassword, runBillingRenewals, type ApiAuditEvent, type ApiGroupDetail, type ApiGroupRosterStudent, type ApiPaymentReminder, type ApiStudentAttendanceHistoryItem, type ApiStudentSubscription, type OperationsBundle, type OverviewReport, type Session, type TeachingBundle, type WorkspaceBundle } from "./api";

type LeadStatus = "Нова" | "Зв'язались" | "Пробне заплановано" | "Після пробного" | "Очікує групу" | "Зарахований" | "Не відповідає" | "Відмовились" | "Неактуально";

type EntityId = string;

type AvailabilitySlot = {
  weekday: number;
  start_time: string;
  end_time: string;
  preference: "preferred" | "possible" | "avoid";
  note?: string | null;
};

type DraftScheduleSlot = { weekday: number; start_time: string; duration_minutes: number };

type LeadKanbanColumnId = "new" | "contacted" | "trial" | "no_show" | "after_trial" | "waiting" | "closed";

const leadKanbanColumns: Array<{ id: LeadKanbanColumnId; title: string; hint: string }> = [
  { id: "new", title: "Нові", hint: "Перший контакт" },
  { id: "contacted", title: "Зв’язались", hint: "В роботі" },
  { id: "trial", title: "Пробне", hint: "Заплановано" },
  { id: "no_show", title: "Не прийшов", hint: "Потрібна дія" },
  { id: "after_trial", title: "Після пробного", hint: "Очікуємо рішення" },
  { id: "waiting", title: "Очікує групу", hint: "Готовий до набору" },
  { id: "closed", title: "Закриті", hint: "Відмова / неактуально" },
];

type Lead = {
  id: EntityId;
  createdAt?: string;
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
  lessons: number | null;
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

function weekOffsetForDate(value: string | Date) {
  const current = startOfLocalWeek(new Date()).getTime();
  const target = startOfLocalWeek(typeof value === "string" ? new Date(value) : value).getTime();
  return Math.round((target - current) / (7 * 24 * 60 * 60 * 1000));
}

function weekdayLong(value: string) {
  const text = new Date(value).toLocaleDateString("uk-UA", { weekday: "long" });
  return text ? text.charAt(0).toLocaleUpperCase("uk-UA") + text.slice(1) : "";
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
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState("");
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
  const [leads, setLeads] = useState(initialLeads);
  const [groups, setGroups] = useState<GroupItem[]>([
    { id: "1", name: "FPV Start 8–10", ages: "8–10", schedule: "Пн / Ср · 17:00", location: "Основна локація", capacity: 8, members: ["8", "9"] },
  ]);
  const [lessons, setLessons] = useState<LessonItem[]>([
    { id: "1", groupId: "1", startsAt: "2026-09-30T17:00", duration: 60, topic: "FPV: траса в симуляторі" },
    { id: "2", groupId: "1", startsAt: "2026-10-05T17:00", duration: 60, topic: "Whoop: базове керування" },
  ]);
  const [selectedLessonId, setSelectedLessonId] = useState<EntityId>(apiEnabled ? "" : "1");
  const [attendance, setAttendance] = useState<Record<EntityId, Record<EntityId, AttendanceValue>>>({
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
  const [plans, setPlans] = useState<PlanDemo[]>([
    { id: "1", name: "8 занять / 30 днів", price: 1800, lessons: 8 },
    { id: "2", name: "Індивідуальний", price: 0, lessons: null },
  ]);
  const [payments, setPayments] = useState<PaymentDemo[]>([
    { id: "1", studentId: "8", planId: "1", amount: 1800, adjustedAmount: 1800, paidAmount: 0, refundedAmount: 0, balanceAmount: 1800, dueDate: "2026-10-05", status: "pending" },
    { id: "2", studentId: "9", planId: "1", amount: 1800, adjustedAmount: 1800, paidAmount: 1800, refundedAmount: 0, balanceAmount: 0, dueDate: "2026-09-28", status: "paid", method: "Картка" },
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
  const [planName, setPlanName] = useState("8 занять / 30 днів");
  const [planPrice, setPlanPrice] = useState("");
  const [planLessons, setPlanLessons] = useState("8");
  const [planUsageMode, setPlanUsageMode] = useState<"attendance" | "scheduled" | "period">("attendance");
  const [planAbsentRule, setPlanAbsentRule] = useState<"consume" | "dont_consume" | "choice">("choice");
  const [planExcusedRule, setPlanExcusedRule] = useState<"consume" | "dont_consume" | "makeup">("makeup");
  const [planEndRule, setPlanEndRule] = useState<"lessons" | "date" | "whichever_first">("whichever_first");
  const [locations, setLocations] = useState<LocationDemo[]>([
    { id: "1", name: "Основна локація", address: "Івано-Франківськ", isActive: true },
  ]);
  const [staff, setStaff] = useState<StaffDemo[]>([
    { id: "1", fullName: "Іван Викладач", role: "Викладач", email: "ivan@aerokids.example", phone: "+380 67 111 22 33", locationIds: ["1"], groupIds: ["1"], isActive: true },
    { id: "2", fullName: "Адміністратор AeroKids", role: "Адміністратор", email: "admin@aerokids.example", phone: "+380 67 444 55 66", locationIds: ["1"], groupIds: [], isActive: true },
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
  const [paymentReminders, setPaymentReminders] = useState<ApiPaymentReminder[]>([]);
  const [reminderSavingId, setReminderSavingId] = useState<EntityId | null>(null);
  const [showStaffForm, setShowStaffForm] = useState(false);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<StaffRoleDemo>("Викладач");
  const [inviteLink, setInviteLink] = useState("");
  const [staffResetLink, setStaffResetLink] = useState("");
  const [showLocationForm, setShowLocationForm] = useState(false);
  const [staffName, setStaffName] = useState("");
  const [staffRole, setStaffRole] = useState<StaffRoleDemo>("Викладач");
  const [staffEmail, setStaffEmail] = useState("");
  const [staffPhone, setStaffPhone] = useState("");
  const [locationName, setLocationName] = useState("");
  const [locationAddress, setLocationAddress] = useState("");
  const [selectedId, setSelectedId] = useState<EntityId | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<EntityId | null>(null);
  const [studentStates, setStudentStates] = useState<Record<EntityId, "Активний" | "Пауза" | "Архів">>({});
  const [transferGroupId, setTransferGroupId] = useState<EntityId | null>(null);
  const [trialMode, setTrialMode] = useState<"schedule" | "complete" | null>(null);
  const [postTrialMode, setPostTrialMode] = useState<"thinking" | "close" | null>(null);
  const [followUpAt, setFollowUpAt] = useState("");
  const [closeKind, setCloseKind] = useState<"declined" | "no_response" | "not_relevant">("declined");
  const [closeReason, setCloseReason] = useState("schedule");
  const [closeNote, setCloseNote] = useState("");
  const [preferenceMode, setPreferenceMode] = useState(false);
  const [preferenceLocationId, setPreferenceLocationId] = useState<EntityId | "">("");
  const [availabilityWindows, setAvailabilityWindows] = useState<AvailabilitySlot[]>([]);
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
  const [newLessonGroupId, setNewLessonGroupId] = useState<EntityId>("1");
  const [newLessonAt, setNewLessonAt] = useState("2026-10-07T17:00");
  const [newLessonDuration, setNewLessonDuration] = useState(60);
  const [newLessonTopic, setNewLessonTopic] = useState("FPV / електроніка");
  const [scheduleGroupId, setScheduleGroupId] = useState<EntityId>("1");
  const [scheduleWeekday, setScheduleWeekday] = useState(0);
  const [scheduleTime, setScheduleTime] = useState("17:00");
  const [scheduleDuration, setScheduleDuration] = useState(60);
  const [scheduleWeekOffset, setScheduleWeekOffset] = useState(0);
  const [attendanceWeekOffset, setAttendanceWeekOffset] = useState(0);
  useEffect(() => {
    setStaffResetLink("");
  }, [selectedStaffId]);

  useEffect(() => {
    if (!lessonSaveNotice) return;
    const timer = window.setTimeout(() => setLessonSaveNotice(""), 2200);
    return () => window.clearTimeout(timer);
  }, [lessonSaveNotice]);

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
      if (["owner", "admin", "accountant"].includes(membership?.role ?? "")) {
        await runBillingRenewals(currentSession).catch(() => undefined);
      }
      const [bundle, operations, teaching, report, reminders] = await Promise.all([
        loadWorkspace(currentSession),
        loadOperations(currentSession),
        loadTeaching(currentSession),
        loadOverviewReport(currentSession),
        loadPaymentReminders(currentSession).catch(() => []),
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
      if (!trialLocationId && operations.locations[0]) setTrialLocationId(operations.locations[0].id);
      if (!groupLocationId && operations.locations[0]) setGroupLocationId(operations.locations[0].id);
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

    const selected = leads.find((lead) => lead.id === selectedId) ?? null;
  const selectedStudent = leads.find((lead) => lead.id === selectedStudentId) ?? null;
  const activeStudents = leads.filter((lead) => lead.status === "Зарахований");

  useEffect(() => {
    const entityId = selected?.id ?? selectedStudent?.id;
    if (!entityId || !apiEnabled || !session) {
      setEntityEvents([]);
      return;
    }
    const role = session.user.memberships.find((item) => item.organization_id === session.organizationId)?.role;
    if (!["owner", "admin", "manager"].includes(role ?? "")) {
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
    if (["Відмовились", "Не відповідає", "Неактуально", "Зарахований"].includes(lead.status)) return false;
    if (lead.nextContactAt && dateValue(lead.nextContactAt) <= Date.now()) return true;
    if (lead.trialResult === "no_show" || lead.trialResult === "cancelled") return true;
    if (lead.status === "Нова" || lead.status === "Після пробного") return true;
    return false;
  }).length, [leads]);

  const leadActiveCount = useMemo(() => leads.filter((lead) =>
    !["Відмовились", "Не відповідає", "Неактуально", "Зарахований"].includes(lead.status)
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

  const createManualLead = async () => {
    const childNameError = personNameError(leadChildName, "Ім’я дитини");
    const childLastNameError = personNameError(leadChildLastName, "Прізвище дитини");
    const childPhoneError = uaPhoneError(leadChildPhone, false);
    const contactNameError = fullNameError(leadContactName, "Відповідальна особа");
    const phoneError = uaPhoneError(leadPhone);
    if (childNameError || childLastNameError || childPhoneError || contactNameError || phoneError) {
      setWorkspaceError(childNameError || childLastNameError || childPhoneError || contactNameError || phoneError);
      return;
    }
    const normalizedPhone = normalizeUaPhone(leadPhone)!;
    const normalizedChildPhone = leadChildPhone.trim() ? normalizeUaPhone(leadChildPhone) : null;
    if (apiEnabled && session) {
      try {
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
      } catch {
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
    setTrialMode(null);
    setPostTrialMode(null);
    setPreferenceMode(false);
    setLeadProcedureTarget(null);
    setLeadEnrollmentGroupId("");
    const lead = leads.find((item) => item.id === id);
    if (lead?.trialAt) setTrialAt(toLocalDateTimeInput(lead.trialAt));
    if (lead?.trialLocation) setTrialLocation(lead.trialLocation);
    if (lead?.trialLocationId) setTrialLocationId(lead.trialLocationId);
    if (lead?.recommendedLevel) setRecommendedLevel(lead.recommendedLevel);
    setTeacherNotes(lead?.teacherNotes ?? "");
    setFollowUpAt(lead?.nextContactAt ? toLocalDateTimeInput(lead.nextContactAt) : "");
    setCloseKind(lead?.status === "Не відповідає" ? "no_response" : lead?.status === "Неактуально" ? "not_relevant" : "declined");
    setCloseReason(lead?.closeReason ?? "schedule");
    setCloseNote(lead?.closeNote ?? "");
    setPreferenceLocationId(lead?.preferredLocationId ?? "");
    setAvailabilityWindows(lead?.availability ?? []);
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
        availability: availabilityWindows,
      }, session);
      await syncWorkspace(session);
      setPreferenceMode(false);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти бажаний графік");
    } finally {
      setPreferenceSaving(false);
    }
  };

  const createGroupFromCandidates = async () => {
    if (!selectedCandidates.length || !groupName.trim()) return;
    if (apiEnabled && session) {
      try {
        await apiPost("/groups/form", {
          name: groupName.trim(),
          capacity: groupCapacity,
          location_id: groupLocationId || null,
          min_age: null,
          max_age: null,
          student_ids: selectedCandidates,
          schedule_slots: groupSchedule,
        }, session);
        await syncWorkspace(session);
        setSelectedCandidates([]);
        setShowGroupForm(false);
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося створити групу.");
        return;
      }
    }
    const nextId = crypto.randomUUID();
    setGroups((items) => [...items, {
      id: nextId,
      name: groupName.trim(),
      ages: "—",
      schedule: scheduleDraftLabel(groupSchedule),
      location: locations.find((location) => location.id === groupLocationId)?.name ?? "Локацію не вказано",
      capacity: groupCapacity,
      members: selectedCandidates,
    }]);
    setLeads((items) => items.map((item) => selectedCandidates.includes(item.id) ? { ...item, status: "Зарахований" } : item));
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

  const nearestLesson = [...lessons].sort((a, b) => {
    const now = Date.now();
    return Math.abs(dateValue(a.startsAt) - now) - Math.abs(dateValue(b.startsAt) - now);
  })[0];
  const selectedLesson = apiEnabled && !workspaceLoaded
    ? undefined
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

  const attendanceWeekStart = startOfLocalWeek(addLocalDays(new Date(), attendanceWeekOffset * 7));
  const attendanceWeekEnd = addLocalDays(attendanceWeekStart, 6);
  const journalLessons = lessons
    .filter((lesson) => {
      const value = localDateInput(new Date(lesson.startsAt));
      return value >= localDateInput(attendanceWeekStart) && value <= localDateInput(attendanceWeekEnd);
    })
    .sort((a, b) => dateValue(a.startsAt) - dateValue(b.startsAt));

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

    const dayNames = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];
    setGroups((items) => items.map((group) => group.id === scheduleGroupId ? {
      ...group,
      schedule: group.schedule === "Розклад не задано"
        ? `${dayNames[scheduleWeekday]} · ${scheduleTime}`
        : `${group.schedule}; ${dayNames[scheduleWeekday]} · ${scheduleTime}`,
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
      const currentlyAssigned = activeTeachers.filter((teacher) => teacher.groupIds.includes(selectedGroupId));
      for (const teacher of currentlyAssigned) {
        if (teacher.id !== selectedGroupTeacherId) {
          await apiDelete(`/staff/${teacher.id}/groups/${selectedGroupId}`, session);
        }
      }
      if (selectedGroupTeacherId) {
        await apiPost(`/staff/${selectedGroupTeacherId}/groups`, {
          group_id: selectedGroupId,
          is_primary: true,
        }, session);
      }
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
    const nextPlanId = plans.some((plan) => plan.id === paymentPlanId && plan.price > 0)
      ? paymentPlanId
      : (plans.find((plan) => plan.price > 0)?.id ?? "");

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
    if (target) setAttendanceWeekOffset(weekOffsetForDate(target.startsAt));
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
    if (!plan || plan.price <= 0) {
      setWorkspaceError("Для нарахування оберіть абонемент із заданою ціною.");
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

  const createPlan = async () => {
    const parsedPrice = planPrice === "" ? Number.NaN : Number(planPrice);
    const parsedLessons = planLessons === "" ? null : Number(planLessons);
    if (!planName.trim() || !Number.isFinite(parsedPrice) || parsedPrice < 0) {
      setWorkspaceError("Вкажіть назву та коректну ціну тарифу.");
      return;
    }
    if (parsedLessons !== null && (!Number.isInteger(parsedLessons) || parsedLessons < 0)) {
      setWorkspaceError("Кількість занять має бути цілим числом.");
      return;
    }
    if (apiEnabled && session) {
      try {
        setWorkspaceError("");
        await apiPost("/subscription-plans", {
          name: planName.trim(),
          price_minor: Math.round(parsedPrice * 100),
          period_days: 30,
          lessons_included: parsedLessons && parsedLessons > 0 ? parsedLessons : null,
        }, session);
        await syncWorkspace(session);
        setPlanPrice("");
        setShowPlanForm(false);
        return;
      } catch (error) {
        setWorkspaceError(error instanceof Error ? error.message : "Не вдалося створити тариф.");
        return;
      }
    }
    setPlans((items) => [...items, {
      id: crypto.randomUUID(),
      name: planName.trim(),
      price: parsedPrice,
      lessons: parsedLessons && parsedLessons > 0 ? parsedLessons : null,
    }]);
    setPlanPrice("");
    setShowPlanForm(false);
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
  const activeTeachers = staff.filter((member) => member.role === "Викладач" && member.isActive);
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
          email: staffEmail.trim().toLowerCase() || null,
          phone: normalizedStaffPhone,
          location_ids: locations[0] ? [locations[0].id] : [],
        }, session);
        await syncWorkspace(session);
        setStaffName("");
        setStaffEmail("");
        setStaffPhone("");
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
      email: staffEmail.trim().toLowerCase(),
      phone: normalizedStaffPhone ? formatUaPhone(normalizedStaffPhone) : "",
      locationIds: locations[0] ? [locations[0].id] : [],
      groupIds: [],
      isActive: true,
    }]);
    setStaffName("");
    setStaffEmail("");
    setStaffPhone("");
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
      }, session);
      const url = new URL(window.location.href);
      url.searchParams.set("invite", result.invite_token);
      setInviteLink(url.toString());
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося створити запрошення.");
      return;
    }
  };

  const createLocationDemo = async () => {
    if (!locationName.trim()) return;
    if (apiEnabled && session) {
      try {
        await apiPost("/locations", {
          name: locationName.trim(),
          address: locationAddress.trim() || null,
        }, session);
        await syncWorkspace(session);
        setLocationName("");
        setLocationAddress("");
        setShowLocationForm(false);
        return;
      } catch {
        return;
      }
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

  if (apiEnabled && !session) {
    return <LoginView onAuthenticated={setSession} />;
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
  const canManageRecurringSchedule = !apiEnabled || ["owner", "admin", "manager"].includes(currentMembership?.role ?? "");
  const canManageLeads = !apiEnabled || ["owner", "admin", "manager"].includes(currentMembership?.role ?? "");
  const canManageStudents = !apiEnabled || ["owner", "admin", "manager"].includes(currentMembership?.role ?? "");
  const canManageLocations = !apiEnabled || ["owner", "admin"].includes(currentMembership?.role ?? "");
  const canManageStaff = !apiEnabled || ["owner", "admin"].includes(currentMembership?.role ?? "");
  const todayKey = localDateInput(new Date());
  const scheduleWeekStart = startOfLocalWeek(addLocalDays(new Date(), scheduleWeekOffset * 7));
  const scheduleWeekDays = Array.from({ length: 7 }, (_, index) => addLocalDays(scheduleWeekStart, index));
  const scheduleWeekEnd = addLocalDays(scheduleWeekStart, 6);
  const lessonsThisWeek = lessons
    .filter((lesson) => {
      if (lesson.status === "cancelled") return false;
      const lessonDate = localDateInput(new Date(lesson.startsAt));
      return lessonDate >= localDateInput(scheduleWeekStart) && lessonDate <= localDateInput(scheduleWeekEnd);
    })
    .sort((a, b) => dateValue(a.startsAt) - dateValue(b.startsAt));
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
      <aside>
        <div className="brand"><img className="brandLogo" src="/aerokids-logo-master-v1.png" alt="AeroKids" /><div><b>AeroKids CRM</b><small>{currentMembership?.organization_name ?? "Керування школою"}</small></div></div>
        <nav>{navigation.map((item) => <button onClick={() => {
          if (item === "Налаштування" && currentMembership) {
            setOrganizationName(currentMembership.organization_name);
            setOrganizationTimezone(currentMembership.organization_timezone);
            setOrganizationCurrency(currentMembership.organization_currency);
            setOrganizationLocale(currentMembership.organization_locale);
          }
          setActive(item);
        }} className={active === item ? "active" : ""} key={item}>{item}</button>)}</nav>
        <div className="asideFooter">
          <button
            className="themeToggle asideThemeToggle"
            type="button"
            role="switch"
            aria-checked={theme === "light"}
            aria-label={theme === "dark" ? "Увімкнути світлу тему" : "Увімкнути темну тему"}
            onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
          >
            <span className="themeToggleTrack" aria-hidden="true"><i>{theme === "dark" ? "☾" : "☀"}</i></span>
            <span>{theme === "dark" ? "Темна тема" : "Світла тема"}</span>
          </button>
          <small>MVP 1 · crm-v1</small>
        </div>
      </aside>

      <main>
        <header>
          <div><p className="eyebrow">{headerContext}</p><h1>{active}</h1></div>
          <div className="headerActions">
            {session && <div className="orgSwitcher">
              <select value={session.organizationId} onChange={(e) => { setSession(changeOrganization(session, e.target.value)); setActive("Дашборд"); }}>
                {session.user.memberships.map((membership) => <option value={membership.organization_id} key={membership.organization_id}>{membership.organization_name}</option>)}
              </select>
              <span>{roleLabel(currentMembership?.role)}</span>
            </div>}
            <button className="search" onClick={() => { setSearchQuery(""); setShowSearch(true); }}>⌕ Пошук</button>
            {canManageLeads && <button className="primary" onClick={() => setShowLeadForm(true)}>+ Нова заявка</button>}
            {session && <button className="search" onClick={() => { clearSession(); setSession(null); }}>Вийти</button>}
          </div>
        </header>

        {apiEnabled && workspaceLoading && <div className="syncBanner">Завантажуємо дані організації…</div>}
        {apiEnabled && workspaceError && <div className="syncBanner error">{workspaceError}</div>}
        {apiEnabled && workspaceLoaded && !workspaceLoading && !workspaceError && <div className="syncStatus">Дані завантажено з CRM API</div>}

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
                  <span className="todayActionType lead">Заявка</span>
                  <span className="todayActionText"><b>{lead.child}</b><small>{kind} · {detail}</small></span>
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
            <div><p className="eyebrow">Воронка</p><h2>Заявки та пробні</h2></div>
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
            <div className="kanbanSummaryStat"><span>В роботі</span><strong>{leadActiveCount}</strong></div>
            <div className="kanbanSummaryStat attention"><span>Потрібна дія</span><strong>{leadActionCount}</strong></div>
            <span className="kanbanHint">Етапи вже видно в колонках. Зверху лишили тільки джерело та порядок карток усередині етапів.</span>
          </div>
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

        {active === "Розклад" && <section className="scheduleLayout">
          <article className="panel schedulePanel">
            <div className="scheduleToolbar">
              <div>
                <p className="eyebrow">Тижневий розклад</p>
                <h2>{scheduleWeekStart.toLocaleDateString("uk-UA", { day: "numeric", month: "short" })} — {scheduleWeekEnd.toLocaleDateString("uk-UA", { day: "numeric", month: "short", year: "numeric" })}</h2>
              </div>
              <div className="scheduleNav">
                <button className="search" onClick={() => setScheduleWeekOffset((value) => value - 1)}>←</button>
                <button className="search" onClick={() => setScheduleWeekOffset(0)} disabled={scheduleWeekOffset === 0}>Сьогодні</button>
                <button className="search" onClick={() => setScheduleWeekOffset((value) => value + 1)}>→</button>
              </div>
            </div>
            <p className="scheduleHint">У календарі показані лише конкретні заняття. Натисніть на заняття, щоб відкрити його журнал, відмітити присутність і записати тему.</p>
            <div className="weekGrid weekGridConcrete">
              {scheduleWeekDays.map((date) => {
                const dayKey = localDateInput(date);
                const dayLessons = lessonsThisWeek.filter((lesson) => localDateInput(new Date(lesson.startsAt)) === dayKey);
                const isToday = dayKey === todayKey;
                return <div className={"dayColumn scheduleDay " + (isToday ? "today" : "")} key={dayKey}>
                  <div className="scheduleDayHead">
                    <b>{date.toLocaleDateString("uk-UA", { weekday: "short" })}</b>
                    <span>{date.getDate()}</span>
                  </div>
                  <div className="scheduleDayLessons">
                    {dayLessons.map((lesson) => {
                      const group = groups.find((item) => item.id === lesson.groupId);
                      const marked = Object.keys(attendance[lesson.id] ?? {}).length;
                      const total = group?.members.length ?? 0;
                      return <button className="scheduleCard concreteLessonCard" key={lesson.id} onClick={() => goToLesson(lesson.id)}>
                        <div className="scheduleCardTop">
                          <time>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time>
                          {marked > 0 && <span>{marked}/{total}</span>}
                        </div>
                        <strong>{group?.name ?? "Група"}</strong>
                        <small>{lesson.topic || "Тема ще не вказана"}</small>
                        <em>Відкрити заняття →</em>
                      </button>;
                    })}
                    {dayLessons.length === 0 && <div className="scheduleDayEmpty">Немає занять</div>}
                  </div>
                </div>;
              })}
            </div>
          </article>
          <aside className="scheduleSide">
            <article className="panel lessonCreate">
              <p className="eyebrow">Нове заняття</p><h2>Додати заняття</h2>
              <label>Група<select value={newLessonGroupId} onChange={(e) => setNewLessonGroupId(e.target.value)}>{groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label>
              <DateTimeEditor label="Дата і час" value={newLessonAt} onChange={setNewLessonAt} />
              <DurationSelect value={newLessonDuration} onChange={setNewLessonDuration} />
              <label>Тема<input value={newLessonTopic} onChange={(e) => setNewLessonTopic(e.target.value)} placeholder="Можна заповнити пізніше в журналі" /></label>
              <button className="primary full" onClick={createLesson}>Створити заняття</button>
            </article>
            {canManageRecurringSchedule && <article className="panel lessonCreate recurringSettings">
              <p className="eyebrow">Шаблон групи</p><h2>Регулярний час</h2>
              <p className="scheduleSideHint">Регулярний час не є заняттям і не відкриває журнал. Він потрібен лише як шаблон для планування.</p>
              <label>Група<select value={scheduleGroupId} onChange={(e) => setScheduleGroupId(e.target.value)}>{groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label>
              <div className="formTwo">
                <label>День<select value={scheduleWeekday} onChange={(e) => setScheduleWeekday(Number(e.target.value))}>{["Пн","Вт","Ср","Чт","Пт","Сб","Нд"].map((day,index) => <option value={index} key={day}>{day}</option>)}</select></label>
                <TimeSelect label="Час" value={scheduleTime} onChange={setScheduleTime} />
              </div>
              <DurationSelect value={scheduleDuration} onChange={setScheduleDuration} />
              <button className="search full" onClick={createGroupSchedule}>Зберегти регулярний час</button>
            </article>}
          </aside>
        </section>}

        {active === "Відвідування" && <section className="attendanceLayout">
          <article className="panel lessonListPanel">
            <div className="attendanceWeekHead"><div><p className="eyebrow">Журнал</p><h2>{attendanceWeekStart.toLocaleDateString("uk-UA", { day: "numeric", month: "short" })} — {attendanceWeekEnd.toLocaleDateString("uk-UA", { day: "numeric", month: "short" })}</h2></div><span className="counter">{journalLessons.length}</span></div>
            <div className="attendanceWeekNav"><button className="search" onClick={() => setAttendanceWeekOffset((value) => value - 1)}>←</button><button className="search" disabled={attendanceWeekOffset === 0} onClick={() => setAttendanceWeekOffset(0)}>Сьогодні</button><button className="search" onClick={() => setAttendanceWeekOffset((value) => value + 1)}>→</button></div>
            <div className="lessonList">
              {journalLessons.map((lesson) => {
                const group = groups.find((g) => g.id === lesson.groupId);
                const isPast = dateValue(lesson.startsAt) < Date.now();
                const completed = lesson.status === "completed";
                const rowState = completed ? "completed" : isPast ? "missed" : "planned";
                const summary = completed ? `${lesson.attendancePresent ?? 0} є · ${lesson.attendanceLate ?? 0} зап. · ${lesson.attendanceAbsent ?? 0} нема · ${lesson.attendanceExcused ?? 0} поважн.` : isPast ? "Журнал не завершено" : "Заплановано";
                return <button className={"lessonRow " + rowState + " " + (lesson.id === selectedLessonId ? "active" : "")} key={lesson.id} onClick={() => setSelectedLessonId(lesson.id)}>
                  <time><b>{weekdayLong(lesson.startsAt)}</b>{new Date(lesson.startsAt).toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })}<small>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</small></time>
                  <span><b>{group?.name ?? "Група"}</b><small>{summary}</small></span>
                  <i>{completed ? "✓" : isPast ? "!" : "•"}</i>
                </button>;
              })}
              {journalLessons.length === 0 && <div className="emptyState compactEmpty">На цей тиждень занять немає.</div>}
            </div>
          </article>
          <article className="panel attendancePanel">
            {lessonSaveNotice && <div className="lessonSaveNotice">✓ Збережено</div>}
            {focusedAttendanceStudentId ? <div className="studentAttendanceOverview">
              <div className="studentAttendanceHero">
                <button className="lessonBackButton" onClick={() => { setFocusedAttendanceStudentId(null); setFocusedAttendanceGroupId(null); }}>← До журналу занять</button>
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
                <button className="lessonBackButton" onClick={() => setActive("Розклад")}>← До розкладу</button>
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
                        <button className={value === "late" ? "active late" : ""} onClick={() => markAttendance(student.id, "late")}>Запізнився</button>
                      </div>
                      {(value === "absent" || value === "excused") && <input className="attendanceReasonInput" value={attendanceNotes[selectedLesson.id]?.[student.id] ?? ""} onChange={(e) => setAttendanceNote(student.id, e.target.value)} maxLength={300} placeholder={value === "excused" ? "Причина / коментар (за потреби)" : "Причина відсутності (за потреби)"} />}
                    </div>;
                  })}
                  {lessonStudents.length === 0 && <div className="emptyState">У цій групі поки немає активних учнів.</div>}
                </div>
                <div className="attendanceFooter">
                  <span>{attendanceLoading ? "Завантажуємо…" : <>Позначено: <b>{Object.keys(attendance[selectedLesson.id] ?? {}).length}/{lessonStudents.length}</b>{lessonStudents.length > Object.keys(attendance[selectedLesson.id] ?? {}).length && <small> · ще {lessonStudents.length - Object.keys(attendance[selectedLesson.id] ?? {}).length}</small>}</>}</span>
                  <div className="attendanceFooterActions">
                    {selectedLesson.status === "completed" && <button className="search" onClick={() => setLessonEditing(false)}>Скасувати</button>}
                    <button className="primary" disabled={attendanceSaving || attendanceLoading || Object.keys(attendance[selectedLesson.id] ?? {}).length !== lessonStudents.length} onClick={saveAttendance}>{attendanceSaving ? "Зберігаємо…" : selectedLesson.status === "completed" ? "Зберегти зміни" : "Зберегти відвідування"}</button>
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
                    <span className="paymentPlanCell"><b>{plan?.name ?? "—"}</b>{subscription && <small>{subscription.status === "paused" ? "Пауза" : subscription.auto_renew ? "Автопродовження увімкнено" : "Без автопродовження"}</small>}</span>
                    <span className="paymentAmountCell"><b>{money(payment.adjustedAmount)}</b><small>{payment.balanceAmount > 0 ? <>Залишок: {money(payment.balanceAmount)}</> : <>Внесено: {money(Math.max(0, payment.paidAmount - payment.refundedAmount))}</>}{payment.refundedAmount > 0 ? " · повернено " + money(payment.refundedAmount) : ""}</small></span>
                    <span>{payment.dueDate ? new Date(payment.dueDate + "T00:00:00").toLocaleDateString("uk-UA") : "—"}</span>
                    <span className={"paymentStatus " + payment.status}>{statusLabel}</span>
                    <span className="paymentActions">
                      {payment.balanceAmount > 0 && payment.status !== "cancelled" && <button className="link payAction" onClick={() => markPaymentPaid(payment.id)}>Сплатити повністю</button>}
                      {payment.balanceAmount > 0 && payment.status !== "cancelled" && <button className="link" onClick={() => openPaymentAction(payment, "partial")}>Часткова</button>}
                      {payment.paidAmount - payment.refundedAmount > 0 && payment.status !== "cancelled" && <button className="link" onClick={() => openPaymentAction(payment, "refund")}>Повернення</button>}
                      {payment.status !== "cancelled" && <button className="link" onClick={() => openPaymentAction(payment, "adjustment")}>Коригувати</button>}
                      {subscription && subscription.status !== "cancelled" && <button className="link" onClick={() => toggleAutoRenew(subscription.id, !subscription.auto_renew)}>{subscription.auto_renew ? "Вимкнути авто" : "Увімкнути авто"}</button>}
                      {subscription?.status === "paused" ? <button className="link" onClick={() => resumeSubscriptionNow(subscription.id)}>Відновити</button> : subscription && subscription.status === "active" ? <button className="link" onClick={() => openPauseSubscription(subscription.id)}>Пауза</button> : null}
                    </span>
                  </div>;
                })}
              </div>
            </article>
          </div>
          <aside className="paymentsSide">
            <article className="panel">
              <div className="panelHead"><div><p className="eyebrow">Тарифи</p><h2>Абонементи</h2></div><div className="miniActions"><span className="counter">{plans.length}</span><button className="link" onClick={() => setShowPlanForm(true)}>+ Тариф</button></div></div>
              <div className="planCards">{plans.map((plan) => <div className="planCard" key={plan.id}><div><b>{plan.name}</b><span>{plan.lessons ? plan.lessons + " занять" : "Гнучкі умови"}</span></div><strong>{plan.price ? money(plan.price) : "Індивідуально"}</strong></div>)}</div>
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
            {canManageLocations && <button className="primary" onClick={() => setShowLocationForm(true)}>+ Додати локацію</button>}
          </div>
          <div className="locationCards">
            {locations.map((location) => {
              const locationStaff = staff.filter((member) => member.locationIds.includes(location.id) && member.isActive);
              const locationGroups = groups.filter((group) => group.location === location.name);
              return <article className="panel locationCard" key={location.id}>
                <div className="locationTop"><span className="locationIcon">⌂</span><span className={"staffStatus " + (location.isActive ? "active" : "inactive")}>{location.isActive ? "Активна" : "Неактивна"}</span></div>
                <h2>{location.name}</h2>
                <p>{location.address || "Адресу ще не вказано"}</p>
                <div className="locationMetrics"><span><b>{locationStaff.length}</b> працівників</span><span><b>{locationGroups.length}</b> груп</span></div>
                <div className="locationPeople">{locationStaff.slice(0,4).map((member) => <i title={member.fullName} key={member.id}>{member.fullName[0]}</i>)}</div>
              </article>;
            })}
          </div>
        </section>}

                {active === "Налаштування" && <section className="settingsLayout">
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
              <div className="groupsHeadActions"><span className="counter">{groups.length}</span>{waiting.length > 0 && <button className="search" onClick={() => document.getElementById("waiting-groups")?.scrollIntoView({ behavior: "smooth" })}>Очікують: {waiting.length}</button>}</div>
            </div>
            {groups.length === 0 ? <div className="groupsEmptyPrimary">
              <strong>Ще немає створених груп</strong>
              <span>Виберіть дітей зі списку очікування нижче та сформуйте першу групу.</span>
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
                <button className="primary" disabled={!selectedCandidates.length} onClick={() => setShowGroupForm(true)}>Створити нову групу</button>
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

      {showSearch && <div className="modalBackdrop">
        <div className="groupModal searchModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowSearch(false)}>×</button>
          <p className="eyebrow">Глобальний пошук</p><h2>Знайти в CRM</h2>
          <input className="globalSearchInput" autoFocus value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Ім’я, прізвище, телефон, відповідальний, група…" />
          {!searchTerm && <div className="searchHint">Введіть ім’я, частину телефону, відповідального або назву групи.</div>}
          {searchTerm && searchLeads.length + searchGroups.length + searchStaff.length + searchPayments.length === 0 && <div className="searchHint">Нічого не знайдено.</div>}
          {searchLeads.length > 0 && <div className="searchResults"><h3>Діти та заявки</h3>{searchLeads.map((item) => <button key={item.id} onClick={() => { if (item.status === "Зарахований") { setActive("Учні"); setSelectedStudentId(item.id); } else { setActive("Заявки"); setSelectedId(item.id); } setShowSearch(false); }}><span><b>{item.child}</b><small>{item.age} років · {item.parent}{item.phone ? " · " + formatUaPhone(item.phone) : ""}{item.childPhone ? " · дитина " + formatUaPhone(item.childPhone) : ""}</small></span><i>{item.status}</i></button>)}</div>}
          {searchGroups.length > 0 && <div className="searchResults"><h3>Групи</h3>{searchGroups.map((item) => <button key={item.id} onClick={() => { setActive("Групи"); setShowSearch(false); void openGroup(item.id); }}><span><b>{item.name}</b><small>{item.ages} · {item.location}{item.teacherName ? " · " + item.teacherName : ""}</small></span><i>{item.members.length}/{item.capacity}</i></button>)}</div>}
          {searchPayments.length > 0 && <div className="searchResults"><h3>Оплати</h3>{searchPayments.map((payment) => { const student = leads.find((lead) => lead.id === payment.studentId); const plan = plans.find((item) => item.id === payment.planId); return <button key={payment.id} onClick={() => { setShowSearch(false); goToPayment(payment.id); }}><span><b>{student?.child ?? "Учень"} · {plan?.name ?? "Оплата"}</b><small>{student?.parent ?? "Відповідальний не вказаний"}{student?.phone ? " · " + formatUaPhone(student.phone) : ""}</small></span><i>{payment.balanceAmount > 0 ? "Залишок " + money(payment.balanceAmount) : "Сплачено"}</i></button>; })}</div>}
          {searchStaff.length > 0 && <div className="searchResults"><h3>Працівники</h3>{searchStaff.map((item) => <button key={item.id} onClick={() => { setActive("Працівники"); setSelectedStaffId(item.id); setShowSearch(false); }}><span><b>{item.fullName}</b><small>{item.role} · {item.email || item.phone}</small></span><i>{item.isActive ? "Активний" : "Неактивний"}</i></button>)}</div>}
        </div>
      </div>}

      {showLeadForm && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowLeadForm(false)}>×</button>
          <p className="eyebrow">Нова заявка</p><h2>Додати дитину</h2>
          <div className="formTwo">
            <label>Ім’я дитини *<input className={leadChildName && personNameError(leadChildName, "Ім’я дитини") ? "inputInvalid" : ""} value={leadChildName} maxLength={120} onChange={(e) => setLeadChildName(e.target.value)} placeholder="Максим" />{leadChildName && personNameError(leadChildName, "Ім’я дитини") && <small className="fieldError">{personNameError(leadChildName, "Ім’я дитини")}</small>}</label>
            <label>Прізвище дитини<input className={leadChildLastName && personNameError(leadChildLastName, "Прізвище дитини") ? "inputInvalid" : ""} value={leadChildLastName} maxLength={120} onChange={(e) => setLeadChildLastName(e.target.value)} placeholder="Коваль" />{leadChildLastName && personNameError(leadChildLastName, "Прізвище дитини") && <small className="fieldError">{personNameError(leadChildLastName, "Прізвище дитини")}</small>}</label>
          </div>
          <div className="formTwo">
            <label>Вік<input type="number" min={3} max={25} value={leadAge} onChange={(e) => setLeadAge(Number(e.target.value))} /></label>
            <label>Телефон дитини <small>(необов’язково)</small><input type="tel" inputMode="tel" maxLength={19} className={leadChildPhone && uaPhoneError(leadChildPhone, false) ? "inputInvalid" : ""} value={leadChildPhone} onChange={(e) => setLeadChildPhone(e.target.value)} onBlur={() => { if (normalizeUaPhone(leadChildPhone)) setLeadChildPhone(formatUaPhone(leadChildPhone)); }} placeholder="+380 67 123 45 67" />{leadChildPhone && uaPhoneError(leadChildPhone, false) && <small className="fieldError">{uaPhoneError(leadChildPhone, false)}</small>}</label>
          </div>
          <label>Ім’я та прізвище відповідального *<input className={leadContactName && fullNameError(leadContactName, "Відповідальна особа") ? "inputInvalid" : ""} value={leadContactName} maxLength={160} autoComplete="name" onChange={(e) => setLeadContactName(e.target.value)} placeholder="Оксана Петренко" />{leadContactName && fullNameError(leadContactName, "Відповідальна особа") && <small className="fieldError">{fullNameError(leadContactName, "Відповідальна особа")}</small>}</label>
          <label>Телефон відповідального *<input type="tel" inputMode="tel" autoComplete="tel" maxLength={19} className={leadPhone && uaPhoneError(leadPhone) ? "inputInvalid" : ""} value={leadPhone} onChange={(e) => setLeadPhone(e.target.value)} onBlur={() => { if (normalizeUaPhone(leadPhone)) setLeadPhone(formatUaPhone(leadPhone)); }} placeholder="+380 67 123 45 67" />{leadPhone && uaPhoneError(leadPhone) && <small className="fieldError">{uaPhoneError(leadPhone)}</small>}</label>
          <label>Джерело<select value={leadSource} onChange={(e) => setLeadSource(e.target.value)}>
            <option value="phone">Телефон</option>
            <option value="website">Сайт</option>
            <option value="instagram">Instagram</option>
            <option value="recommendation">Рекомендація</option>
            <option value="walk-in">Зайшли особисто</option>
          </select></label>
          <label>Коментар<textarea value={leadComment} onChange={(e) => setLeadComment(e.target.value)} placeholder="Що цікавить, бажаний час, примітки…" /></label>
          <button className="primary full" disabled={Boolean(personNameError(leadChildName, "Ім’я дитини") || personNameError(leadChildLastName, "Прізвище дитини") || uaPhoneError(leadChildPhone, false) || fullNameError(leadContactName, "Відповідальна особа") || uaPhoneError(leadPhone))} onClick={createManualLead}>Створити заявку</button>
        </div>
      </div>}

      {showInviteForm && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowInviteForm(false)}>×</button>
          <p className="eyebrow">Доступ до CRM</p><h2>Запросити працівника</h2>
          {!inviteLink ? <>
            <label>Email *<input type="email" autoComplete="email" maxLength={255} className={inviteEmail && emailError(inviteEmail, true) ? "inputInvalid" : ""} value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="teacher@example.com" />{inviteEmail && emailError(inviteEmail, true) && <small className="fieldError">{emailError(inviteEmail, true)}</small>}</label>
            <label>Роль<select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as StaffRoleDemo)}>{["Адміністратор","Менеджер","Викладач","Бухгалтер"].map((role) => <option key={role}>{role}</option>)}</select></label>
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
          <label>Роль<select value={staffRole} onChange={(e) => setStaffRole(e.target.value as StaffRoleDemo)}>{["Власник","Адміністратор","Менеджер","Викладач","Бухгалтер"].map((role) => <option key={role}>{role}</option>)}</select></label>
          <div className="formTwo"><label>Email<input type="email" autoComplete="email" maxLength={255} className={staffEmail && emailError(staffEmail) ? "inputInvalid" : ""} value={staffEmail} onChange={(e) => setStaffEmail(e.target.value)} />{staffEmail && emailError(staffEmail) && <small className="fieldError">{emailError(staffEmail)}</small>}</label><label>Телефон<input type="tel" inputMode="tel" autoComplete="tel" maxLength={19} className={staffPhone && uaPhoneError(staffPhone, false) ? "inputInvalid" : ""} value={staffPhone} onChange={(e) => setStaffPhone(e.target.value)} onBlur={() => { if (normalizeUaPhone(staffPhone)) setStaffPhone(formatUaPhone(staffPhone)); }} placeholder="+380 67 123 45 67" />{staffPhone && uaPhoneError(staffPhone, false) && <small className="fieldError">{uaPhoneError(staffPhone, false)}</small>}</label></div><div className="formNotice">Для працівника потрібно вказати хоча б email або телефон.</div>
          <button className="primary full" disabled={Boolean(personNameError(staffName, "Ім’я та прізвище") || emailError(staffEmail) || uaPhoneError(staffPhone, false) || (!staffEmail.trim() && !staffPhone.trim()))} onClick={createStaffMember}>Додати працівника</button>
        </div>
      </div>}

      {showLocationForm && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowLocationForm(false)}>×</button>
          <p className="eyebrow">Мережа</p><h2>Нова локація</h2>
          <label>Назва<input value={locationName} onChange={(e) => setLocationName(e.target.value)} placeholder="AeroKids Центр" /></label>
          <label>Адреса<input value={locationAddress} onChange={(e) => setLocationAddress(e.target.value)} placeholder="Івано-Франківськ" /></label>
          <button className="primary full" disabled={!locationName.trim()} onClick={createLocationDemo}>Створити локацію</button>
        </div>
      </div>}

      {selectedGroupId && <div className="drawerBackdrop groupPageBackdrop">
        <aside className="drawer groupDetailDrawer" onClick={(e) => e.stopPropagation()}>
          <div className="groupPageTopbar">
            <button className="groupBackButton" onClick={() => { setSelectedGroupId(null); setGroupDetail(null); setShowGroupCandidatePicker(false); setGroupCandidateId(""); setGroupTeacherEditing(false); }}>← До списку груп</button>
            <button className="groupPageClose" aria-label="Закрити групу" onClick={() => { setSelectedGroupId(null); setGroupDetail(null); setShowGroupCandidatePicker(false); setGroupCandidateId(""); setGroupTeacherEditing(false); }}>×</button>
          </div>
          <p className="eyebrow">Група</p>
          <div className="groupDetailHero">
            <div className="groupDetailIdentity">
              <h2>{groupDetail?.group.name ?? selectedGroup?.name ?? "Група"}</h2>
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
          {apiEnabled && groupDetail && <div className="groupMemberList">
            <div className="groupMemberSectionHead"><div><b>Активні учасники</b><small>{groupDetail.members.length} у групі</small></div></div>
            {groupDetail.members.length === 0 && <div className="emptyState">У групі немає активних або призупинених учнів.</div>}
            {groupDetail.members.map((member) => {
              const billingLabel = member.billing?.status === "overdue" ? "Прострочено" : member.billing?.status === "due" ? "Оплата сьогодні" : member.billing?.status === "upcoming" ? "Очікується" : member.billing?.status === "current" ? "Сплачено" : "Без тарифу";
              const latestPayment = member.payments.find((payment) => payment.balance_minor > 0) ?? member.payments[0];
              const usage = member.billing?.lessons_included != null ? `${member.billing.lessons_used ?? 0}/${member.billing.lessons_included} використано · залишилось ${member.billing.lessons_remaining ?? 0}` : "";
              return <article className="groupMemberCard groupMemberCardCompact" key={member.student_id}>
                <div className="groupMemberIdentityCell">
                  <div className="groupMemberTop"><span className="candidateAvatar">{member.first_name[0]}</span><div><b>{member.first_name} {member.last_name ?? ""}</b><small>{member.age ?? "—"} років · з {new Date(member.enrollment_started_at + "T00:00:00").toLocaleDateString("uk-UA")}</small><small>{member.contact_name ?? "Відповідальний не вказаний"}{member.contact_phone ? " · " + formatUaPhone(member.contact_phone) : ""}</small></div></div>
                  <button className="link groupMemberOpen" onClick={() => { setSelectedStudentId(member.student_id); closeGroupDetail(); setActive("Учні"); }}>Картка →</button>
                </div>
                <button className="groupMemberMetricButton attendanceMetric" onClick={() => goToStudentAttendance(member.student_id, groupDetail.group.id)}>
                  <small>Відвідування</small><b>{member.attendance.attendance_rate}%</b><em>{member.attendance.present} був · {member.attendance.late} запізн. · {member.attendance.absent} нема · {member.attendance.excused} поважн.</em><i>Відкрити →</i>
                </button>
                {member.billing ? <div className="groupMemberFinanceCell">
                  <button className="groupMemberMetricButton paymentMetric" onClick={() => goToStudentPayments(member.student_id, latestPayment?.id)}>
                    <small>Оплата</small><b className={"billingText " + member.billing.status}>{billingLabel}</b><em>{member.billing.plan_name ?? "Тариф не вказано"}{usage ? " · " + usage : ""}{member.billing.subscription_ends_on ? " · до " + new Date(member.billing.subscription_ends_on + "T00:00:00").toLocaleDateString("uk-UA") : ""}</em><i>{member.billing.amount_due_minor > 0 ? "Борг " + money(member.billing.amount_due_minor / 100) : "Відкрити →"}</i>
                  </button>
                  {member.payments.length > 0 && <details className="memberPayments memberPaymentsInline"><summary>Історія оплат ({member.payments.length})</summary><div>{member.payments.map((payment) => <button className="memberPaymentHistoryRow" key={payment.id} onClick={() => goToStudentPayments(member.student_id, payment.id)}><span>{payment.note ?? "Нарахування"}<small>{payment.due_date ? "До " + new Date(payment.due_date + "T00:00:00").toLocaleDateString("uk-UA") : "Без дати"}</small></span><b>{money(payment.adjusted_amount_minor / 100)}<small>{payment.balance_minor > 0 ? "Залишок " + money(payment.balance_minor / 100) : payment.status === "cancelled" ? "Скасовано" : payment.status === "refunded" ? "Повернено" : "Сплачено"}</small></b></button>)}</div></details>}
                </div> : <div className="groupMemberFinanceCell"><span className="groupMemberMetricStatic"><small>Оплата</small><b>Приховано для ролі</b><em>Фінансові дані недоступні</em></span></div>}
              </article>;
            })}
          </div>}
        </aside>
      </div>}

      {selectedStaff && <div className="drawerBackdrop" onClick={() => setSelectedStaffId(null)}>
        <aside className="drawer studentDrawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setSelectedStaffId(null)}>×</button>
          <p className="eyebrow">Працівник</p>
          <div className="studentHero"><span>{selectedStaff.fullName[0]}</span><div><h2>{selectedStaff.fullName}</h2><p>{selectedStaff.role}</p></div></div>
          <div className="contactCard"><span>Контакти</span><b>{selectedStaff.email || "Email не вказано"}</b><a href={"tel:" + selectedStaff.phone.replace(/\s/g,"")}>{selectedStaff.phone || "Телефон не вказано"}</a></div>
          <div className="studentSection"><h3>Локації</h3><div className="assignmentList">{locations.map((location) => <label key={location.id}><input type="checkbox" checked={selectedStaff.locationIds.includes(location.id)} onChange={() => toggleStaffLocation(selectedStaff.id, location.id)} /><span>{location.name}<small>{location.address}</small></span></label>)}</div></div>
          <div className="studentSection"><h3>Групи</h3><div className="assignmentList">{groups.map((group) => <label key={group.id}><input type="checkbox" checked={selectedStaff.groupIds.includes(group.id)} onChange={() => toggleStaffGroup(selectedStaff.id, group.id)} /><span>{group.name}<small>{group.schedule}</small></span></label>)}</div></div>
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
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowPlanForm(false)}>×</button>
          <p className="eyebrow">Абонементи</p><h2>Новий тариф</h2>
          <label>Назва<input value={planName} onChange={(e) => setPlanName(e.target.value)} /></label>
          <div className="formTwo">
            <label>Ціна, грн<input type="text" inputMode="numeric" pattern="[0-9]*" placeholder="2500" value={planPrice} onChange={(e) => setPlanPrice(e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, ""))} /></label>
            <label>Занять<input type="text" inputMode="numeric" pattern="[0-9]*" placeholder="8" value={planLessons} onChange={(e) => setPlanLessons(e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, ""))} /></label>
          </div>
          <button className="primary full" disabled={!planName.trim() || planPrice === ""} onClick={createPlan}>Створити тариф</button>
        </div>
      </div>}

            {showPaymentForm && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowPaymentForm(false)}>×</button>
          <p className="eyebrow">Нарахування</p><h2>Створити оплату</h2>
          <label>Учень<select value={paymentStudentId} onChange={(e) => setPaymentStudentId(e.target.value)}>{activeStudents.map((student) => <option value={student.id} key={student.id}>{student.child} · відповідальний: {student.parent}</option>)}</select></label>
          <label>Абонемент<select value={paymentPlanId} onChange={(e) => setPaymentPlanId(e.target.value)}>{plans.filter((plan) => plan.price > 0).map((plan) => <option value={plan.id} key={plan.id}>{plan.name} · {money(plan.price)}</option>)}</select></label>
          <label>Оплатити до<input type="date" value={paymentDueDate} min={localDateInput(new Date())} onChange={(e) => setPaymentDueDate(e.target.value)} /></label>
          <label className="toggleRow"><input type="checkbox" checked={paymentAutoRenew} onChange={(e) => setPaymentAutoRenew(e.target.checked)} /><span><b>Автопродовження</b><small>Наступне нарахування створиться автоматично перед завершенням цього періоду.</small></span></label>
          {activeStudents.length === 0 && <div className="formNotice">Спочатку зарахуйте хоча б одного учня до групи.</div>}
          {!plans.some((plan) => plan.price > 0) && <div className="formNotice">Створіть тариф із ціною, щоб зробити нарахування.</div>}
          <button className="primary full" disabled={paymentSaving || !paymentStudentId || !paymentPlanId || !plans.some((plan) => plan.id === paymentPlanId && plan.price > 0)} onClick={createPayment}>{paymentSaving ? "Створюємо…" : "Створити нарахування"}</button>
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
            <div><span>Локація</span><b>{studentGroup(selectedStudent.id)?.location ?? "—"}</b></div>
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
              <h3>Перевести в іншу групу</h3>
              <select className="transferSelect" value={transferGroupId ?? ""} onChange={(e) => setTransferGroupId(e.target.value || null)}>
                <option value="">Оберіть групу</option>
                {groups.map((group) => <option value={group.id} key={group.id}>{group.name} · {group.members.length}/{group.capacity}</option>)}
              </select>
              <button className="primary full" disabled={transferGroupId === null || transferGroupId === studentGroup(selectedStudent.id)?.id} onClick={transferStudent}>Перевести учня</button>
            </div>
          </>}

          {apiEnabled ? <AuditHistory title="Історія учня" events={entityEvents} loading={historyLoading} /> : <div className="history">
            <h3>Історія учня</h3>
            <div><i></i><p><b>Пробне заняття</b><span>{selectedStudent.recommendedLevel ?? "Рівень не вказано"}</span></p></div>
            <div><i></i><p><b>Зараховано</b><span>{studentGroup(selectedStudent.id)?.name ?? "Групу не вказано"}</span></p></div>
          </div>}
        </aside>
      </div>}

      {showGroupForm && <div className="modalBackdrop">
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowGroupForm(false)}>×</button>
          <p className="eyebrow">Нова група</p>
          <h2>Сформувати групу</h2>
          <p className="modalIntro">Вибрано {selectedCandidates.length} дітей. Після створення вони перейдуть зі списку очікування в активну групу.</p>
          <label>Назва групи<input value={groupName} onChange={(e) => setGroupName(e.target.value)} /></label>
          <div className="formTwo">
            <label>Місткість<input type="number" min={1} max={30} value={groupCapacity} onChange={(e) => setGroupCapacity(Number(e.target.value))} /></label>
            <label>Локація<select value={groupLocationId} onChange={(e) => setGroupLocationId(e.target.value)}>
              <option value="">Без локації</option>
              {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
            </select></label>
          </div>
          <ScheduleSlotEditor value={groupSchedule} onChange={setGroupSchedule} />
          <div className="selectedNames">{leads.filter((x) => selectedCandidates.includes(x.id)).map((x) => {
            const compatibility = candidateCompatibility(x, groupSchedule, groupLocationId || null);
            return <span className={"candidateCompatibility " + compatibility.state} key={x.id}>
              <b>{x.child} · {x.age}</b><small>{compatibility.icon} {compatibility.label}</small><small>{compatibility.detail}</small>
            </span>;
          })}</div>
          <button className="primary full" disabled={selectedCandidates.length > groupCapacity || hasDuplicateSlots(groupSchedule)} onClick={createGroupFromCandidates}>
            {selectedCandidates.length > groupCapacity ? "Збільште місткість групи" : hasDuplicateSlots(groupSchedule) ? "Приберіть однакові слоти" : "Створити групу і зарахувати"}
          </button>
        </div>
      </div>}

      {selected && <div className="drawerBackdrop" onClick={() => setSelectedId(null)}>
        <aside className="drawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setSelectedId(null)}>×</button>
          <p className="eyebrow">Картка заявки</p>
          <h2>{selected.child}, {selected.age} років</h2>
          <div className="contactCard"><span>Контакт</span><b>{selected.parent}</b><a href={"tel:" + selected.phone.replace(/\s/g, "")}>{selected.phone}</a></div>
          {["Пробне заплановано","Після пробного","Відмовились","Не відповідає","Неактуально","Зарахований"].includes(selected.status) || ["no_show","cancelled"].includes(selected.trialResult ?? "")
            ? <div className="statusField statusReadonly">Статус<strong>{leadDisplayStatus(selected)}</strong></div>
            : <label className="statusField">Статус
                <select value={selected.status} onChange={(e) => updateStatus(selected.id, e.target.value as LeadStatus)}>
                  {statuses.filter((status) => ["Нова","Зв'язались","Очікує групу"].includes(status)).map((status) => <option key={status}>{status}</option>)}
                </select>
              </label>}
          <div className="detailGrid"><span>Джерело<b>{leadSourceLabel(selected.source)}</b></span><span>Вік<b>{selected.age}</b></span></div>
          {selected.nextContactAt && <div className="noteBox followUpBox"><span>Наступний контакт</span><p>{new Date(selected.nextContactAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</p></div>}
          {["Відмовились","Не відповідає","Неактуально"].includes(selected.status) && <div className="noteBox closedLeadBox"><span>Заявку закрито</span><p><b>{selected.status}</b>{selected.closeReason ? " · " + closeReasonLabel(selected.closeReason) : ""}</p>{selected.closeNote && <p>{selected.closeNote}</p>}<button className="search reopenLead" onClick={reopenLead}>Повернути в роботу</button></div>}
          {selected.comment && <div className="noteBox"><span>Коментар</span><p>{selected.comment}</p></div>}
          {selected.trialAt && <div className="trialSummary"><span>Пробне заняття</span><b>{new Date(selected.trialAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</b><small>{selected.trialLocation ?? "Локацію не вказано"}</small></div>}
          <div className="preferenceSummary">
            <div><span>Бажана локація</span><b>{selected.preferredLocationName ?? "Не вказано"}</b></div>
            <div><span>Бажаний час</span><b>{availabilityLabel(selected.availability ?? [])}</b></div>
            <button className="search" onClick={() => setPreferenceMode((value) => !value)}>{preferenceMode ? "Скасувати" : "Змінити"}</button>
          </div>

          {preferenceMode && <div className="workflowBox">
            <div className="workflowHead"><h3>Побажання щодо графіка</h3><button onClick={() => setPreferenceMode(false)}>×</button></div>
            <p className="softPreferenceHint">Це орієнтовні побажання сім’ї. Фінальний графік узгоджується під час формування групи.</p>
            <label>Бажана локація<select value={preferenceLocationId} onChange={(e) => setPreferenceLocationId(e.target.value)}>
              <option value="">Не має значення</option>
              {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
            </select></label>
            <AvailabilityWindowEditor value={availabilityWindows} onChange={setAvailabilityWindows} />
            <button className="primary full" disabled={preferenceSaving || availabilityWindows.some((x) => x.end_time <= x.start_time)} onClick={saveStudentPreferences}>{preferenceSaving ? "Зберігаємо…" : "Зберегти побажання"}</button>
          </div>}



          {trialMode === "schedule" && <div className="workflowBox">
            <div className="workflowHead"><h3>Запис на пробне</h3><button onClick={() => setTrialMode(null)}>×</button></div>
            <DateTimeEditor label="Дата і час" value={trialAt} onChange={setTrialAt} />
            <label>Локація<select value={trialLocationId} onChange={(e) => { setTrialLocationId(e.target.value); setTrialLocation(locations.find((location) => location.id === e.target.value)?.name ?? ""); }}>
              <option value="">Без локації</option>
              {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
            </select></label>
            <button className="primary full" onClick={scheduleTrial}>Підтвердити пробне</button>
          </div>}

          {trialMode === "complete" && <div className="workflowBox">
            <div className="workflowHead"><h3>{leadProcedureTarget === "no_show" ? "Зафіксувати пропущене пробне" : "Результат пробного"}</h3><button onClick={() => { setTrialMode(null); setLeadProcedureTarget(null); }}>×</button></div>
            {!selected.trialId && <><DateTimeEditor label="Коли було пробне" value={trialAt} onChange={setTrialAt} /><label>Локація<select value={trialLocationId} onChange={(e) => setTrialLocationId(e.target.value)}><option value="">Без локації</option>{locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}</select></label></>}
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
            {selected.status === "Очікує групу" && <small>Готові навчатися · потрібно підібрати групу.</small>}
          </div>}

          {leadProcedureTarget === "waiting" && <div className="workflowBox leadDirectEnrollmentStep">
            <div className="workflowHead"><h3>Зарахувати в групу</h3><button onClick={() => { setLeadProcedureTarget(null); setLeadEnrollmentGroupId(""); }}>×</button></div>
            <p className="softPreferenceHint">Попередні етапи можна пропустити. Для зарахування обов’язково лише обрати групу з вільним місцем.</p>
            <label>Група<select value={leadEnrollmentGroupId} onChange={(e) => setLeadEnrollmentGroupId(e.target.value)}>
              <option value="">Оберіть групу</option>
              {groups.filter((group) => group.members.length < group.capacity).map((group) => <option value={group.id} key={group.id}>{group.name} · {group.schedule} · {group.location} · вільно {group.capacity - group.members.length}</option>)}
            </select></label>
            {groups.length > 0 && groups.every((group) => group.members.length >= group.capacity) && <div className="emptyState compactEmpty">Немає груп із вільними місцями.</div>}
            <button className="primary full" disabled={!leadEnrollmentGroupId || leadEnrollmentSaving} onClick={enrollLeadDirectly}>{leadEnrollmentSaving ? "Зараховуємо…" : "Зарахувати дитину"}</button>
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

          {postTrialMode === "thinking" && <div className="workflowBox">
            <div className="workflowHead"><h3>{selected.trialResult === "no_show" || selected.trialResult === "cancelled" ? "Передзвонити пізніше" : "Ще думають"}</h3><button onClick={() => setPostTrialMode(null)}>×</button></div>
            <p className="softPreferenceHint">Залишаємо заявку в роботі й ставимо дату, коли треба зв’язатися з батьками знову.</p>
            <DateTimeEditor label="Наступний контакт" value={followUpAt} onChange={setFollowUpAt} />
            <button className="primary full" disabled={!followUpAt} onClick={saveThinkingFollowUp}>Зберегти нагадування</button>
          </div>}

          {postTrialMode === "close" && <div className="workflowBox">
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
            <button className="search dangerSoft" onClick={() => { setCloseKind("declined"); setPostTrialMode("close"); setWorkspaceError(""); }}>Скасувати заявку</button>
          </div>}

          {apiEnabled ? <AuditHistory title="Історія" events={entityEvents} loading={historyLoading} /> : <div className="history">
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

function leadKanbanColumn(lead: Lead): LeadKanbanColumnId {
  if (["Відмовились", "Не відповідає", "Неактуально"].includes(lead.status)) return "closed";
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
  const [closedExpanded, setClosedExpanded] = useState(false);
  const activeColumns = leadKanbanColumns.filter((column) => column.id !== "closed");
  const closedColumn = leadKanbanColumns.find((column) => column.id === "closed")!;
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
            <div><b>{lead.child}</b><small>{lead.age ? lead.age + " років" : "Вік не вказано"} · {lead.parent}</small></div>
            <button className="kanbanMore" aria-label="Відкрити заявку" onClick={(event) => { event.stopPropagation(); onOpen(lead.id); }}>•••</button>
          </div>
          <div className="kanbanMeta">
            <span className="sourceBadge">{leadSourceLabel(lead.source)}</span>
            {lead.preferredLocationName && <span className="locationBadge">{lead.preferredLocationName}</span>}
            {lead.recommendedLevel && <span className="levelBadge">{lead.recommendedLevel}</span>}
          </div>
          <div className={"kanbanNextAction " + urgency}><i></i><span>{leadNextAction(lead)}</span></div>
          {lead.phone && <div className="kanbanPhone">{formatUaPhone(lead.phone)}</div>}
          {movingId === lead.id && <div className="kanbanSaving">Оновлюємо…</div>}
        </article>;
      })}
    </div>
  </section>;

  return <div className="kanbanBoard">
    <div className="leadKanban">{activeColumns.map((column) => renderColumn(column, leads.filter((lead) => leadKanbanColumn(lead) === column.id)))}</div>
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
      <b>{lead.child}</b><span>{lead.age}</span><span>{lead.parent}</span><span>{leadSourceLabel(lead.source)}</span><span className="pill">{leadDisplayStatus(lead)}</span><span className={"nextAction " + (lead.nextContactAt && dateValue(lead.nextContactAt) < Date.now() ? "overdue" : "")}>{leadNextAction(lead)}</span>
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
  const dayNames = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];
  const ordered = [...items].sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time));
  const grouped = new Map<string, string[]>();
  ordered.forEach((item) => {
    const time = item.start_time.slice(0, 5);
    const days = grouped.get(time) ?? [];
    days.push(dayNames[item.weekday] ?? "?");
    grouped.set(time, days);
  });
  return [...grouped.entries()].map(([time, days]) => `${days.join(" / ")} · ${time}`).join("; ");
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
    lessons: item.lessons_included,
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

function leadNextAction(lead: Lead) {
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
    closeReason: item.close_reason ?? undefined,
    closeNote: item.close_note ?? undefined,
  }));

  const students: Lead[] = bundle.students.map((item) => ({
    id: item.student_id,
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

function AuditHistory({ title, events, loading }: { title: string; events: ApiAuditEvent[]; loading: boolean }) {
  return <div className="history">
    <h3>{title}</h3>
    {loading && <div className="historyEmpty">Завантажуємо історію…</div>}
    {!loading && events.length === 0 && <div className="historyEmpty">Подій поки немає.</div>}
    {!loading && events.map((event) => <div key={event.id}>
      <i></i>
      <p>
        <b>{auditEventLabel(event.event_type)}</b>
        <span>{auditEventDetail(event)} · {new Date(event.created_at).toLocaleString("uk-UA")}{event.actor_name ? " · " + event.actor_name : ""}</span>
      </p>
    </div>)}
  </div>;
}

function auditEventLabel(type: string) {
  const labels: Record<string, string> = {
    "lead.created": "Заявка створена",
    "lead.duplicate_intake": "Повторна заявка",
    "student.crm_status_changed": "Статус заявки змінено",
    "trial.scheduled": "Пробне заплановано",
    "trial.rescheduled": "Пробне перенесено",
    "trial.completed": "Пробне пройдено",
    "trial.no_show": "Не прийшов на пробне",
    "trial.cancelled": "Пробне скасовано",
    "lead.outcome_updated": "Рішення по заявці",
    "student.enrolled": "Зараховано до групи",
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

function LoginView({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
  const params = new URLSearchParams(window.location.search);
  const inviteToken = params.get("invite");
  const resetToken = params.get("reset");
  const [inviteName, setInviteName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [bootstrapAvailable, setBootstrapAvailable] = useState(false);
  const [checkingBootstrap, setCheckingBootstrap] = useState(true);
  const [organizationName, setOrganizationName] = useState("AeroKids");
  const [organizationSlug, setOrganizationSlug] = useState("aerokids");
  const [ownerName, setOwnerName] = useState("");
  const [bootstrapSecret, setBootstrapSecret] = useState("");

  useEffect(() => {
    if (inviteToken || resetToken) {
      setCheckingBootstrap(false);
      return;
    }
    getBootstrapStatus()
      .then(setBootstrapAvailable)
      .catch(() => setBootstrapAvailable(false))
      .finally(() => setCheckingBootstrap(false));
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      onAuthenticated(await login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося увійти");
    } finally {
      setLoading(false);
    }
  };

  const acceptInvitation = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!inviteToken) return;
    setError("");
    setLoading(true);
    try {
      const nextSession = await acceptInvite({
        invite_token: inviteToken,
        full_name: inviteName.trim(),
        password,
      });
      window.history.replaceState({}, "", window.location.pathname);
      onAuthenticated(nextSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося прийняти запрошення");
    } finally {
      setLoading(false);
    }
  };

  const completePasswordReset = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!resetToken) return;
    setError("");
    setLoading(true);
    try {
      const nextSession = await resetPassword({
        reset_token: resetToken,
        password,
      });
      window.history.replaceState({}, "", window.location.pathname);
      onAuthenticated(nextSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося змінити пароль");
    } finally {
      setLoading(false);
    }
  };

  const setup = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      onAuthenticated(await bootstrapOwner({
        organization_name: organizationName.trim(),
        organization_slug: organizationSlug.trim().toLowerCase(),
        full_name: ownerName.trim(),
        email,
        password,
      }, bootstrapSecret.trim() || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося створити першу організацію");
    } finally {
      setLoading(false);
    }
  };

  return <div className="loginScreen">
    <div className="loginCard">
      <div className="loginBrand"><img className="brandLogo brandLogoLarge" src="/aerokids-logo-master-v1.png" alt="AeroKids" /><div><b>AeroKids CRM</b><small>Керування школою в одному місці</small></div></div>

      {resetToken ? <>
        <p className="eyebrow">Новий пароль</p>
        <h1>Створіть новий пароль</h1>
        <p className="loginIntro">Посилання одноразове. Після збереження ви одразу ввійдете у CRM.</p>
        <form onSubmit={completePasswordReset}>
          <label>Новий пароль<input type="password" minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="loginError">{error}</div>}
          <button className="primary full" disabled={loading}>{loading ? "Зберігаємо…" : "Змінити пароль"}</button>
        </form>
      </> : inviteToken ? <>
        <p className="eyebrow">Запрошення</p>
        <h1>Створіть свій доступ</h1>
        <p className="loginIntro">Вкажіть ім’я та пароль. Роль і організація вже задані запрошенням.</p>
        <form onSubmit={acceptInvitation}>
          <label>Ваше ім’я<input autoComplete="name" value={inviteName} onChange={(e) => setInviteName(e.target.value)} required /></label>
          <label>Пароль<input type="password" minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="loginError">{error}</div>}
          <button className="primary full" disabled={loading}>{loading ? "Створюємо доступ…" : "Прийняти запрошення"}</button>
        </form>
      </> : checkingBootstrap ? <div className="loginChecking">Перевіряємо CRM…</div> : bootstrapAvailable ? <>
        <p className="eyebrow">Перший запуск</p>
        <h1>Створіть першу організацію</h1>
        <p className="loginIntro">Це виконується один раз. Після цього ви станете власником організації та зможете запрошувати команду.</p>
        <form onSubmit={setup}>
          <label>Назва організації<input value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} required /></label>
          <label>Короткий slug<input value={organizationSlug} onChange={(e) => setOrganizationSlug(e.target.value.replace(/[^a-z0-9-]/g, ""))} required /></label>
          <label>Ваше ім’я<input autoComplete="name" value={ownerName} onChange={(e) => setOwnerName(e.target.value)} required /></label>
          <label>Email<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Пароль<input type="password" minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <label>Ключ першого запуску<input type="password" autoComplete="off" value={bootstrapSecret} onChange={(e) => setBootstrapSecret(e.target.value)} placeholder="Задається в Render → aerokids-crm-api → Environment" required /></label>
          <small className="setupHint">Введіть значення BOOTSTRAP_SECRET із налаштувань backend у Render.</small>
          {error && <div className="loginError">{error}</div>}
          <button className="primary full" disabled={loading}>{loading ? "Створюємо…" : "Створити CRM"}</button>
        </form>
      </> : <>
        <p className="eyebrow">Вхід</p>
        <h1>Увійдіть у CRM</h1>
        <p className="loginIntro">Використовуйте email і пароль вашого облікового запису.</p>
        <form onSubmit={submit}>
          <label>Email<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Пароль<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="loginError">{error}</div>}
          <button className="primary full" disabled={loading}>{loading ? "Входимо…" : "Увійти"}</button>
        </form>
        <small className="loginNote">Доступ визначається роллю в конкретній організації.</small>
      </>}
    </div>
  </div>;
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

const DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];
const TIME_OPTIONS = Array.from({ length: 56 }, (_, index) => `${String(8 + Math.floor(index / 4)).padStart(2, "0")}:${String((index % 4) * 15).padStart(2, "0")}`);

function TimeSelect({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label>{label}<select value={value.slice(0, 5)} onChange={(event) => onChange(event.target.value)}>{TIME_OPTIONS.map((time) => <option key={time}>{time}</option>)}</select></label>;
}

function WeekdayPicker({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <label>День<select value={value} onChange={(event) => onChange(Number(event.target.value))}>{DAY_NAMES.map((day, index) => <option value={index} key={day}>{day}</option>)}</select></label>;
}

function DurationSelect({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <label>Тривалість<select value={value} onChange={(event) => onChange(Number(event.target.value))}>{[45, 60, 75, 90].map((minutes) => <option value={minutes} key={minutes}>{minutes} хв</option>)}</select></label>;
}

function ScheduleSlotEditor({ value, onChange }: { value: DraftScheduleSlot[]; onChange: (value: DraftScheduleSlot[]) => void }) {
  const update = (index: number, patch: Partial<DraftScheduleSlot>) => onChange(value.map((slot, i) => i === index ? { ...slot, ...patch } : slot));
  return <fieldset className="slotEditor"><legend>Розклад групи</legend>{value.map((slot, index) => <div className="slotRow" key={index}>
    <WeekdayPicker value={slot.weekday} onChange={(weekday) => update(index, { weekday })} />
    <TimeSelect label="Початок" value={slot.start_time} onChange={(start_time) => update(index, { start_time })} />
    <DurationSelect value={slot.duration_minutes} onChange={(duration_minutes) => update(index, { duration_minutes })} />
    <button type="button" className="link danger" onClick={() => onChange(value.filter((_, i) => i !== index))} disabled={value.length === 1}>Видалити</button>
  </div>)}<button type="button" className="search" onClick={() => onChange([...value, { weekday: (value.at(-1)?.weekday ?? -1) + 1 > 6 ? 0 : (value.at(-1)?.weekday ?? -1) + 1, start_time: "17:00", duration_minutes: 60 }])}>+ Додати день</button></fieldset>;
}

function AvailabilityWindowEditor({ value, onChange }: { value: AvailabilitySlot[]; onChange: (value: AvailabilitySlot[]) => void }) {
  const update = (index: number, patch: Partial<AvailabilitySlot>) => onChange(value.map((slot, i) => i === index ? { ...slot, ...patch } : slot));
  return <div className="availabilityEditor">{value.map((slot, index) => <div className="availabilityRow" key={index}>
    <WeekdayPicker value={slot.weekday} onChange={(weekday) => update(index, { weekday })} />
    <TimeSelect label="Від" value={slot.start_time} onChange={(start_time) => update(index, { start_time })} />
    <TimeSelect label="До" value={slot.end_time} onChange={(end_time) => update(index, { end_time })} />
    <label>Пріоритет<select value={slot.preference ?? "preferred"} onChange={(e) => update(index, { preference: e.target.value as AvailabilitySlot["preference"] })}><option value="preferred">Бажано</option><option value="possible">Можливо</option><option value="avoid">Небажано</option></select></label>
    <label className="windowNote">Коментар<input value={slot.note ?? ""} onChange={(e) => update(index, { note: e.target.value || null })} placeholder="Необов’язково" /></label>
    <button type="button" className="link danger" onClick={() => onChange(value.filter((_, i) => i !== index))}>Видалити</button>
  </div>)}<button type="button" className="search" onClick={() => onChange([...value, { weekday: 0, start_time: "16:30", end_time: "19:00", preference: "preferred", note: null }])}>+ Додати ще варіант</button></div>;
}

function DateTimeEditor({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const [date, clock = "17:00"] = value.split("T");
  return <div className="dateTimeEditor"><label>Дата<input type="date" aria-label={label + ": дата"} value={date} onChange={(e) => onChange(`${e.target.value}T${clock}`)} /></label><TimeSelect label="Час" value={clock} onChange={(time) => onChange(`${date}T${time}`)} /></div>;
}

function scheduleDraftLabel(slots: DraftScheduleSlot[]) { return slots.map((slot) => `${DAY_NAMES[slot.weekday]} · ${slot.start_time}`).join("; "); }
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
