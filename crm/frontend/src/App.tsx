import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { acceptInvite, apiDelete, apiEnabled, apiPatch, apiPost, apiPut, bootstrapOwner, changeOrganization, clearSession, getBootstrapStatus, loadAttendance, loadAuditEvents, loadOperations, loadOverviewReport, loadSession, loadTeaching, loadWorkspace, login, refreshMe, type ApiAuditEvent, type OperationsBundle, type OverviewReport, type Session, type TeachingBundle, type WorkspaceBundle } from "./api";

type LeadStatus = "Нова" | "Зв'язались" | "Пробне заплановано" | "Пробне пройдено" | "Очікує групу" | "Зарахований";

type EntityId = string;

type AvailabilitySlot = {
  weekday: number;
  start_time: string;
  end_time: string;
};

type Lead = {
  id: EntityId;
  child: string;
  age: number;
  parent: string;
  phone: string;
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
  trialResult?: "scheduled" | "completed" | "no_show";
  recommendedLevel?: string;
  teacherNotes?: string;
};

type GroupItem = {
  id: EntityId;
  name: string;
  ages: string;
  schedule: string;
  location: string;
  capacity: number;
  members: EntityId[];
};

type AttendanceValue = "present" | "absent" | "late" | "excused";

type LessonItem = {
  id: EntityId;
  groupId: EntityId;
  startsAt: string;
  duration: number;
  topic: string;
  status?: "scheduled" | "completed" | "cancelled";
};

type PlanDemo = {
  id: EntityId;
  name: string;
  price: number;
  lessons: number | null;
};

