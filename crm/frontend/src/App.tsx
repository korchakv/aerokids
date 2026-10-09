Warning: truncated output (original token count: 44369)
Total output lines: 3862

import { useEffect, useMemo, useRef, useState } from "react";
import { UiIcon, navigationIcon } from "./components/UiIcon";
import { AuditHistory } from "./components/AuditHistory";
import { LoginView } from "./features/auth/LoginView";
import { allNav, roleLabel, visibleNavigation } from "./features/shell/navigation";
import { DashboardView } from "./features/shell/DashboardView";
import { GlobalSearch } from "./features/shell/GlobalSearch";
import { LeadKanban, LeadTable } from "./features/leads/LeadBoard";
import { LeadDrawer } from "./features/leads/LeadDrawer";
import { LeadCreateDialog } from "./features/leads/LeadCreateDialog";
import { initialLeads, statuses } from "./features/leads/demo";
import { availabilityLabel, flattenAvailabilityWindows, groupAvailabilitySlots } from "./features/leads/availability";
import { canonicalLeadSource, leadActionMeta, leadActionPriority, leadDisplayStatus, leadIsDeferred, leadKanbanColumn, leadMissingDetails, leadPrimaryActionLabel, leadSourceLabel, type EntityId, type Lead, type LeadKanbanColumnId, type LeadStatus } from "./features/leads/model";
import type { GroupItem } from "./features/groups/types";
import { GroupsView } from "./features/groups/GroupsView";
import { GroupDetailDrawer } from "./features/groups/GroupDetailDrawer";
import { GroupCreateDialog } from "./features/groups/GroupCreateDialog";
import { candidateCompatibility, MatchBadge, MatchExplanation } from "./features/groups/matching";
import { ageRange, hasDuplicateSlots, scheduleDraftLabel, scheduleSlots } from "./features/groups/helpers";
import { applyTeaching, SCHEDULE_DAY_NAMES, type LessonItem } from "./features/teaching/model";
import { AttendanceView } from "./features/teaching/AttendanceView";
import { type AttendanceValue } from "./features/teaching/attendance";
import { ScheduleView } from "./features/teaching/ScheduleView";
import { type PaymentDemo, type PlanDemo } from "./features/billing/model";
import { BillingDialogs } from "./features/billing/BillingDialogs";
import { PaymentsView } from "./features/billing/PaymentsView";
import type { LocationDemo } from "./features/locations/types";
import { LocationsView } from "./features/locations/LocationsView";
import { LocationDialog } from "./features/locations/LocationDialog";
import { staffRoleValue, type StaffDemo, type StaffRoleDemo } from "./features/staff/model";
import { StaffDrawer, StaffView } from "./features/staff/StaffView";
import { StaffDialogs } from "./features/staff/StaffDialogs";
import { SettingsView } from "./features/settings/SettingsView";
import { ReportsView } from "./features/reports/ReportsView";
import { StudentDrawer, StudentsView, type StudentFilter, type StudentLifecycleLabel } from "./features/students/StudentsView";
import { applyOperations, paymentPageItemToDemo } from "./features/operations/adapters";
import { applyWorkspace, crmStatusLabel, crmStatusValue, workspaceGroupToGroupItem, workspaceStudentLifecycle, workspaceStudentToLead } from "./features/workspace/adapters";
import { cleanSpaces, emailError, formatUaPhone, fullNameError, normalizeUaPhone, normalizedSearch, personNameError, searchMatches, uaPhoneError } from "./utils/contact";
import { addLocalDays, dateValue, dayOffsetForDate, defaultPaymentDueDate, lessonWeekdayLabel, localDateInput, startOfLocalWeek, toLocalDateTimeInput, weekdayLong } from "./utils/date";
import { AvailabilityWindowEditor, DateTimeEditor, DAY_NAMES, DurationSelect, ScheduleSlotEditor, TimeSelect, type AvailabilitySlot, type AvailabilityWindowDraft, type DraftScheduleSlot } from "./components/ScheduleEditors";
import { apiDelete, apiEnabled, apiPatch, apiPost, apiPut, changeOrganization, checkIntakeDuplicates, clearSession, loadAttendance, loadAuditEvents, loadGroupDetail, loadGroupRoster, loadOperations, loadOverviewReport, loadPaymentPage, loadPaymentReminders, loadSession, loadStudentAttendanceHistory, loadTeaching, loadWorkspace, loadWorkspaceGroupsPage, loadWorkspaceStudentsPage, recordPaymentReminder, refreshMe, runBillingRenewals, type ApiAuditEvent, type ApiGroupDetail, type ApiGroupRosterStudent, type ApiPaymentReminder, type ApiStudentAttendanceHistoryItem, type ApiStudentSubscription, type IntakeDuplicateMatch, type OverviewReport, type Session, type WorkspaceBundle } from "./api";


type UiScale = 1 | 1.1 | 1.25 | 1.4;
const UI_SCALE_LEVELS: UiScale[] = [1, 1.1, 1.25, 1.4];
const REGISTRY_PAGE_SIZE = 25;
const PAYMENT_PAGE_SIZE = 50;
type PaymentStatusFilter = "all" | "pending" | "paid" | "refunded" | "cancelled";
type PaymentOverdueFilter = "all" | "yes" | "no";




















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
  const [studentFilter, setStudentFilter] = useState<StudentFilter>("all");
  const [studentRegistryQuery, setStudentRegistryQuery] = useState("");
  const [studentRegistryRows, setStudentRegistryRows] = useState<Lead[]>([]);
  const [studentRegistryStates, setStudentRegistryStates] = useState<Record<EntityId, StudentLifecycleLabel>>({});
  const [studentRegistryTotal, setStudentRegistryTotal] = useState(0);
  const [studentRegistryOffset, setStudentRegistryOffset] = useState(0);
  const [studentRegistryLoading, setStudentRegistryLoading] = useState(false);
  const [studentRegistryError, setStudentRegistryError] = useState("");
  const [groupRegistryQuery, setGroupRegistryQuery] = useState("");
  const [groupRegistrySort, setGroupRegistrySort] = useState<"name" | "size_desc" | "size_asc">("name");
  const [groupRegistryRows, setGroupRegistryRows] = useState<GroupItem[]>([]);
  const [groupRegistryTotal, setGroupRegistryTotal] = useState(0);
  const [groupRegistryOffset, setGroupRegistryOffset] = useState(0);
  const [groupRegistryLoading, setGroupRegistryLoading] = useState(false);
  const [groupRegistryError, setGroupRegistryError] = useState("");
  const [registryRefreshTick, setRegistryRefreshTick] = useState(0);
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
  const [paymentRegistryRows, setPaymentRegistryRows] = useState<PaymentDemo[]>([]);
  const [paymentRegistryTotal, setPaymentRegistryTotal] = useState(0);
  const [paymentRegistryOffset, setPaymentRegistryOffset] = useState(0);
  const [paymentRegistryQuery, setPaymentRegistryQuery] = useState("");
  const [paymentRegistryStatus, setPaymentRegistryStatus] = useState<PaymentStatusFilter>("all");
  const [paymentRegistryOverdue, setPaymentRegistryOverdue] = useState<PaymentOverdueFilter>("all");
  const [paymentRegistrySort, setPaymentRegistrySort] = useState<"newest" | "due" | "student">("newest");
  const [paymentRegistryLoading, setPaymentRegistryLoading] = useState(false);
  const [paymentRegistryError, setPaymentRegistryError] = useState("");
  const [paymentRegistryRefreshTick, setPaymentRegistryRefreshTick] = useState(0);
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
  const [studentStates, setStudentStates] = useState<Record<EntityId, StudentLifecycleLabel>>({});
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
  const [trialAt, setTrialAt] = useState(() => `${localDateInput(new Date())}T17:00`);
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
  const [newLessonAt, setNewLessonAt] = useState(() => `${localDateInput(new Date())}T17:00`);
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
      setRegistryRefreshTick((value) => value + 1);
      setPaymentRegistryRefreshTick((value) => value + 1);
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
        setRegistryRefreshTick((value) => value + 1);
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

  useEffect(() => {
    setStudentRegistryOffset(0);
  }, [studentFilter, studentRegistryQuery]);

  useEffect(() => {
    setGroupRegistryOffset(0);
  }, [groupRegistryQuery, groupRegistrySort]);

  useEffect(() => {
    if (!apiEnabled || !session || active !== "Учні") return;
    let cancelled = false;
    setStudentRegistryLoading(true);
    setStudentRegistryError("");
    const timer = window.setTimeout(() => {
      loadWorkspaceStudentsPage(session, {
        q: studentRegistryQuery,
        status: studentFilter === "all" ? undefined : studentFilter,
        sort: "name",
        limit: REGISTRY_PAGE_SIZE,
        offset: studentRegistryOffset,
      }).then((page) => {
        if (cancelled) return;
        if (page.total > 0 && studentRegistryOffset >= page.total) {
          setStudentRegistryOffset(Math.floor((page.total - 1) / REGISTRY_PAGE_SIZE) * REGISTRY_PAGE_SIZE);
          return;
        }
        setStudentRegistryRows(page.items.map(workspaceStudentToLead));
        setStudentRegistryStates(Object.fromEntries(page.items.map((item) => [item.student_id, workspaceStudentLifecycle(item)])));
        setStudentRegistryTotal(page.total);
      }).catch((error) => {
        if (!cancelled) setStudentRegistryError(error instanceof Error ? error.message : "Не вдалося завантажити сторінку учнів");
      }).finally(() => {
        if (!cancelled) setStudentRegistryLoading(false);
      });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [active, session?.accessToken, session?.organizationId, studentFilter, studentRegistryQuery, studentRegistryOffset, registryRefreshTick]);

  useEffect(() => {
    if (!apiEnabled || !session || active !== "Групи") return;
    let cancelled = false;
    setGroupRegistryLoading(true);
    setGroupRegistryError("");
    const timer = window.setTimeout(() => {
      loadWorkspaceGroupsPage(session, {
        q: groupRegistryQuery,
        sort: groupRegistrySort,
        limit: REGISTRY_PAGE_SIZE,
        offset: groupRegistryOffset,
      }).then((page) => {
        if (cancelled) return;
        if (page.total > 0 && groupRegistryOffset >= page.total) {
          setGroupRegistryOffset(Math.floor((page.total - 1) / REGISTRY_PAGE_SIZE) * REGISTRY_PAGE_SIZE);
          return;
        }
        setGroupRegistryRows(page.items.map((item) => workspaceGroupToGroupItem(item)));
        setGroupRegistryTotal(page.total);
      }).catch((error) => {
        if (!cancelled) setGroupRegistryError(error instanceof Error ? error.message : "Не вдалося завантажити сторінку груп");
      }).finally(() => {
        if (!cancelled) setGroupRegistryLoading(false);
      });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [active, session?.accessToken, session?.organizationId, groupRegistryQuery, groupRegistrySort, groupRegistryOffset, registryRefreshTick]);

  useEffect(() => {
    setPaymentRegistryOffset(0);
  }, [paymentRegistryQuery, paymentRegistryStatus, paymentRegistryOverdue, paymentRegistrySort]);

  useEffect(() => {
    if (!apiEnabled || !session || active !== "Оплати") return;
    let cancelled = false;
    setPaymentRegistryLoading(true);
    setPaymentRegistryError("");
    const timer = window.setTimeout(() => {
      loadPaymentPage(session, {
        q: paymentRegistryQuery,
        status: paymentRegistryStatus === "all" ? undefined : paymentRegistryStatus,
        overdue: paymentRegistryOverdue === "all" ? undefined : paymentRegistryOverdue === "yes",
        sort: paymentRegistrySort,
        limit: PAYMENT_PAGE_SIZE,
        offset: paymentRegistryOffset,
      }).then((page) => {
        if (cancelled) return;
        if (paymentRegistryOffset > 0 && paymentRegistryOffset >= page.total) {
          setPaymentRegistryOffset(page.total === 0 ? 0 : Math.floor((page.total - 1) / PAYMENT_PAGE_SIZE) * PAYMENT_PAGE_SIZE);
          return;
        }
        setPaymentRegistryRows(page.items.map(paymentPageItemToDemo));
        setPaymentRegistryTotal(page.total);
      }).catch((error) => {
        if (!cancelled) setPaymentRegistryError(error instanceof Error ? error.message : "Не вдалося завантажити сторінку оплат");
      }).finally(() => {
        if (!cancelled) setPaymentRegistryLoading(false);
      });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [active, session?.accessToken, session?.organizationId, paymentRegistryQuery, paymentRegistryStatus, paymentRegistryOverdue, paymentRegistrySort, paymentRegistryOffset, paymentRegistryRefreshTick]);

    const selected = leads.find((lead) => lead.id === selectedId) ?? null;
  const selectedMissingDetails = selected ? leadMissingDetails(selected) : [];
  const selectedStudent = leads.find((lead) => lead.id === selectedStudentId)
    ?? studentRegistryRows.find((lead) => lead.id === selectedStudentId)
    ?? null;
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

  const demoRegistryStudents = useMemo(() => {
    const query = normalizedSearch(studentRegistryQuery);
    return visibleStudents.filter((student) => !query || normalizedSearch([
      student.child, student.parent, student.phone, student.childPhone, student.groupName,
    ].filter(Boolean).join(" ")).includes(query));
  }, [visibleStudents, studentRegistryQuery]);

  const demoRegistryGroups = useMemo(() => {
    const query = normalizedSearch(groupRegistryQuery);
    return groups
      .filter((group) => !query || normalizedSearch([group.name, group.location, group.teacherName].filter(Boolean).join(" ")).includes(query))
      .sort((a, b) => groupRegistrySort === "size_desc"
        ? (b.memberCount ?? b.members.length) - (a.memberCount ?? a.members.length)
        : groupRegistrySort === "size_asc"
          ? (a.memberCount ?? a.members.length) - (b.memberCount ?? b.members.length)
          : a.name.localeCompare(b.name, "uk-UA"));
  }, [groups, groupRegistryQuery, groupRegistrySort]);

  const registryStudents = apiEnabled ? studentRegistryRows : demoRegistryStudents;
  const registryGroups = apiEnabled
    ? groupRegistryRows.map((group) => {
      const hydrated = groups.find((item) => item.id === group.id);
      return hydrated ? {
        ...hydrated,
        ...group,
        schedule: hydrated.schedule,
        members: hydrated.members,
        teacherName: group.teacherName ?? hydrated.teacherName,
      } : group;
    })
    : demoRegistryGroups;
  const registryStudentStates = useMemo(
    () => ({ ...studentStates, ...studentRegistryStates }),
    [studentStates, studentRegistryStates],
  );

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
          childPhone: childPhone ? for…14369 tokens truncated…tus === "overdue").reduce((sum, payment) => sum + payment.balanceAmount, 0),
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
            <GlobalSearch
              open={showSearch}
              query={searchQuery}
              searchTerm={searchTerm}
              searchLeads={searchLeads}
              searchGroups={searchGroups}
              searchStaff={searchStaff}
              searchPayments={searchPayments}
              leads={leads}
              plans={plans}
              money={money}
              onOpenChange={setShowSearch}
              onQueryChange={setSearchQuery}
              onOpenLead={(id) => { setActive("Заявки"); setSelectedId(id); }}
              onOpenStudent={(id) => { setActive("Учні"); setSelectedStudentId(id); }}
              onOpenGroup={(id) => { setActive("Групи"); void openGroup(id); }}
              onOpenPayment={goToPayment}
              onOpenStaff={(id) => { setActive("Працівники"); setSelectedStaffId(id); }}
            />
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

        {active === "Дашборд" && <DashboardView
          groups={groups}
          leads={leads}
          plans={plans}
          todayLessons={todayLessons}
          todayTrials={todayTrials}
          dashboardLeadTasks={dashboardLeadTasks}
          renewalSubscriptionTasks={renewalSubscriptionTasks}
          dashboardPaymentTasks={dashboardPaymentTasks}
          dashboardTaskCount={dashboardTaskCount}
          todayKey={todayKey}
          canSeeSchedule={canSeeSchedule}
          money={money}
          onOpenSchedule={() => setActive("Розклад")}
          onOpenLesson={goToLesson}
          onOpenGroup={goToGroup}
          onOpenLead={openLead}
          onOpenStudent={(studentId) => { setSelectedStudentId(studentId); setActive("Учні"); }}
          onOpenPayment={goToPayment}
        />}

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

        {active === "Учні" && <StudentsView
          students={registryStudents}
          totalStudents={activeStudents.length}
          groupedStudents={activeStudents.filter((student) => studentGroup(student.id)).length}
          pausedStudents={Object.values(studentStates).filter((state) => state === "Пауза").length}
          groupCount={groups.length}
          studentFilter={studentFilter}
          onFilterChange={setStudentFilter}
          query={studentRegistryQuery}
          onQueryChange={setStudentRegistryQuery}
          pageTotal={apiEnabled ? studentRegistryTotal : registryStudents.length}
          pageLimit={REGISTRY_PAGE_SIZE}
          pageOffset={apiEnabled ? studentRegistryOffset : 0}
          loading={apiEnabled && studentRegistryLoading}
          error={studentRegistryError}
          onPreviousPage={() => setStudentRegistryOffset((value) => Math.max(0, value - REGISTRY_PAGE_SIZE))}
          onNextPage={() => setStudentRegistryOffset((value) => value + REGISTRY_PAGE_SIZE)}
          studentStates={registryStudentStates}
          groupForStudent={studentGroup}
          onOpenStudent={(studentId, currentGroupId) => {
            setSelectedStudentId(studentId);
            setTransferGroupId(currentGroupId);
          }}
        />}

        {active === "Розклад" && <ScheduleView
          groups={groups}
          lessonsThisWeek={lessonsThisWeek}
          trialsThisWeek={trialsThisWeek}
          scheduleWeekStart={scheduleWeekStart}
          scheduleWeekEnd={scheduleWeekEnd}
          scheduleWeekDays={scheduleWeekDays}
          completedThisWeek={completedThisWeek}
          unfinishedPastThisWeek={unfinishedPastThisWeek}
          scheduleFilterGroupId={scheduleFilterGroupId}
          scheduleWeekOffset={scheduleWeekOffset}
          todayKey={todayKey}
          attendance={attendance}
          groupTeacherName={(groupId) => groupTeacher(groupId)?.fullName}
          onScheduleFilterChange={setScheduleFilterGroupId}
          onPreviousWeek={() => setScheduleWeekOffset((value) => value - 1)}
          onCurrentWeek={() => setScheduleWeekOffset(0)}
          onNextWeek={() => setScheduleWeekOffset((value) => value + 1)}
          onOpenLead={openLead}
          onOpenLesson={goToLesson}
          newLessonGroupId={newLessonGroupId}
          newLessonAt={newLessonAt}
          newLessonDuration={newLessonDuration}
          newLessonTopic={newLessonTopic}
          onNewLessonGroupChange={setNewLessonGroupId}
          onNewLessonAtChange={setNewLessonAt}
          onNewLessonDurationChange={setNewLessonDuration}
          onNewLessonTopicChange={setNewLessonTopic}
          onCreateLesson={createLesson}
          canManageRecurringSchedule={canManageRecurringSchedule}
          scheduleGroupId={scheduleGroupId}
          scheduleWeekday={scheduleWeekday}
          scheduleTime={scheduleTime}
          scheduleDuration={scheduleDuration}
          onScheduleGroupChange={setScheduleGroupId}
          onScheduleWeekdayChange={setScheduleWeekday}
          onScheduleTimeChange={setScheduleTime}
          onScheduleDurationChange={setScheduleDuration}
          onCreateGroupSchedule={createGroupSchedule}
        />}

        {active === "Відвідування" && <AttendanceView
          attendanceDayOffset={attendanceDayOffset}
          attendanceDay={attendanceDay}
          attendanceDayKey={attendanceDayKey}
          attendanceTodayKey={attendanceTodayKey}
          attendanceNow={attendanceNow}
          journalLessons={journalLessons}
          groups={groups}
          nearestAttendanceLesson={nearestAttendanceLesson}
          selectedLessonId={selectedLessonId}
          completedAttendanceLessons={completedAttendanceLessons}
          pendingAttendanceLessons={pendingAttendanceLessons}
          lessonSaveNotice={lessonSaveNotice}
          focusedAttendanceStudentId={focusedAttendanceStudentId}
          focusedAttendanceStudent={focusedAttendanceStudent}
          focusedAttendanceGroup={focusedAttendanceGroup}
          focusedAttendanceRate={focusedAttendanceRate}
          focusedAttendanceCounts={focusedAttendanceCounts}
          studentAttendanceHistoryLoading={studentAttendanceHistoryLoading}
          focusedAttendanceRows={focusedAttendanceRows}
          selectedLesson={selectedLesson}
          lessonGroup={lessonGroup}
          lessonEditing={lessonEditing}
          lessonTopicDraft={lessonTopicDraft}
          lessonNotesDraft={lessonNotesDraft}
          lessonDetailsSaving={lessonDetailsSaving}
          lessonStudents={lessonStudents}
          attendance={attendance}
          attendanceNotes={attendanceNotes}
          attendanceLoading={attendanceLoading}
          attendanceSaving={attendanceSaving}
          onPreviousDay={() => setAttendanceDayOffset((value) => value - 1)}
          onToday={() => setAttendanceDayOffset(0)}
          onNextDay={() => setAttendanceDayOffset((value) => value + 1)}
          onSelectLesson={setSelectedLessonId}
          onCloseStudentHistory={() => { setFocusedAttendanceStudentId(null); setFocusedAttendanceGroupId(null); }}
          onOpenLesson={goToLesson}
          onBackToSchedule={() => setActive("Розклад")}
          onEditLesson={() => setLessonEditing(true)}
          onCancelLessonEdit={() => setLessonEditing(false)}
          onMarkAllPresent={markAllPresent}
          onMarkUnmarkedAbsent={markUnmarkedAbsent}
          onLessonTopicChange={setLessonTopicDraft}
          onLessonNotesChange={setLessonNotesDraft}
          onSaveLessonDetails={saveLessonDetails}
          onMarkAttendance={markAttendance}
          onAttendanceNoteChange={setAttendanceNote}
          onSaveAttendance={saveAttendance}
        />}

        {active === "Оплати" && <PaymentsView
          payments={visiblePaymentRows}
          plans={plans}
          subscriptions={subscriptions}
          leads={leads}
          paymentTotals={paymentTotals}
          paymentCounts={paymentCounts}
          query={paymentRegistryQuery}
          statusFilter={paymentRegistryStatus}
          overdueFilter={paymentRegistryOverdue}
          sort={paymentRegistrySort}
          pageTotal={visiblePaymentTotal}
          pageLimit={PAYMENT_PAGE_SIZE}
          pageOffset={paymentRegistryOffset}
          loading={apiEnabled && paymentRegistryLoading}
          error={paymentRegistryError}
          onQueryChange={setPaymentRegistryQuery}
          onStatusFilterChange={setPaymentRegistryStatus}
          onOverdueFilterChange={setPaymentRegistryOverdue}
          onSortChange={setPaymentRegistrySort}
          onPreviousPage={() => setPaymentRegistryOffset((value) => Math.max(0, value - PAYMENT_PAGE_SIZE))}
          onNextPage={() => setPaymentRegistryOffset((value) => value + PAYMENT_PAGE_SIZE)}
          paymentReminders={paymentReminders}
          reminderSavingId={reminderSavingId}
          focusedPaymentId={focusedPaymentId}
          canManagePlans={canManagePlans}
          showInactivePlans={showInactivePlans}
          money={money}
          formatPhone={formatUaPhone}
          onReminderHandled={markReminderHandled}
          onOpenPaymentForm={openPaymentForm}
          onMarkPaymentPaid={markPaymentPaid}
          onOpenPaymentAction={openPaymentAction}
          onToggleAutoRenew={toggleAutoRenew}
          onOpenPlanChange={openPlanChange}
          onResumeSubscription={resumeSubscriptionNow}
          onPauseSubscription={openPauseSubscription}
          onOpenPlanCreate={openPlanCreate}
          onOpenPlanEdit={openPlanEdit}
          onToggleInactivePlans={() => setShowInactivePlans((value) => !value)}
        />}

        {active === "Працівники" && <StaffView
          staff={staff}
          locations={locations}
          onSelectStaff={setSelectedStaffId}
          onInvite={() => { setInviteLink(""); setShowInviteForm(true); }}
          onCreate={() => setShowStaffForm(true)}
        />}

        {active === "Локації" && <LocationsView
          locations={locations}
          staff={staff}
          groups={groups}
          canManageLocations={canManageLocations}
          onCreate={openLocationCreation}
          onEdit={openLocationEdit}
        />}

                {active === "Налаштування" && <SettingsView
          organizationName={organizationName}
          organizationTimezone={organizationTimezone}
          organizationCurrency={organizationCurrency}
          organizationLocale={organizationLocale}
          organizationSaving={organizationSaving}
          onOrganizationName={setOrganizationName}
          onOrganizationTimezone={setOrganizationTimezone}
          onOrganizationCurrency={setOrganizationCurrency}
          onOrganizationLocale={setOrganizationLocale}
          onSaveOrganization={saveOrganizationSettings}
          theme={theme}
          onTheme={setTheme}
          uiScale={uiScale}
          canScaleDown={uiScale !== UI_SCALE_LEVELS[0]}
          canScaleUp={uiScale !== UI_SCALE_LEVELS[UI_SCALE_LEVELS.length - 1]}
          onScaleDown={() => changeUiScale(-1)}
          onScaleUp={() => changeUiScale(1)}
          organizationSlug={currentMembership?.organization_slug ?? ""}
          roleName={roleLabel(currentMembership?.role)}
        />}
        {active === "Звіти" && <ReportsView
          conversionPercent={leads.length ? Math.round(activeStudents.length / leads.length * 100) : 0}
          activeStudentCount={activeStudents.length}
          leadCount={leads.length}
          occupancyPercent={occupancy}
          occupiedSeats={occupiedSeats}
          totalCapacity={totalCapacity}
          attendanceRate={attendanceRate}
          attendanceTotal={overviewReport?.attendance.total ?? attendanceValues.length}
          paidAmount={money(overviewReport ? overviewReport.payments.paid_minor / 100 : paymentTotals.paid)}
          pendingAmount={money(overviewReport ? overviewReport.payments.pending_minor / 100 : paymentTotals.pending)}
          overdueAmount={money(overviewReport ? overviewReport.payments.overdue_minor / 100 : paymentTotals.overdue)}
          funnel={[
            { label: "Нова", count: overviewFunnelCount(overviewReport, "new", leads.filter((x) => x.status === "Нова").length) },
            { label: "Пробне", count: overviewFunnelCount(overviewReport, "trial_scheduled", leads.filter((x) => x.status === "Пробне заплановано").length) },
            { label: "Очікує групу", count: overviewFunnelCount(overviewReport, "waiting_for_group", waiting.length) },
            { label: "Зарахований", count: overviewFunnelCount(overviewReport, "enrolled", activeStudents.length) },
          ]}
          funnelMax={Math.max(1, overviewReport ? overviewReport.funnel.reduce((sum, item) => sum + item.count, 0) : leads.length)}
          attendance={{
            present: overviewReport?.attendance.present ?? attendanceStats.present,
            late: overviewReport?.attendance.late ?? attendanceStats.late,
            absent: overviewReport?.attendance.absent ?? attendanceStats.absent,
            excused: overviewReport?.attendance.excused ?? attendanceStats.excused,
          }}
          activeLocations={overviewReport?.active_locations ?? locations.filter((x) => x.isActive).length}
          activeStaff={overviewReport?.active_staff ?? staff.filter((x) => x.isActive).length}
          activeGroups={overviewReport?.active_groups ?? groups.length}
          activeStudents={overviewReport?.active_students ?? activeStudents.length}
        />}
        {active === "Групи" && <GroupsView
          groups={registryGroups}
          waiting={waiting}
          visibleWaiting={visibleWaiting}
          candidateLevels={candidateLevels}
          locations={locations}
          selectedCandidates={selectedCandidates}
          candidateAgeFilter={candidateAgeFilter}
          candidateLevelFilter={candidateLevelFilter}
          candidateLocationFilter={candidateLocationFilter}
          candidateMatchFilter={candidateMatchFilter}
          candidateSort={candidateSort}
          groupSchedule={groupSchedule}
          groupLocationId={groupLocationId}
          groupQuery={groupRegistryQuery}
          groupSort={groupRegistrySort}
          groupPageTotal={apiEnabled ? groupRegistryTotal : registryGroups.length}
          groupPageLimit={REGISTRY_PAGE_SIZE}
          groupPageOffset={apiEnabled ? groupRegistryOffset : 0}
          groupPageLoading={apiEnabled && groupRegistryLoading}
          groupPageError={groupRegistryError}
          onGroupQueryChange={setGroupRegistryQuery}
          onGroupSortChange={setGroupRegistrySort}
          onPreviousGroupPage={() => setGroupRegistryOffset((value) => Math.max(0, value - REGISTRY_PAGE_SIZE))}
          onNextGroupPage={() => setGroupRegistryOffset((value) => value + REGISTRY_PAGE_SIZE)}
          teacherNameForGroup={(groupId) => groupTeacher(groupId)?.fullName}
          onOpenGroup={(groupId) => { void openGroup(groupId); }}
          onOpenCreation={openGroupCreation}
          onToggleCandidate={toggleCandidate}
          onCandidateAgeFilterChange={setCandidateAgeFilter}
          onCandidateLevelFilterChange={setCandidateLevelFilter}
          onCandidateLocationFilterChange={setCandidateLocationFilter}
          onCandidateMatchFilterChange={setCandidateMatchFilter}
          onCandidateSortChange={setCandidateSort}
        />}

        {active !== "Дашборд" && active !== "Заявки" && active !== "Учні" && active !== "Групи" && active !== "Розклад" && active !== "Відвідування" && active !== "Оплати" && active !== "Працівники" && active !== "Локації" && active !== "Звіти" && <section className="panel placeholder">
          <p className="eyebrow">Наступний модуль</p>
          <h2>{active}</h2>
          <p>Каркас модуля вже передбачений у навігації. Реалізуємо після завершення наскрізного сценарію «заявка → пробне → група → учень».</p>
        </section>}
      </main>

      <LeadCreateDialog
        open={showLeadForm}
        leadChildName={leadChildName}
        leadChildLastName={leadChildLastName}
        leadChildPhone={leadChildPhone}
        leadAge={leadAge}
        leadContactName={leadContactName}
        leadPhone={leadPhone}
        leadSource={leadSource}
        leadComment={leadComment}
        duplicateChecking={leadDuplicateChecking}
        duplicateMatches={leadDuplicateMatches}
        setLeadChildName={setLeadChildName}
        setLeadChildLastName={setLeadChildLastName}
        setLeadChildPhone={setLeadChildPhone}
        setLeadAge={setLeadAge}
        setLeadContactName={setLeadContactName}
        setLeadPhone={setLeadPhone}
        setLeadSource={setLeadSource}
        setLeadComment={setLeadComment}
        onClose={() => { setShowLeadForm(false); setLeadDuplicateMatches([]); }}
        onCheckDuplicates={checkManualLeadDuplicates}
        onOpenDuplicate={openDuplicateStudent}
        onCreate={createManualLead}
      />

      <StaffDialogs
        showInviteForm={showInviteForm}
        inviteEmail={inviteEmail}
        inviteRole={inviteRole}
        inviteCanTeach={inviteCanTeach}
        inviteLink={inviteLink}
        setShowInviteForm={setShowInviteForm}
        setInviteEmail={setInviteEmail}
        setInviteRole={setInviteRole}
        setInviteCanTeach={setInviteCanTeach}
        onCreateInvitation={createInvitation}
        showStaffForm={showStaffForm}
        staffName={staffName}
        staffRole={staffRole}
        staffCanTeach={staffCanTeach}
        staffEmail={staffEmail}
        staffPhone={staffPhone}
        setShowStaffForm={setShowStaffForm}
        setStaffName={setStaffName}
        setStaffRole={setStaffRole}
        setStaffCanTeach={setStaffCanTeach}
        setStaffEmail={setStaffEmail}
        setStaffPhone={setStaffPhone}
        onCreateStaff={createStaffMember}
      />

      

      <LocationDialog
        open={showLocationForm}
        locationEditId={locationEditId}
        locationName={locationName}
        locationAddress={locationAddress}
        locationSaving={locationSaving}
        locationDeleteSaving={locationDeleteSaving}
        locationReturnToGroup={locationReturnToGroup}
        onClose={closeLocationForm}
        onNameChange={setLocationName}
        onAddressChange={setLocationAddress}
        onSave={saveLocationDemo}
        onDelete={deleteLocationDemo}
      />

      <GroupDetailDrawer
        groupId={selectedGroupId}
        selectedGroup={selectedGroup ?? undefined}
        groupDetail={groupDetail}
        groupDetailLoading={groupDetailLoading}
        apiEnabled={apiEnabled}
        leads={leads}
        payments={payments}
        activeLocations={activeLocations}
        activeTeachers={activeTeachers}
        teacherName={selectedGroup?.teacherName ?? selectedTeacher?.fullName}
        canEditGroups={canEditGroups}
        canManageStaff={canManageStaff}
        canManageLeads={canManageLeads}
        groupEditing={groupEditing}
        groupEditName={groupEditName}
        groupEditCapacity={groupEditCapacity}
        groupEditLocationId={groupEditLocationId}
        groupEditTeacherId={groupEditTeacherId}
        groupEditSchedule={groupEditSchedule}
        groupEditError={groupEditError}
        groupEditSaving={groupEditSaving}
        groupDeleteSaving={groupDeleteSaving}
        groupTeacherEditing={groupTeacherEditing}
        selectedGroupTeacherId={selectedGroupTeacherId}
        groupTeacherSaving={groupTeacherSaving}
        showGroupCandidatePicker={showGroupCandidatePicker}
        existingGroupCandidates={existingGroupCandidates}
        groupCandidateId={groupCandidateId}
        groupCandidateSaving={groupCandidateSaving}
        money={money}
        formatPhone={formatUaPhone}
        hasDuplicateSlots={hasDuplicateSlots}
        onClose={closeGroupDetail}
        onBeginEdit={beginGroupEdit}
        onEditNameChange={setGroupEditName}
        onEditCapacityChange={setGroupEditCapacity}
        onEditLocationChange={setGroupEditLocationId}
        onEditTeacherChange={setGroupEditTeacherId}
        onEditScheduleChange={setGroupEditSchedule}
        onClearEditError={() => setGroupEditError("")}
        onCancelEdit={() => { setGroupEditing(false); setGroupEditError(""); }}
        onSaveEdit={saveGroupEdit}
        onDelete={deleteSelectedGroup}
        onBeginTeacherEdit={() => { setSelectedGroupTeacherId(groupTeacher(selectedGroupId ?? "")?.id ?? ""); setGroupTeacherEditing(true); }}
        onSelectedTeacherChange={setSelectedGroupTeacherId}
        onCancelTeacherEdit={() => setGroupTeacherEditing(false)}
        onSaveTeacher={assignTeacherToSelectedGroup}
        onToggleCandidatePicker={() => { setShowGroupCandidatePicker((value) => !value); setGroupCandidateId(existingGroupCandidates[0]?.id ?? ""); }}
        onCloseCandidatePicker={() => { setShowGroupCandidatePicker(false); setGroupCandidateId(""); }}
        onAddCandidate={addCandidateToExistingGroup}
        onOpenStudent={(studentId) => {
          setSelectedStudentId(studentId);
          closeGroupDetail();
          if (apiEnabled) setActive("Учні");
        }}
        onOpenStudentAttendance={goToStudentAttendance}
        onOpenStudentPayments={goToStudentPayments}
      />

      {selectedStaff && <StaffDrawer
        staff={selectedStaff}
        locations={locations}
        groups={groups}
        apiEnabled={apiEnabled}
        resetLink={staffResetLink}
        onClose={() => setSelectedStaffId(null)}
        onToggleTeaching={async (next) => {
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
        }}
        onToggleLocation={(locationId) => toggleStaffLocation(selectedStaff.id, locationId)}
        onToggleGroup={(groupId) => toggleStaffGroup(selectedStaff.id, groupId)}
        onToggleActive={async () => {
          if (apiEnabled && session) {
            try {
              await apiPatch(`/staff/${selectedStaff.id}`, { is_active: !selectedStaff.isActive }, session);
              await syncWorkspace(session);
            } catch {
              return;
            }
            return;
          }
          setStaff((items) => items.map((item) => item.id === selectedStaff.id ? { ...item, isActive: !item.isActive } : item));
        }}
        onCreatePasswordReset={createStaffPasswordReset}
      />}

      <BillingDialogs
        plans={plans}
        subscriptions={subscriptions}
        activeStudents={activeStudents}
        money={money}
        paymentMinDate={localDateInput(new Date())}
        showPlanForm={showPlanForm}
        planEditId={planEditId}
        planName={planName}
        planPrice={planPrice}
        planDays={planDays}
        planLessons={planLessons}
        planActive={planActive}
        planSaving={planSaving}
        planHistory={planHistory}
        planHistoryLoading={planHistoryLoading}
        planHistoryOpen={planHistoryOpen}
        tariffHistoryDetail={tariffHistoryDetail}
        onClosePlanForm={() => { setShowPlanForm(false); setPlanEditId(null); }}
        onPlanNameChange={setPlanName}
        onPlanPriceChange={setPlanPrice}
        onPlanDaysChange={setPlanDays}
        onPlanLessonsChange={setPlanLessons}
        onPlanActiveChange={setPlanActive}
        onSavePlan={savePlan}
        onTogglePlanHistory={() => planHistoryOpen ? setPlanHistoryOpen(false) : void loadPlanHistory()}
        showPaymentForm={showPaymentForm}
        paymentStudentId={paymentStudentId}
        paymentPlanId={paymentPlanId}
        paymentDueDate={paymentDueDate}
        paymentAutoRenew={paymentAutoRenew}
        paymentSaving={paymentSaving}
        onClosePaymentForm={() => setShowPaymentForm(false)}
        onPaymentStudentChange={setPaymentStudentId}
        onPaymentPlanChange={setPaymentPlanId}
        onPaymentDueDateChange={setPaymentDueDate}
        onPaymentAutoRenewChange={setPaymentAutoRenew}
        onCreatePayment={createPayment}
        paymentActionId={paymentActionId}
        paymentActionType={paymentActionType}
        paymentActionAmount={paymentActionAmount}
        paymentActionReason={paymentActionReason}
        paymentActionMethod={paymentActionMethod}
        paymentAdjustmentDirection={paymentAdjustmentDirection}
        paymentActionSaving={paymentActionSaving}
        onClosePaymentAction={() => { setPaymentActionId(null); setPaymentActionType(null); }}
        onPaymentActionAmountChange={setPaymentActionAmount}
        onPaymentActionReasonChange={setPaymentActionReason}
        onPaymentActionMethodChange={setPaymentActionMethod}
        onPaymentAdjustmentDirectionChange={setPaymentAdjustmentDirection}
        onSubmitPaymentAction={submitPaymentAction}
        planChangeSubscriptionId={planChangeSubscriptionId}
        planChangePlanId={planChangePlanId}
        planChangeReason={planChangeReason}
        planChangeSaving={planChangeSaving}
        planChangeResult={planChangeResult}
        onClosePlanChange={() => { setPlanChangeSubscriptionId(null); setPlanChangeResult(""); }}
        onPlanChangePlanIdChange={setPlanChangePlanId}
        onPlanChangeReasonChange={setPlanChangeReason}
        onSubmitPlanChange={submitPlanChange}
        pauseSubscriptionId={pauseSubscriptionId}
        pauseStart={pauseStart}
        pauseResumeOn={pauseResumeOn}
        pauseNote={pauseNote}
        onClosePause={() => setPauseSubscriptionId(null)}
        onPauseStartChange={setPauseStart}
        onPauseResumeOnChange={setPauseResumeOn}
        onPauseNoteChange={setPauseNote}
        onSubmitPause={submitPauseSubscription}
      />

      <StudentDrawer
        student={selectedStudent}
        currentGroup={selectedStudent ? studentGroup(selectedStudent.id) : undefined}
        studentState={selectedStudent ? (studentStates[selectedStudent.id] ?? "Активний") : "Активний"}
        canManageStudents={canManageStudents}
        canDeleteStudents={canDeleteStudents}
        transferGroupId={transferGroupId}
        groups={groups}
        deleting={studentDeleteSaving}
        apiEnabled={apiEnabled}
        auditEvents={entityEvents}
        historyLoading={historyLoading}
        onClose={() => setSelectedStudentId(null)}
        onLifecycleChange={(state) => { if (selectedStudent) void setStudentLifecycle(selectedStudent.id, state); }}
        onTransferGroupChange={setTransferGroupId}
        onTransfer={() => { void transferStudent(); }}
        onDelete={() => { void deleteSelectedStudent(); }}
        auditEventLabel={auditEventLabel}
        auditEventDetail={auditEventDetail}
      />

      <GroupCreateDialog
        open={showGroupForm}
        groupName={groupName}
        groupCapacity={groupCapacity}
        groupLocationId={groupLocationId}
        newGroupTeacherId={newGroupTeacherId}
        groupSchedule={groupSchedule}
        groupCreateError={groupCreateError}
        selectedCandidates={selectedCandidates}
        leads={leads}
        activeLocations={activeLocations}
        activeTeachers={activeTeachers}
        canManageStaff={canManageStaff}
        setOpen={setShowGroupForm}
        setGroupName={setGroupName}
        setGroupCapacity={setGroupCapacity}
        setGroupLocationId={setGroupLocationId}
        setNewGroupTeacherId={setNewGroupTeacherId}
        setGroupSchedule={setGroupSchedule}
        setGroupCreateError={setGroupCreateError}
        onCreateLocation={createLocationFromGroup}
        onCreateGroup={createGroupFromCandidates}
      />

      {selected && <LeadDrawer {...{
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
      }} />}
    </div>
  );
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


function formatMoney(value: number, locale = "uk-UA", currency = "UAH") {
  return new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}



export default App;