type PaymentDemo = {
  id: EntityId;
  studentId: EntityId;
  planId: EntityId;
  amount: number;
  dueDate: string;
  status: "pending" | "paid" | "overdue";
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

const statuses: LeadStatus[] = ["Нова", "Зв'язались", "Пробне заплановано", "Пробне пройдено", "Очікує групу", "Зарахований"];

function App() {
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
  const [leadFilter, setLeadFilter] = useState<"all" | "new" | "trial" | "waiting">("all");
  const [studentFilter, setStudentFilter] = useState<"all" | "active" | "paused" | "archived">("all");
  const [candidateFilter, setCandidateFilter] = useState<"all" | "8-10" | "11-13" | "beginner">("all");
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadChildName, setLeadChildName] = useState("");
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
  const [selectedLessonId, setSelectedLessonId] = useState<EntityId>("1");
  const [attendance, setAttendance] = useState<Record<EntityId, Record<EntityId, AttendanceValue>>>({
    "1": { "8": "present", "9": "late" },
  });
  const [attendanceLoading, setAttendanceLoading] = useState(false);
  const [attendanceSaving, setAttendanceSaving] = useState(false);
  const [plans, setPlans] = useState<PlanDemo[]>([
    { id: "1", name: "8 занять / 30 днів", price: 1800, lessons: 8 },
    { id: "2", name: "Індивідуальний", price: 0, lessons: null },
  ]);
  const [payments, setPayments] = useState<PaymentDemo[]>([
    { id: "1", studentId: "8", planId: "1", amount: 1800, dueDate: "2026-10-05", status: "pending" },
    { id: "2", studentId: "9", planId: "1", amount: 1800, dueDate: "2026-09-28", status: "paid", method: "Картка" },
  ]);
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [paymentStudentId, setPaymentStudentId] = useState<EntityId>("8");
  const [paymentPlanId, setPaymentPlanId] = useState<EntityId>("1");
  const [paymentDueDate, setPaymentDueDate] = useState("2026-10-31");
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [planName, setPlanName] = useState("8 занять / 30 днів");
  const [planPrice, setPlanPrice] = useState(1800);
  const [planLessons, setPlanLessons] = useState(8);
  const [locations, setLocations] = useState<LocationDemo[]>([
    { id: "1", name: "Основна локація", address: "Івано-Франківськ", isActive: true },
  ]);
  const [staff, setStaff] = useState<StaffDemo[]>([
    { id: "1", fullName: "Іван Викладач", role: "Викладач", email: "ivan@aerokids.example", phone: "+380 67 111 22 33", locationIds: ["1"], groupIds: ["1"], isActive: true },
    { id: "2", fullName: "Адміністратор AeroKiDS", role: "Адміністратор", email: "admin@aerokids.example", phone: "+380 67 444 55 66", locationIds: ["1"], groupIds: [], isActive: true },
  ]);
  const [selectedStaffId, setSelectedStaffId] = useState<EntityId | null>(null);
  const [showStaffForm, setShowStaffForm] = useState(false);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<StaffRoleDemo>("Викладач");
  const [inviteLink, setInviteLink] = useState("");
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
  const [preferenceMode, setPreferenceMode] = useState(false);
  const [preferenceLocationId, setPreferenceLocationId] = useState<EntityId | "">("");
  const [availabilityDays, setAvailabilityDays] = useState<number[]>([]);
  const [availabilityStart, setAvailabilityStart] = useState("16:00");
  const [availabilityEnd, setAvailabilityEnd] = useState("20:00");
  const [preferenceSaving, setPreferenceSaving] = useState(false);
  const [trialAt, setTrialAt] = useState("2026-10-05T17:00");
  const [trialLocation, setTrialLocation] = useState("Основна локація");
  const [trialLocationId, setTrialLocationId] = useState<EntityId | "">("");
  const [recommendedLevel, setRecommendedLevel] = useState("Початковий");
  const [teacherNotes, setTeacherNotes] = useState("");
  const [selectedCandidates, setSelectedCandidates] = useState<EntityId[]>([]);
  const [groupName, setGroupName] = useState("FPV Start 8–10");
  const [groupSchedule, setGroupSchedule] = useState("Пн / Ср · 17:00");
  const [groupCapacity, setGroupCapacity] = useState(8);
  const [groupLocationId, setGroupLocationId] = useState<EntityId | "">("");
  const [showGroupForm, setShowGroupForm] = useState(false);
  const [newLessonGroupId, setNewLessonGroupId] = useState<EntityId>("1");
  const [newLessonAt, setNewLessonAt] = useState("2026-10-07T17:00");
  const [newLessonTopic, setNewLessonTopic] = useState("FPV / електроніка");
  const [scheduleGroupId, setScheduleGroupId] = useState<EntityId>("1");
  const [scheduleWeekday, setScheduleWeekday] = useState(0);
  const [scheduleTime, setScheduleTime] = useState("17:00");
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
      const [bundle, operations, teaching, report] = await Promise.all([
        loadWorkspace(currentSession),
        loadOperations(currentSession),
        loadTeaching(currentSession),
        loadOverviewReport(currentSession),
      ]);
      applyWorkspace(bundle, setLeads, setGroups, setStudentStates);
      applyOperations(operations, setLocations, setStaff, setPlans, setPayments);
      if (!trialLocationId && operations.locations[0]) setTrialLocationId(operations.locations[0].id);
      if (!groupLocationId && operations.locations[0]) setGroupLocationId(operations.locations[0].id);
      applyTeaching(teaching, setLessons, setGroups);
      setOverviewReport(report);
      setSelectedLessonId((current) => teaching.lessons.some((item) => item.id === current) ? current : (teaching.lessons[0]?.id ?? ""));
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
    if (leadFilter === "new") return leads.filter((item) => item.status === "Нова");
    if (leadFilter === "trial") return leads.filter((item) => item.status === "Пробне заплановано");
    if (leadFilter === "waiting") return leads.filter((item) => item.status === "Очікує групу");
    return leads;
  }, [leads, leadFilter]);

  const visibleStudents = useMemo(() => activeStudents.filter((item) => {
    const state = studentStates[item.id] ?? "Активний";
    if (studentFilter === "active") return state === "Активний";
    if (studentFilter === "paused") return state === "Пауза";
    if (studentFilter === "archived") return state === "Архів";
    return true;
  }), [activeStudents, studentStates, studentFilter]);

  const visibleWaiting = useMemo(() => waiting.filter((item) => {
    if (candidateFilter === "8-10") return item.age >= 8 && item.age <= 10;
    if (candidateFilter === "11-13") return item.age >= 11 && item.age <= 13;
    if (candidateFilter === "beginner") return item.recommendedLevel === "Початковий";
    return true;
  }), [waiting, candidateFilter]);

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
    if (!leadChildName.trim() || !leadContactName.trim() || !leadPhone.trim()) return;
    if (apiEnabled && session) {
      try {
        await apiPost("/intake", {
          child_first_name: leadChildName.trim(),
          child_age: leadAge,
          contact_name: leadContactName.trim(),
          phone: leadPhone.trim(),
          source: leadSource,
          comment: leadComment.trim() || null,
        }, session);
        await syncWorkspace(session);
        setShowLeadForm(false);
        setActive("Заявки");
        setLeadChildName("");
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
      child: leadChildName.trim(),
      age: leadAge,
      parent: leadContactName.trim(),
      phone: leadPhone.trim(),
      source: leadSource,
      status: "Нова",
      comment: leadComment.trim() || undefined,
    }, ...items]);
    setShowLeadForm(false);
    setActive("Заявки");
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
        setTrialMode(null);
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

  const completeTrial = async (result: "completed" | "no_show") => {
    if (!selected) return;
    if (apiEnabled && session && selected.trialId) {
      try {
        await apiPatch(`/trial-lessons/${selected.trialId}/complete`, {
          status: result,
          recommended_level: result === "completed" ? recommendedLevel : null,
          teacher_notes: teacherNotes || null,
        }, session);
        await syncWorkspace(session);
        setTrialMode(null);
        return;
      } catch {
        return;
      }
    }
    setLeads((items) => items.map((item) => item.id === selected.id ? {
      ...item,
      status: result === "completed" ? "Очікує групу" : "Зв'язались",
      trialResult: result,
      recommendedLevel: result === "completed" ? recommendedLevel : item.recommendedLevel,
      teacherNotes: teacherNotes || item.teacherNotes,
    } : item));
    setTrialMode(null);
  };

  const openLead = (id: EntityId) => {
    setSelectedId(id);
    setTrialMode(null);
    setPreferenceMode(false);
    const lead = leads.find((item) => item.id === id);
    if (lead?.trialAt) setTrialAt(toLocalDateTimeInput(lead.trialAt));
    if (lead?.trialLocation) setTrialLocation(lead.trialLocation);
    if (lead?.trialLocationId) setTrialLocationId(lead.trialLocationId);
    if (lead?.recommendedLevel) setRecommendedLevel(lead.recommendedLevel);
    setTeacherNotes(lead?.teacherNotes ?? "");
    setPreferenceLocationId(lead?.preferredLocationId ?? "");
    setAvailabilityDays(Array.from(new Set((lead?.availability ?? []).map((slot) => slot.weekday))));
    setAvailabilityStart(lead?.availability?.[0]?.start_time ?? "16:00");
    setAvailabilityEnd(lead?.availability?.[0]?.end_time ?? "20:00");
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
        availability: availabilityDays.map((weekday) => ({
          weekday,
          start_time: availabilityStart,
          end_time: availabilityEnd,
        })),
      }, session);
      await syncWorkspace(session);
      setPreferenceMode(false);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Не вдалося зберегти бажаний графік");
    } finally {
      setPreferenceSaving(false);
    }
  };

  const toggleAvailabilityDay = (weekday: number) => {
    setAvailabilityDays((days) => days.includes(weekday) ? days.filter((day) => day !== weekday) : [...days, weekday].sort());
  };

  const createGroupFromCandidates = async () => {
    if (!selectedCandidates.length || !groupName.trim()) return;
    const selectedLeadRows = leads.filter((x) => selectedCandidates.includes(x.id));
    if (apiEnabled && session) {
      try {
        await apiPost("/groups/form", {
          name: groupName.trim(),
          capacity: groupCapacity,
          location_id: groupLocationId || null,
          min_age: selectedLeadRows.length ? Math.min(...selectedLeadRows.map((x) => x.age)) : null,
          max_age: selectedLeadRows.length ? Math.max(...selectedLeadRows.map((x) => x.age)) : null,
          student_ids: selectedCandidates,
          schedule_slots: parseScheduleText(groupSchedule),
        }, session);
        await syncWorkspace(session);
        setSelectedCandidates([]);
        setShowGroupForm(false);
        return;
      } catch {
        return;
      }
    }
    const nextId = crypto.randomUUID();
    setGroups((items) => [...items, {
      id: nextId,
      name: groupName.trim(),
      ages: selectedCandidates.length ? ageRange(selectedLeadRows) : "—",
      schedule: groupSchedule,
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

  const selectedLesson = lessons.find((lesson) => lesson.id === selectedLessonId) ?? lessons[0];
  const lessonGroup = selectedLesson ? groups.find((group) => group.id === selectedLesson.groupId) : undefined;
  const lessonStudents = lessonGroup ? leads.filter((lead) => lessonGroup.members.includes(lead.id)) : [];

  useEffect(() => {
    if (!apiEnabled || !session || !selectedLesson?.id) return;
    let cancelled = false;
    setAttendanceLoading(true);
    loadAttendance(selectedLesson.id, session)
      .then((rows) => {
        if (cancelled) return;
        const mapped: Record<EntityId, AttendanceValue> = {};
        rows.forEach((row) => { mapped[row.student_id] = row.status; });
        setAttendance((all) => ({ ...all, [selectedLesson.id]: mapped }));
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

  const markAllPresent = () => {
    if (!selectedLesson) return;
    const next: Record<EntityId, AttendanceValue> = {};
    lessonStudents.forEach((student) => { next[student.id] = "present"; });
    setAttendance((all) => ({ ...all, [selectedLesson.id]: next }));
  };

  const createGroupSchedule = async () => {
    if (!scheduleGroupId) return;
    if (apiEnabled && session) {
      try {
        await apiPost("/group-schedules", {
          group_id: scheduleGroupId,
          weekday: scheduleWeekday,
          start_time: scheduleTime,
          duration_minutes: 60,
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
          duration_minutes: 60,
          topic: newLessonTopic.trim() || "Заняття",
        }, session);
        await syncWorkspace(session);
        setSelectedLessonId(created.id);
        setActive("Відвідування");
        return;
      } catch {
        return;
      }
    }
    const nextId = crypto.randomUUID();
    setLessons((items) => [...items, {
      id: nextId,
      groupId: newLessonGroupId,
      startsAt: newLessonAt,
      duration: 60,
      topic: newLessonTopic.trim() || "Заняття",
    }]);
    setSelectedLessonId(nextId);
    setActive("Відвідування");
  };

  const saveAttendance = async () => {
    if (!selectedLesson) return;
    const lessonMarks = attendance[selectedLesson.id] ?? {};
    if (apiEnabled && session) {
      setAttendanceSaving(true);
      try {
        await apiPut(`/lesson-sessions/${selectedLesson.id}/attendance`, {
          items: lessonStudents.map((student) => ({
            student_id: student.id,
            status: lessonMarks[student.id] ?? "present",
          })),
        }, session);
        await syncWorkspace(session);
      } catch {
        return;
      } finally {
        setAttendanceSaving(false);
      }
      return;
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

  const createPayment = async () => {
    const plan = plans.find((item) => item.id === paymentPlanId);
    if (!plan || plan.price <= 0) {
      setWorkspaceError("Для нарахування оберіть абонемент із заданою ціною.");
      return;
    }
    if (apiEnabled && session) {
      try {
        const subscription = await apiPost<{ id: string }>("/student-subscriptions", {
          student_id: paymentStudentId,
          plan_id: paymentPlanId,
          starts_on: new Date().toISOString().slice(0, 10),
          discount_minor: 0,
        }, session);
        await apiPost("/payments", {
          student_id: paymentStudentId,
          subscription_id: subscription.id,
          amount_minor: Math.round(plan.price * 100),
          due_date: paymentDueDate || null,
          note: plan.name,
        }, session);
        await syncWorkspace(session);
        setShowPaymentForm(false);
        return;
      } catch {
        return;
      }
    }
    const nextId = crypto.randomUUID();
    setPayments((items) => [...items, {
      id: nextId,
      studentId: paymentStudentId,
      planId: paymentPlanId,
      amount: plan.price,
      dueDate: paymentDueDate,
      status: "pending",
    }]);
    setShowPaymentForm(false);
  };

  const createPlan = async () => {
    if (!planName.trim() || planPrice < 0) return;
    if (apiEnabled && session) {
      try {
        await apiPost("/subscription-plans", {
          name: planName.trim(),
          price_minor: Math.round(planPrice * 100),
          period_days: 30,
          lessons_included: planLessons > 0 ? planLessons : null,
        }, session);
        await syncWorkspace(session);
        setShowPlanForm(false);
        return;
      } catch {
        return;
      }
    }
    setPlans((items) => [...items, {
      id: crypto.randomUUID(),
      name: planName.trim(),
      price: planPrice,
      lessons: planLessons > 0 ? planLessons : null,
    }]);
    setShowPlanForm(false);
  };

  const paymentTotals = {
    paid: payments.filter((x) => x.status === "paid").reduce((sum, x) => sum + x.amount, 0),
    pending: payments.filter((x) => x.status === "pending").reduce((sum, x) => sum + x.amount, 0),
    overdue: payments.filter((x) => x.status === "overdue").reduce((sum, x) => sum + x.amount, 0),
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

  const createStaffMember = async () => {
    if (!staffName.trim()) return;
    if (apiEnabled && session) {
      try {
        await apiPost("/staff", {
          full_name: staffName.trim(),
          role: staffRoleValue(staffRole),
          email: staffEmail.trim() || null,
          phone: staffPhone.trim() || null,
          location_ids: locations[0] ? [locations[0].id] : [],
        }, session);
        await syncWorkspace(session);
        setStaffName("");
        setStaffEmail("");
        setStaffPhone("");
        setShowStaffForm(false);
        return;
      } catch {
        return;
      }
    }
    const nextId = crypto.randomUUID();
    setStaff((items) => [...items, {
      id: nextId,
      fullName: staffName.trim(),
      role: staffRole,
      email: staffEmail.trim(),
      phone: staffPhone.trim(),
      locationIds: locations[0] ? [locations[0].id] : [],
      groupIds: [],
      isActive: true,
    }]);
    setStaffName("");
    setStaffEmail("");
    setStaffPhone("");
    setShowStaffForm(false);
  };

  const createInvitation = async () => {
    if (!session || !inviteEmail.trim()) return;
    try {
      const result = await apiPost<{ invite_token: string }>("/organization-invitations", {
        email: inviteEmail.trim(),
        role: staffRoleValue(inviteRole),
      }, session);
      const url = new URL(window.location.href);
      url.searchParams.set("invite", result.invite_token);
      setInviteLink(url.toString());
    } catch {
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
    ? `${currentMembership?.organization_name ?? "School CRM"} · ${locations[0].name}`
    : currentMembership?.organization_name ?? "School CRM";
  const navigation = visibleNavigation(currentMembership?.role);
  const canManageRecurringSchedule = !apiEnabled || ["owner", "admin", "manager"].includes(currentMembership?.role ?? "");
  const canManageLeads = !apiEnabled || ["owner", "admin", "manager"].includes(currentMembership?.role ?? "");
  const canManageStudents = !apiEnabled || ["owner", "admin", "manager"].includes(currentMembership?.role ?? "");
  const canManageLocations = !apiEnabled || ["owner", "admin"].includes(currentMembership?.role ?? "");
  const searchTerm = searchQuery.trim().toLocaleLowerCase("uk-UA");
  const searchLeads = searchTerm ? leads.filter((item) =>
    [item.child, item.parent, item.phone, item.source].some((value) => value.toLocaleLowerCase("uk-UA").includes(searchTerm))
  ).slice(0, 8) : [];
  const searchGroups = searchTerm ? groups.filter((item) =>
    [item.name, item.ages, item.location].some((value) => value.toLocaleLowerCase("uk-UA").includes(searchTerm))
  ).slice(0, 5) : [];
  const searchStaff = searchTerm ? staff.filter((item) =>
    [item.fullName, item.email, item.phone, item.role].some((value) => value.toLocaleLowerCase("uk-UA").includes(searchTerm))
  ).slice(0, 5) : [];

  return (
    <div className="shell">
      <aside>
        <div className="brand"><span className="mark">✦</span><div><b>School CRM</b><small>{currentMembership?.organization_name ?? "AeroKiDS · demo tenant"}</small></div></div>
        <nav>{navigation.map((item) => <button onClick={() => {
          if (item === "Налаштування" && currentMembership) {
            setOrganizationName(currentMembership.organization_name);
            setOrganizationTimezone(currentMembership.organization_timezone);
            setOrganizationCurrency(currentMembership.organization_currency);
            setOrganizationLocale(currentMembership.organization_locale);
          }
          setActive(item);
        }} className={active === item ? "active" : ""} key={item}>{item}</button>)}</nav>
        <div className="asideFooter">MVP 1 · crm-v1</div>
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

        {active === "Дашборд" && <>
          <section className="stats">
            <article><span>Нові заявки</span><strong>{stats.newLeads}</strong><small>потребують першого контакту</small></article>
            <article><span>Пробні заплановано</span><strong>{stats.trial}</strong><small>найближчі записи</small></article>
            <article><span>Очікують групу</span><strong>{stats.waiting}</strong><small>кандидати до формування</small></article>
            <article><span>Зараховані</span><strong>{stats.activeStudents}</strong><small>у сформованих групах</small></article>
          </section>
          <section className="grid">
            <article className="panel wide">
              <div className="panelHead"><div><p className="eyebrow">Потрібно опрацювати</p><h2>Останні заявки</h2></div><button className="link" onClick={() => setActive("Заявки")}>Усі заявки →</button></div>
              <LeadTable leads={leads.slice(0, 5)} onOpen={openLead} />
            </article>
            <article className="panel">
              <p className="eyebrow">Сьогодні</p><h2>Пробні заняття</h2>
              <div className="timeline">
                {upcomingTrials.length === 0 && <div className="emptyState">Запланованих пробних поки немає.</div>}
                {upcomingTrials.map((lead) => <button className="timelineButton" key={lead.id} onClick={() => openLead(lead.id)}>
                  <time>{new Date(lead.trialAt!).toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })}<small>{new Date(lead.trialAt!).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</small></time>
                  <p><b>{lead.child}</b><span>{lead.parent}{lead.trialLocation ? " · " + lead.trialLocation : ""}</span></p>
                </button>)}
              </div>
            </article>
            <article className="panel">
              <p className="eyebrow">Формування груп</p><h2>Очікують групу</h2>
              <div className="suggestion"><strong>{waiting.length} дітей</strong><span>відфільтруйте за віком і рівнем</span><button className="primary" onClick={() => setActive("Групи")}>Сформувати групу</button></div>
            </article>
          </section>
        </>}

        {active === "Заявки" && <section className="panel leadsPage">
          <div className="panelHead">
            <div><p className="eyebrow">Воронка</p><h2>Заявки та пробні</h2></div>
            <div className="filters">
              <button className={"chip " + (leadFilter === "all" ? "active" : "")} onClick={() => setLeadFilter("all")}>Усі</button>
              <button className={"chip " + (leadFilter === "new" ? "active" : "")} onClick={() => setLeadFilter("new")}>Нові</button>
              <button className={"chip " + (leadFilter === "trial" ? "active" : "")} onClick={() => setLeadFilter("trial")}>Пробні</button>
              <button className={"chip " + (leadFilter === "waiting" ? "active" : "")} onClick={() => setLeadFilter("waiting")}>Очікують групу</button>
            </div>
          </div>
          <LeadTable leads={visibleLeads} onOpen={openLead} />
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
            <div className="panelHead"><div><p className="eyebrow">Тиждень</p><h2>Розклад груп</h2></div><span className="counter">{groups.length}</span></div>
            <div className="weekGrid">
              {["Пн","Вт","Ср","Чт","Пт","Сб"].map((day) => <div className="dayColumn" key={day}>
                <b>{day}</b>
                {groups.flatMap((group) => scheduleSlots(group).filter((slot) => slot.day === day).map((slot) =>
                  <button className="scheduleCard" key={group.id + day} onClick={() => setActive("Групи")}>
                    <time>{slot.time}</time><strong>{group.name}</strong><span>{group.location}</span><small>{group.members.length}/{group.capacity} учнів</small>
                  </button>
                ))}
              </div>)}
            </div>
          </article>
          <aside className="scheduleSide">
            {canManageRecurringSchedule && <article className="panel lessonCreate">
              <p className="eyebrow">Регулярний розклад</p><h2>Додати слот</h2>
              <label>Група<select value={scheduleGroupId} onChange={(e) => setScheduleGroupId(e.target.value)}>{groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label>
              <div className="formTwo">
                <label>День<select value={scheduleWeekday} onChange={(e) => setScheduleWeekday(Number(e.target.value))}>{["Пн","Вт","Ср","Чт","Пт","Сб","Нд"].map((day,index) => <option value={index} key={day}>{day}</option>)}</select></label>
                <label>Час<input type="time" value={scheduleTime} onChange={(e) => setScheduleTime(e.target.value)} /></label>
              </div>
              <button className="search full" onClick={createGroupSchedule}>Додати в розклад</button>
            </article>}
            <article className="panel lessonCreate">
              <p className="eyebrow">Нове заняття</p><h2>Додати заняття</h2>
              <label>Група<select value={newLessonGroupId} onChange={(e) => setNewLessonGroupId(e.target.value)}>{groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label>
              <label>Дата і час<input type="datetime-local" value={newLessonAt} onChange={(e) => setNewLessonAt(e.target.value)} /></label>
              <label>Тема<input value={newLessonTopic} onChange={(e) => setNewLessonTopic(e.target.value)} /></label>
              <button className="primary full" onClick={createLesson}>Створити заняття</button>
            </article>
          </aside>
        </section>}

        {active === "Відвідування" && <section className="attendanceLayout">
          <article className="panel lessonListPanel">
            <div className="panelHead"><div><p className="eyebrow">Заняття</p><h2>Журнал</h2></div><span className="counter">{lessons.length}</span></div>
            <div className="lessonList">
              {lessons.map((lesson) => {
                const group = groups.find((g) => g.id === lesson.groupId);
                const marked = Object.keys(attendance[lesson.id] ?? {}).length;
                return <button className={"lessonRow " + (lesson.id === selectedLessonId ? "active" : "")} key={lesson.id} onClick={() => setSelectedLessonId(lesson.id)}>
                  <time>{new Date(lesson.startsAt).toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })}<small>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</small></time>
                  <span><b>{group?.name ?? "Група"}</b><small>{lesson.topic}</small></span>
                  <i>{marked}/{group?.members.length ?? 0}</i>
                </button>;
              })}
            </div>
          </article>
          <article className="panel attendancePanel">
            {selectedLesson && <>
              <div className="panelHead"><div><p className="eyebrow">Відвідування</p><h2>{lessonGroup?.name}</h2><p className="lessonMeta">{new Date(selectedLesson.startsAt).toLocaleString("uk-UA")} · {selectedLesson.duration} хв</p></div><button className="search" onClick={markAllPresent}>Усі присутні</button></div>
              <div className="topicBox"><span>Тема заняття</span><b>{selectedLesson.topic}</b></div>
              <div className="attendanceTable">
                {lessonStudents.map((student) => {
                  const value = attendance[selectedLesson.id]?.[student.id] ?? "present";
                  return <div className="attendanceRow" key={student.id}>
                    <span className="studentIdentity"><i>{student.child[0]}</i><b>{student.child}<small>{student.age} років</small></b></span>
                    <div className="attendanceButtons">
                      <button className={value === "present" ? "active present" : ""} onClick={() => markAttendance(student.id, "present")}>✓ Був</button>
                      <button className={value === "late" ? "active late" : ""} onClick={() => markAttendance(student.id, "late")}>Запізнився</button>
                      <button className={value === "absent" ? "active absent" : ""} onClick={() => markAttendance(student.id, "absent")}>Відсутній</button>
                      <button className={value === "excused" ? "active excused" : ""} onClick={() => markAttendance(student.id, "excused")}>Поважна</button>
                    </div>
                  </div>;
                })}
                {lessonStudents.length === 0 && <div className="emptyState">У цій групі поки немає активних учнів.</div>}
              </div>
              <div className="attendanceFooter"><span>{attendanceLoading ? "Завантажуємо…" : <>Позначено: <b>{Object.keys(attendance[selectedLesson.id] ?? {}).length}/{lessonStudents.length}</b></>}</span><button className="primary" disabled={attendanceSaving || attendanceLoading} onClick={saveAttendance}>{attendanceSaving ? "Зберігаємо…" : "Зберегти відвідування"}</button></div>
            </>}
          </article>
        </section>}

        {active === "Оплати" && <section className="paymentsLayout">
          <div className="paymentsMain">
            <section className="paymentStats">
              <article><span>Сплачено</span><strong>{money(paymentTotals.paid)}</strong><small>{payments.filter((x) => x.status === "paid").length} платежів</small></article>
              <article><span>Очікується</span><strong>{money(paymentTotals.pending)}</strong><small>{payments.filter((x) => x.status === "pending").length} рахунків</small></article>
              <article><span>Прострочено</span><strong>{money(paymentTotals.overdue)}</strong><small>{payments.filter((x) => x.status === "overdue").length} боргів</small></article>
            </section>
            <article className="panel paymentsPanel">
              <div className="panelHead"><div><p className="eyebrow">Фінанси</p><h2>Оплати учнів</h2></div><button className="primary" onClick={() => setShowPaymentForm(true)}>+ Нарахування</button></div>
              <div className="paymentTable">
                <div className="paymentRow paymentHead"><span>Учень</span><span>Абонемент</span><span>Сума</span><span>До дати</span><span>Статус</span><span></span></div>
                {payments.map((payment) => {
                  const student = leads.find((lead) => lead.id === payment.studentId);
                  const plan = plans.find((item) => item.id === payment.planId);
                  return <div className="paymentRow" key={payment.id}>
                    <span><b>{student?.child ?? "Учень"}</b><small>{student?.parent}</small></span>
                    <span>{plan?.name ?? "—"}</span>
                    <span><b>{money(payment.amount)}</b></span>
                    <span>{new Date(payment.dueDate).toLocaleDateString("uk-UA")}</span>
                    <span className={"paymentStatus " + payment.status}>{payment.status === "paid" ? "Сплачено" : payment.status === "overdue" ? "Прострочено" : "Очікується"}</span>
                    <span>{payment.status !== "paid" ? <button className="link payAction" onClick={() => markPaymentPaid(payment.id)}>Позначити сплачено</button> : <small>{payment.method}</small>}</span>
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

                {active === "Групи" && <section className="groupsLayout">
          <article className="panel">
            <div className="panelHead"><div><p className="eyebrow">Waiting list</p><h2>Очікують групу</h2></div><span className="counter">{waiting.length}</span></div>
            <div className="candidateFilters">
              <button className={"chip " + (candidateFilter === "all" ? "active" : "")} onClick={() => setCandidateFilter("all")}>Усі</button>
              <button className={"chip " + (candidateFilter === "8-10" ? "active" : "")} onClick={() => setCandidateFilter("8-10")}>8–10 років</button>
              <button className={"chip " + (candidateFilter === "11-13" ? "active" : "")} onClick={() => setCandidateFilter("11-13")}>11–13 років</button>
              <button className={"chip " + (candidateFilter === "beginner" ? "active" : "")} onClick={() => setCandidateFilter("beginner")}>Початковий</button>
            </div>
            <div className="candidateList">
              {visibleWaiting.length === 0 && <div className="emptyState">За цим фільтром кандидатів немає.</div>}
              {visibleWaiting.map((lead) => <label className={"candidate " + (selectedCandidates.includes(lead.id) ? "selected" : "")} key={lead.id}>
                <input type="checkbox" checked={selectedCandidates.includes(lead.id)} onChange={() => toggleCandidate(lead.id)} />
                <span className="candidateAvatar">{lead.child[0]}</span>
                <span className="candidateMain"><b>{lead.child}</b><small>{lead.age} років · {lead.recommendedLevel ?? "Рівень не вказано"}</small><small>{availabilityLabel(lead.availability ?? [])}{lead.preferredLocationName ? " · " + lead.preferredLocationName : ""}</small></span>
                <span className="candidateSource">{lead.source}</span>
              </label>)}
            </div>
            <div className="selectionBar">
              <span>Вибрано: <b>{selectedCandidates.length}</b></span>
              <button className="primary" disabled={!selectedCandidates.length} onClick={() => setShowGroupForm(true)}>Створити групу</button>
            </div>
          </article>

          <div className="groupsSide">
            <article className="panel">
              <p className="eyebrow">Підказка CRM</p>
              <h2>Схожі кандидати</h2>
              <div className="suggestion compact"><strong>{waiting.filter((x) => x.age >= 8 && x.age <= 10 && x.recommendedLevel === "Початковий").length}</strong><span>8–10 років · початковий</span><button className="link" onClick={() => setSelectedCandidates(waiting.filter((x) => x.age >= 8 && x.age <= 10 && x.recommendedLevel === "Початковий").map((x) => x.id))}>Вибрати цих дітей →</button></div>
            </article>
            <article className="panel">
              <div className="panelHead"><div><p className="eyebrow">Активні</p><h2>Групи</h2></div><span className="counter">{groups.length}</span></div>
              <div className="groupCards">
                {groups.map((group) => <div className="groupCard" key={group.id}>
                  <div><b>{group.name}</b><span>{group.schedule}</span></div>
                  <div className="capacity"><strong>{group.members.length}/{group.capacity}</strong><span>{group.location}</span></div>
                  <div className="capacityTrack"><i style={{ width: Math.min(100, group.members.length / group.capacity * 100) + "%" }} /></div>
                </div>)}
              </div>
            </article>
          </div>
        </section>}

        {active !== "Дашборд" && active !== "Заявки" && active !== "Учні" && active !== "Групи" && active !== "Розклад" && active !== "Відвідування" && active !== "Оплати" && active !== "Працівники" && active !== "Локації" && active !== "Звіти" && <section className="panel placeholder">
          <p className="eyebrow">Наступний модуль</p>
          <h2>{active}</h2>
          <p>Каркас модуля вже передбачений у навігації. Реалізуємо після завершення наскрізного сценарію «заявка → пробне → група → учень».</p>
        </section>}
      </main>

      {showSearch && <div className="modalBackdrop" onClick={() => setShowSearch(false)}>
        <div className="groupModal searchModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowSearch(false)}>×</button>
          <p className="eyebrow">Пошук</p><h2>Знайти в CRM</h2>
          <input className="globalSearchInput" autoFocus value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Ім’я, телефон, група, працівник…" />
          {!searchTerm && <div className="searchHint">Почніть вводити ім’я, телефон або назву групи.</div>}
          {searchTerm && searchLeads.length + searchGroups.length + searchStaff.length === 0 && <div className="searchHint">Нічого не знайдено.</div>}
          {searchLeads.length > 0 && <div className="searchResults">
            <h3>Діти та заявки</h3>
            {searchLeads.map((item) => <button key={item.id} onClick={() => {
              if (item.status === "Зарахований") setSelectedStudentId(item.id); else setSelectedId(item.id);
              setShowSearch(false);
            }}><span><b>{item.child}</b><small>{item.parent} · {item.phone}</small></span><i>{item.status}</i></button>)}
          </div>}
          {searchGroups.length > 0 && <div className="searchResults">
            <h3>Групи</h3>
            {searchGroups.map((item) => <button key={item.id} onClick={() => { setActive("Групи"); setShowSearch(false); }}>
              <span><b>{item.name}</b><small>{item.ages} · {item.location}</small></span><i>{item.members.length}/{item.capacity}</i>
            </button>)}
          </div>}
          {searchStaff.length > 0 && <div className="searchResults">
            <h3>Працівники</h3>
            {searchStaff.map((item) => <button key={item.id} onClick={() => { setSelectedStaffId(item.id); setShowSearch(false); }}>
              <span><b>{item.fullName}</b><small>{item.role} · {item.email || item.phone}</small></span><i>{item.isActive ? "Активний" : "Неактивний"}</i>
            </button>)}
          </div>}
        </div>
      </div>}

      {showLeadForm && <div className="modalBackdrop" onClick={() => setShowLeadForm(false)}>
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowLeadForm(false)}>×</button>
          <p className="eyebrow">Нова заявка</p><h2>Додати дитину</h2>
          <div className="formTwo">
            <label>Ім’я дитини<input value={leadChildName} onChange={(e) => setLeadChildName(e.target.value)} placeholder="Максим" /></label>
            <label>Вік<input type="number" min={3} max={25} value={leadAge} onChange={(e) => setLeadAge(Number(e.target.value))} /></label>
          </div>
          <label>Контактна особа<input value={leadContactName} onChange={(e) => setLeadContactName(e.target.value)} placeholder="Оксана" /></label>
          <label>Телефон<input type="tel" value={leadPhone} onChange={(e) => setLeadPhone(e.target.value)} placeholder="+380 67 123 45 67" /></label>
          <label>Джерело<select value={leadSource} onChange={(e) => setLeadSource(e.target.value)}>
            <option value="phone">Телефон</option>
            <option value="website">Сайт</option>
            <option value="instagram">Instagram</option>
            <option value="recommendation">Рекомендація</option>
            <option value="walk-in">Зайшли особисто</option>
          </select></label>
          <label>Коментар<textarea value={leadComment} onChange={(e) => setLeadComment(e.target.value)} placeholder="Що цікавить, бажаний час, примітки…" /></label>
          <button className="primary full" disabled={!leadChildName.trim() || !leadContactName.trim() || !leadPhone.trim()} onClick={createManualLead}>Створити заявку</button>
        </div>
      </div>}

      {showInviteForm && <div className="modalBackdrop" onClick={() => setShowInviteForm(false)}>
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowInviteForm(false)}>×</button>
          <p className="eyebrow">Доступ до CRM</p><h2>Запросити працівника</h2>
          {!inviteLink ? <>
            <label>Email<input type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="teacher@example.com" /></label>
            <label>Роль<select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as StaffRoleDemo)}>{["Адміністратор","Менеджер","Викладач","Бухгалтер"].map((role) => <option key={role}>{role}</option>)}</select></label>
            <button className="primary full" disabled={!inviteEmail.trim()} onClick={createInvitation}>Створити запрошення</button>
          </> : <>
            <div className="inviteSuccess"><b>Запрошення готове</b><p>Надішліть це посилання працівнику. Воно одноразове та діє 7 днів.</p><code>{inviteLink}</code></div>
            <button className="primary full" onClick={() => navigator.clipboard?.writeText(inviteLink)}>Копіювати посилання</button>
          </>}
        </div>
      </div>}

            {showStaffForm && <div className="modalBackdrop" onClick={() => setShowStaffForm(false)}>
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowStaffForm(false)}>×</button>
          <p className="eyebrow">Команда</p><h2>Новий працівник</h2>
          <label>Ім’я та прізвище<input value={staffName} onChange={(e) => setStaffName(e.target.value)} placeholder="Іван Петренко" /></label>
          <label>Роль<select value={staffRole} onChange={(e) => setStaffRole(e.target.value as StaffRoleDemo)}>{["Власник","Адміністратор","Менеджер","Викладач","Бухгалтер"].map((role) => <option key={role}>{role}</option>)}</select></label>
          <div className="formTwo"><label>Email<input type="email" value={staffEmail} onChange={(e) => setStaffEmail(e.target.value)} /></label><label>Телефон<input value={staffPhone} onChange={(e) => setStaffPhone(e.target.value)} /></label></div>
          <button className="primary full" disabled={!staffName.trim()} onClick={createStaffMember}>Додати працівника</button>
        </div>
      </div>}

      {showLocationForm && <div className="modalBackdrop" onClick={() => setShowLocationForm(false)}>
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowLocationForm(false)}>×</button>
          <p className="eyebrow">Мережа</p><h2>Нова локація</h2>
          <label>Назва<input value={locationName} onChange={(e) => setLocationName(e.target.value)} placeholder="AeroKiDS Центр" /></label>
          <label>Адреса<input value={locationAddress} onChange={(e) => setLocationAddress(e.target.value)} placeholder="Івано-Франківськ" /></label>
          <button className="primary full" disabled={!locationName.trim()} onClick={createLocationDemo}>Створити локацію</button>
        </div>
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
        </aside>
      </div>}

            {showPlanForm && <div className="modalBackdrop" onClick={() => setShowPlanForm(false)}>
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowPlanForm(false)}>×</button>
          <p className="eyebrow">Абонементи</p><h2>Новий тариф</h2>
          <label>Назва<input value={planName} onChange={(e) => setPlanName(e.target.value)} /></label>
          <div className="formTwo">
            <label>Ціна, грн<input type="number" min={0} value={planPrice} onChange={(e) => setPlanPrice(Number(e.target.value))} /></label>
            <label>Занять<input type="number" min={0} value={planLessons} onChange={(e) => setPlanLessons(Number(e.target.value))} /></label>
          </div>
          <button className="primary full" disabled={!planName.trim()} onClick={createPlan}>Створити тариф</button>
        </div>
      </div>}

            {showPaymentForm && <div className="modalBackdrop" onClick={() => setShowPaymentForm(false)}>
        <div className="groupModal" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setShowPaymentForm(false)}>×</button>
          <p className="eyebrow">Нарахування</p><h2>Створити оплату</h2>
          <label>Учень<select value={paymentStudentId} onChange={(e) => setPaymentStudentId(e.target.value)}>{activeStudents.map((student) => <option value={student.id} key={student.id}>{student.child} · {student.parent}</option>)}</select></label>
          <label>Абонемент<select value={paymentPlanId} onChange={(e) => setPaymentPlanId(e.target.value)}>{plans.map((plan) => <option value={plan.id} key={plan.id}>{plan.name} · {plan.price ? money(plan.price) : "індивідуально"}</option>)}</select></label>
          <label>Оплатити до<input type="date" value={paymentDueDate} onChange={(e) => setPaymentDueDate(e.target.value)} /></label>
          <button className="primary full" onClick={createPayment}>Створити нарахування</button>
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

      {showGroupForm && <div className="modalBackdrop" onClick={() => setShowGroupForm(false)}>
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
          <label>Розклад<input value={groupSchedule} onChange={(e) => setGroupSchedule(e.target.value)} /></label>
          <div className="selectedNames">{leads.filter((x) => selectedCandidates.includes(x.id)).map((x) => {
            const compatibility = candidateCompatibility(x, parseScheduleText(groupSchedule), groupLocationId || null);
            return <span className={"candidateCompatibility " + compatibility.state} key={x.id}>
              <b>{x.child} · {x.age}</b><small>{compatibility.label}</small>
            </span>;
          })}</div>
          <button className="primary full" disabled={selectedCandidates.length > groupCapacity} onClick={createGroupFromCandidates}>
            {selectedCandidates.length > groupCapacity ? "Збільште місткість групи" : "Створити групу і зарахувати"}
          </button>
        </div>
      </div>}

      {selected && <div className="drawerBackdrop" onClick={() => setSelectedId(null)}>
        <aside className="drawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setSelectedId(null)}>×</button>
          <p className="eyebrow">Картка заявки</p>
          <h2>{selected.child}, {selected.age} років</h2>
          <div className="contactCard"><span>Контакт</span><b>{selected.parent}</b><a href={"tel:" + selected.phone.replace(/\s/g, "")}>{selected.phone}</a></div>
          <label className="statusField">Статус
            <select value={selected.status} onChange={(e) => updateStatus(selected.id, e.target.value as LeadStatus)}>
              {statuses.map((status) => <option key={status}>{status}</option>)}
            </select>
          </label>
          <div className="detailGrid"><span>Джерело<b>{selected.source}</b></span><span>Вік<b>{selected.age}</b></span></div>
          {selected.comment && <div className="noteBox"><span>Коментар</span><p>{selected.comment}</p></div>}
          {selected.trialAt && <div className="trialSummary"><span>Пробне заняття</span><b>{new Date(selected.trialAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</b><small>{selected.trialLocation ?? "Локацію не вказано"}</small></div>}
          <div className="preferenceSummary">
            <div><span>Бажана локація</span><b>{selected.preferredLocationName ?? "Не вказано"}</b></div>
            <div><span>Бажаний час</span><b>{availabilityLabel(selected.availability ?? [])}</b></div>
            <button className="search" onClick={() => setPreferenceMode((value) => !value)}>{preferenceMode ? "Скасувати" : "Змінити"}</button>
          </div>

          {preferenceMode && <div className="workflowBox">
            <div className="workflowHead"><h3>Бажаний графік</h3><button onClick={() => setPreferenceMode(false)}>×</button></div>
            <label>Локація<select value={preferenceLocationId} onChange={(e) => setPreferenceLocationId(e.target.value)}>
              <option value="">Не має значення</option>
              {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
            </select></label>
            <div className="availabilityDays">
              {["Пн","Вт","Ср","Чт","Пт","Сб","Нд"].map((day, index) => <button type="button" key={day} className={availabilityDays.includes(index) ? "active" : ""} onClick={() => toggleAvailabilityDay(index)}>{day}</button>)}
            </div>
            <div className="formTwo">
              <label>Від<input type="time" value={availabilityStart} onChange={(e) => setAvailabilityStart(e.target.value)} /></label>
              <label>До<input type="time" value={availabilityEnd} onChange={(e) => setAvailabilityEnd(e.target.value)} /></label>
            </div>
            <button className="primary full" disabled={preferenceSaving || availabilityEnd <= availabilityStart} onClick={saveStudentPreferences}>{preferenceSaving ? "Зберігаємо…" : "Зберегти бажаний графік"}</button>
          </div>}



          <div className="drawerActions">
            <button className="primary" onClick={() => setTrialMode("schedule")}>{selected.trialAt ? "Змінити пробне" : "Записати на пробне"}</button>
            {selected.trialAt && selected.trialResult !== "completed" && <button className="search" onClick={() => setTrialMode("complete")}>Результат пробного</button>}
          </div>

          {trialMode === "schedule" && <div className="workflowBox">
            <div className="workflowHead"><h3>Запис на пробне</h3><button onClick={() => setTrialMode(null)}>×</button></div>
            <label>Дата і час<input type="datetime-local" value={trialAt} onChange={(e) => setTrialAt(e.target.value)} /></label>
            <label>Локація<select value={trialLocationId} onChange={(e) => { setTrialLocationId(e.target.value); setTrialLocation(locations.find((location) => location.id === e.target.value)?.name ?? ""); }}>
              <option value="">Без локації</option>
              {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
            </select></label>
            <button className="primary full" onClick={scheduleTrial}>Підтвердити пробне</button>
          </div>}

          {trialMode === "complete" && <div className="workflowBox">
            <div className="workflowHead"><h3>Результат пробного</h3><button onClick={() => setTrialMode(null)}>×</button></div>
            <label>Рекомендований рівень<select value={recommendedLevel} onChange={(e) => setRecommendedLevel(e.target.value)}><option>Початковий</option><option>Середній</option><option>Просунутий</option></select></label>
            <label>Коментар викладача<textarea value={teacherNotes} onChange={(e) => setTeacherNotes(e.target.value)} placeholder="Що сподобалось, як дитина справилась, що рекомендуємо" /></label>
            <div className="resultActions"><button className="primary" onClick={() => completeTrial("completed")}>Пробне пройдено</button><button className="search" onClick={() => completeTrial("no_show")}>Не прийшов</button></div>
          </div>}

          {selected.trialResult === "completed" && <div className="resultCard"><span>Пробне завершено</span><b>{selected.recommendedLevel ?? "Рівень не вказано"}</b>{selected.teacherNotes && <p>{selected.teacherNotes}</p>}<small>Дитина автоматично перейшла в «Очікує групу».</small></div>}

          {apiEnabled ? <AuditHistory title="Історія" events={entityEvents} loading={historyLoading} /> : <div className="history">
            <h3>Історія</h3>
            <div><i></i><p><b>Заявка створена</b><span>Джерело: {selected.source}</span></p></div>
            {selected.trialAt && <div><i></i><p><b>Пробне заплановано</b><span>{new Date(selected.trialAt).toLocaleString("uk-UA")}</span></p></div>}
            {selected.trialResult === "completed" && <div><i></i><p><b>Пробне пройдено</b><span>Рівень: {selected.recommendedLevel ?? "не вказано"}</span></p></div>}
            {selected.status !== "Нова" && <div><i></i><p><b>Поточний статус</b><span>{selected.status}</span></p></div>}
          </div>}
        </aside>
      </div>}
    </div>
  );
}

function LeadTable({ leads, onOpen }: { leads: Lead[]; onOpen: (id: EntityId) => void }) {
  return <div className="table">
    <div className="row tableHead"><span>Дитина</span><span>Вік</span><span>Батьки</span><span>Джерело</span><span>Статус</span></div>
    {leads.map((lead) => <button className="row rowButton" key={lead.id} onClick={() => onOpen(lead.id)}><b>{lead.child}</b><span>{lead.age}</span><span>{lead.parent}</span><span>{lead.source}</span><span className="pill">{lead.status}</span></button>)}
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
    status: item.status,
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
  })));

  const today = new Date().toISOString().slice(0, 10);
  setPayments(bundle.payments
    .filter((item) => item.status === "pending" || item.status === "paid")
    .map((item) => ({
      id: item.id,
      studentId: item.student_id,
      planId: item.plan_id ?? "",
      amount: item.amount_minor / 100,
      dueDate: item.due_date ?? "",
      status: item.status === "paid" ? "paid" : item.due_date && item.due_date < today ? "overdue" : "pending",
      method: paymentMethodLabel(item.method),
    })));
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
    child: [item.first_name, item.last_name].filter(Boolean).join(" "),
    age: item.age ?? 0,
    parent: item.contact_name ?? "Контакт не вказано",
    phone: item.contact_phone ?? "",
    source: item.source ?? "CRM",
    comment: item.comment ?? undefined,
    preferredLocationId: item.preferred_location_id ?? undefined,
    preferredLocationName: item.preferred_location_name ?? undefined,
    availability: item.availability.map((slot) => ({
      weekday: slot.weekday,
      start_time: slot.start_time.slice(0, 5),
      end_time: slot.end_time.slice(0, 5),
    })),
    status: crmStatusLabel(item.crm_status),
    trialId: item.latest_trial_id ?? undefined,
    trialAt: item.latest_trial_at ?? undefined,
    trialLocationId: item.trial_location_id ?? undefined,
    trialLocation: item.trial_location_name ?? undefined,
    recommendedLevel: item.recommended_level ?? undefined,
    trialResult: item.crm_status === "waiting_for_group" || item.crm_status === "enrolled" ? "completed" : item.latest_trial_at ? "scheduled" : undefined,
  }));

  const students: Lead[] = bundle.students.map((item) => ({
    id: item.student_id,
    child: [item.first_name, item.last_name].filter(Boolean).join(" "),
    age: item.age ?? 0,
    parent: item.contact_name ?? "Контакт не вказано",
    phone: item.contact_phone ?? "",
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
    "Пробне пройдено": "trial_completed",
    "Очікує групу": "waiting_for_group",
    "Зарахований": "enrolled",
  };
  return values[status];
}

function crmStatusLabel(status: WorkspaceBundle["leads"][number]["crm_status"]): LeadStatus {
  const labels: Record<WorkspaceBundle["leads"][number]["crm_status"], LeadStatus> = {
    new: "Нова",
    contacted: "Зв'язались",
    trial_scheduled: "Пробне заплановано",
    trial_completed: "Пробне пройдено",
    waiting_for_group: "Очікує групу",
    enrolled: "Зарахований",
    no_response: "Зв'язались",
    declined: "Зв'язались",
    not_relevant: "Зв'язались",
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
        <span>{auditEventDetail(event)} · {new Date(event.created_at).toLocaleString("uk-UA")}</span>
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
  if (typeof payload["crm_status"] === "string") return String(payload["crm_status"]);
  if (typeof payload["student_status"] === "string") return String(payload["student_status"]);
  if (typeof payload["recommended_level"] === "string") return String(payload["recommended_level"]);
  if (typeof payload["amount_minor"] === "number") return formatMoney(Number(payload["amount_minor"]) / 100);
  return "CRM";
}

function LoginView({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
  const inviteToken = new URLSearchParams(window.location.search).get("invite");
  const [inviteName, setInviteName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [bootstrapAvailable, setBootstrapAvailable] = useState(false);
  const [checkingBootstrap, setCheckingBootstrap] = useState(true);
  const [organizationName, setOrganizationName] = useState("AeroKiDS");
  const [organizationSlug, setOrganizationSlug] = useState("aerokids");
  const [ownerName, setOwnerName] = useState("");

  useEffect(() => {
    if (inviteToken) {
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
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося створити першу організацію");
    } finally {
      setLoading(false);
    }
  };

  return <div className="loginScreen">
    <div className="loginCard">
      <div className="loginBrand"><span className="mark">✦</span><div><b>School CRM</b><small>Керування школою в одному місці</small></div></div>

      {inviteToken ? <>
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

function toLocalDateTimeInput(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function formatMoney(value: number, locale = "uk-UA", currency = "UAH") {
  return new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

function candidateCompatibility(
  lead: Lead,
  schedule: Array<{ weekday: number; start_time: string; duration_minutes: number }>,
  locationId: string | null,
) {
  if (lead.preferredLocationId && locationId && lead.preferredLocationId !== locationId) {
    return { state: "mismatch", label: "Інша бажана локація" };
  }
  if (!schedule.length || !(lead.availability?.length)) {
    return { state: "unknown", label: "Графік не вказано або ще не задано" };
  }

  const fits = schedule.every((lesson) => {
    const lessonStart = timeToMinutes(lesson.start_time);
    const lessonEnd = lessonStart + lesson.duration_minutes;
    return lead.availability!.some((slot) =>
      slot.weekday === lesson.weekday
      && timeToMinutes(slot.start_time) <= lessonStart
      && timeToMinutes(slot.end_time) >= lessonEnd
    );
  });

  return fits
    ? { state: "match", label: "Графік підходить" }
    : { state: "mismatch", label: "Графік не збігається" };
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

function parseScheduleText(value: string) {
  const weekdayMap: Record<string, number> = {
    "Пн": 0, "Вт": 1, "Ср": 2, "Чт": 3, "Пт": 4, "Сб": 5, "Нд": 6,
  };
  return value.split(";").flatMap((part) => {
    const [daysPart, timePart] = part.split("·").map((item) => item.trim());
    if (!daysPart || !/^([01]\d|2[0-3]):[0-5]\d$/.test(timePart ?? "")) return [];
    return daysPart.split("/").map((day) => day.trim()).flatMap((day) => {
      const weekday = weekdayMap[day];
      return weekday === undefined ? [] : [{ weekday, start_time: timePart, duration_minutes: 60 }];
    });
  });
}

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
