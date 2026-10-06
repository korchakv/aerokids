export type Membership = {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  organization_timezone: string;
  organization_currency: string;
  organization_locale: string;
  role: "owner" | "admin" | "manager" | "teacher" | "accountant";
};

export type AuthUser = {
  id: string;
  email: string;
  full_name: string | null;
  memberships: Membership[];
};

export type Session = {
  accessToken: string;
  user: AuthUser;
  organizationId: string;
};

const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const STORAGE_KEY = "school-crm-session";

export const apiEnabled = Boolean(API_URL);

async function request<T>(path: string, init: RequestInit = {}, session?: Session): Promise<T> {
  if (!API_URL) throw new Error("API URL is not configured");
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (session) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
    headers.set("X-Organization-Id", session.organizationId);
  }

  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = "Request failed";
    try {
      const body = await response.json();
      const detail = body?.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = detail
          .map((item) => typeof item?.msg === "string" ? item.msg : JSON.stringify(item))
          .join("; ");
      } else if (detail && typeof detail === "object") {
        message = typeof detail.message === "string" ? detail.message : JSON.stringify(detail);
      }
    } catch {}
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<Session> {
  const result = await request<{ access_token: string; user: AuthUser }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  const organizationId = result.user.memberships[0]?.organization_id;
  if (!organizationId) throw new Error("Для цього користувача немає доступної організації");
  const session = { accessToken: result.access_token, user: result.user, organizationId };
  saveSession(session);
  return session;
}

export async function refreshMe(session: Session): Promise<Session> {
  const user = await request<AuthUser>("/auth/me", {
    headers: { Authorization: `Bearer ${session.accessToken}` },
  });
  const organizationId = user.memberships.some((m) => m.organization_id === session.organizationId)
    ? session.organizationId
    : user.memberships[0]?.organization_id;
  if (!organizationId) throw new Error("Немає доступної організації");
  const updated = { ...session, user, organizationId };
  saveSession(updated);
  return updated;
}

export function changeOrganization(session: Session, organizationId: string): Session {
  if (!session.user.memberships.some((m) => m.organization_id === organizationId)) {
    throw new Error("Немає доступу до цієї організації");
  }
  const updated = { ...session, organizationId };
  saveSession(updated);
  return updated;
}

export function loadSession(): Session | null {
  try {
    let raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        sessionStorage.setItem(STORAGE_KEY, raw);
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    return raw ? JSON.parse(raw) as Session : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  localStorage.removeItem(STORAGE_KEY);
}

export function clearSession() {
  sessionStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(STORAGE_KEY);
}

export function apiGet<T>(path: string, session: Session) {
  return request<T>(path, {}, session);
}

export function apiPost<T>(path: string, body: unknown, session: Session) {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) }, session);
}

export function apiPatch<T>(path: string, body: unknown, session: Session) {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) }, session);
}


export type StudentAvailabilitySlot = {
  weekday: number;
  start_time: string;
  end_time: string;
  preference: "preferred" | "possible" | "avoid";
  note: string | null;
};

export type IntakeDuplicateMatch = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  age: number | null;
  crm_status: WorkspaceLead["crm_status"];
  student_status: "prospect" | "active" | "paused" | "archived";
  student_phone: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  matched_phone: string;
  matched_as: "student" | "contact" | "student_and_contact";
  likely_same_student: boolean;
};

export function checkIntakeDuplicates(input: {
  child_first_name: string;
  child_age: number;
  phone: string;
  child_phone?: string | null;
}, session: Session) {
  return apiPost<{ matches: IntakeDuplicateMatch[] }>("/intake/duplicate-check", input, session);
}


export type WorkspaceLead = {
  student_id: string;
  created_at: string;
  first_name: string;
  last_name: string | null;
  student_phone: string | null;
  age: number | null;
  source: string | null;
  comment: string | null;
  preferred_location_id: string | null;
  preferred_location_name: string | null;
  availability: StudentAvailabilitySlot[];
  crm_status: "new" | "contacted" | "trial_scheduled" | "trial_completed" | "waiting_for_group" | "enrolled" | "no_response" | "declined" | "not_relevant";
  contact_name: string | null;
  contact_phone: string | null;
  latest_trial_id: string | null;
  latest_trial_at: string | null;
  latest_trial_status: "scheduled" | "completed" | "no_show" | "cancelled" | null;
  trial_location_id: string | null;
  trial_location_name: string | null;
  recommended_level: string | null;
  teacher_notes: string | null;
  next_contact_at: string | null;
  close_reason: string | null;
  close_note: string | null;
};

export type WorkspaceStudent = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  student_phone: string | null;
  age: number | null;
  source: string | null;
  student_status: "active" | "paused" | "archived";
  contact_name: string | null;
  contact_phone: string | null;
  group_id: string | null;
  group_name: string | null;
};

export type WorkspaceGroup = {
  group_id: string;
  name: string;
  location_id: string | null;
  location_name: string | null;
  capacity: number | null;
  enrolled_count: number;
  min_age: number | null;
  max_age: number | null;
  primary_teacher_id: string | null;
  primary_teacher_name: string | null;
};

export type WorkspaceBundle = {
  leads: WorkspaceLead[];
  students: WorkspaceStudent[];
  groups: WorkspaceGroup[];
};

export async function loadWorkspace(session: Session): Promise<WorkspaceBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  const role = membership?.role;

  const leadsPromise = ["owner", "admin", "manager", "teacher"].includes(role ?? "")
    ? apiGet<WorkspaceLead[]>("/workspace/leads", session)
    : Promise.resolve([]);

  const studentsPromise = apiGet<WorkspaceStudent[]>("/workspace/students", session);

  const groupsPromise = role === "accountant"
    ? Promise.resolve([])
    : apiGet<WorkspaceGroup[]>("/workspace/groups", session);

  const [leads, students, groups] = await Promise.all([leadsPromise, studentsPromise, groupsPromise]);
  return { leads, students, groups };
}


export type ApiLocation = {
  id: string;
  organization_id: string;
  name: string;
  address: string | null;
  is_active: boolean;
};

export type ApiStaff = {
  id: string;
  organization_id: string;
  user_id: string | null;
  full_name: string;
  email: string | null;
  phone: string | null;
  role: "owner" | "admin" | "manager" | "teacher" | "accountant";
  is_active: boolean;
  notes: string | null;
};

export type ApiStaffProfile = ApiStaff & {
  assignments: {
    location_ids: string[];
    group_ids: string[];
  };
};

export type ApiSubscriptionPlan = {
  id: string;
  organization_id: string;
  name: string;
  price_minor: number;
  period_days: number;
  lessons_included: number | null;
  usage_mode: "attendance" | "scheduled" | "period";
  absent_rule: "consume" | "dont_consume" | "choice";
  excused_rule: "consume" | "dont_consume" | "makeup";
  late_rule: "consume" | "dont_consume";
  end_rule: "lessons" | "date" | "whichever_first";
  renewal_trigger: "last_lesson" | "date" | "manual";
  allow_debt: boolean;
  max_lates: number | null;
  makeup_expiry_days: number | null;
  is_active: boolean;
};

export type ApiPayment = {
  id: string;
  organization_id: string;
  student_id: string;
  subscription_id: string | null;
  plan_id: string | null;
  amount_minor: number;
  currency: string;
  status: "pending" | "paid" | "refunded" | "cancelled";
  method: "cash" | "card" | "bank" | "other" | null;
  due_date: string | null;
  paid_at: string | null;
  note: string | null;
  adjusted_amount_minor: number;
  paid_minor: number;
  refunded_minor: number;
  balance_minor: number;
};

export type ApiStudentSubscription = {
  id: string;
  organization_id: string;
  student_id: string;
  plan_id: string;
  group_id: string | null;
  status: "active" | "paused" | "expired" | "cancelled";
  starts_on: string;
  ends_on: string;
  price_minor: number;
  discount_minor: number;
  discount_label: string | null;
  auto_renew: boolean;
  renewal_of_id: string | null;
  used_lessons: number;
  remaining_lessons: number | null;
  needs_renewal: boolean;
};

export type OperationsBundle = {
  locations: ApiLocation[];
  staff: ApiStaffProfile[];
  plans: ApiSubscriptionPlan[];
  payments: ApiPayment[];
  subscriptions: ApiStudentSubscription[];
};

export async function loadOperations(session: Session): Promise<OperationsBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  const role = membership?.role;

  const fullAccess = ["owner", "admin", "manager", "teacher"].includes(role ?? "");

  const locationsPromise = fullAccess
    ? apiGet<ApiLocation[]>("/locations", session)
    : Promise.resolve([]);

  const staffPromise = fullAccess
    ? apiGet<ApiStaff[]>("/staff", session).then(async (items) => Promise.all(
        items.map((item) => apiGet<ApiStaffProfile>(`/staff/${item.id}/profile`, session))
      ))
    : Promise.resolve([]);

  const financeAccess = fullAccess || role === "accountant";

  const plansPromise = financeAccess
    ? apiGet<ApiSubscriptionPlan[]>("/subscription-plans", session)
    : Promise.resolve([]);

  const paymentsPromise = financeAccess
    ? apiGet<ApiPayment[]>("/payments", session)
    : Promise.resolve([]);

  const subscriptionsPromise = financeAccess
    ? apiGet<ApiStudentSubscription[]>("/student-subscriptions", session)
    : Promise.resolve([]);

  const [locations, staff, plans, payments, subscriptions] = await Promise.all([
    locationsPromise,
    staffPromise,
    plansPromise,
    paymentsPromise,
    subscriptionsPromise,
  ]);

  return { locations, staff, plans, payments, subscriptions };
}


export function runBillingRenewals(session: Session) {
  return apiPost<{ resumed_subscriptions: number; created_subscriptions: number; skipped_stale_subscriptions: number; created_payment_ids: string[] }>("/billing/renewals/run", {}, session);
}

export function apiPut<T>(path: string, body: unknown, session: Session) {
  return request<T>(path, { method: "PUT", body: JSON.stringify(body) }, session);
}

export async function apiDelete(path: string, session: Session): Promise<void> {
  if (!API_URL) throw new Error("API URL is not configured");
  const response = await fetch(`${API_URL}${path}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${session.accessToken}`,
      "X-Organization-Id": session.organizationId,
    },
  });
  if (!response.ok) {
    let message = "Request failed";
    try {
      const body = await response.json();
      message = body.detail ?? message;
    } catch {}
    throw new Error(message);
  }
}


export async function getBootstrapStatus(): Promise<boolean> {
  const result = await request<{ available: boolean }>("/auth/bootstrap-status");
  return result.available;
}

export async function bootstrapOwner(input: {
  organization_name: string;
  organization_slug: string;
  full_name: string;
  email: string;
  password: string;
}, bootstrapSecret?: string): Promise<Session> {
  const result = await request<{
    organization_id: string;
    user_id: string;
    access_token: string;
    token_type: string;
  }>("/auth/bootstrap", {
    method: "POST",
    headers: bootstrapSecret ? { "X-Bootstrap-Secret": bootstrapSecret } : undefined,
    body: JSON.stringify(input),
  });

  const user = await request<AuthUser>("/auth/me", {
    headers: { Authorization: `Bearer ${result.access_token}` },
  });
  const session: Session = {
    accessToken: result.access_token,
    user,
    organizationId: result.organization_id,
  };
  saveSession(session);
  return session;
}


export type InvitationStatus = "valid" | "accepted" | "expired" | "invalid";

export async function getInvitationStatus(inviteToken: string): Promise<InvitationStatus> {
  const result = await request<{ status: InvitationStatus }>("/auth/invite-status", {
    method: "POST",
    body: JSON.stringify({ invite_token: inviteToken }),
  });
  return result.status;
}


export async function acceptInvite(input: {
  invite_token: string;
  full_name: string;
  password: string;
}): Promise<Session> {
  const result = await request<{ access_token: string; user: AuthUser }>("/auth/accept-invite", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const organizationId = result.user.memberships[0]?.organization_id;
  if (!organizationId) throw new Error("Запрошення не надало доступу до організації");
  const session: Session = {
    accessToken: result.access_token,
    user: result.user,
    organizationId,
  };
  saveSession(session);
  return session;
}


export type ApiGroupSchedule = {
  id: string;
  organization_id: string;
  group_id: string;
  weekday: number;
  start_time: string;
  duration_minutes: number;
  is_active: boolean;
};

export type ApiLessonSession = {
  id: string;
  organization_id: string;
  group_id: string;
  location_id: string | null;
  starts_at: string;
  duration_minutes: number;
  topic: string | null;
  notes: string | null;
  status: "scheduled" | "completed" | "cancelled";
  attendance_present: number;
  attendance_absent: number;
  attendance_late: number;
  attendance_excused: number;
  attendance_total: number;
};

export type ApiAttendance = {
  id: string;
  organization_id: string;
  session_id: string;
  student_id: string;
  status: "present" | "absent" | "late" | "excused";
  note: string | null;
};

export type ApiGroupMemberDetail = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  student_phone: string | null;
  age: number | null;
  contact_name: string | null;
  contact_phone: string | null;
  enrollment_started_at: string;
  enrollment_status: "active" | "paused" | "finished";
  attendance: {
    present: number;
    absent: number;
    late: number;
    excused: number;
    total: number;
    attendance_rate: number;
  };
  billing: {
    status: "current" | "upcoming" | "due" | "overdue" | "no_plan";
    plan_name: string | null;
    lessons_used: number | null;
    lessons_included: number | null;
    lessons_remaining: number | null;
    amount_due_minor: number;
    next_due_date: string | null;
    last_paid_at: string | null;
    last_paid_minor: number | null;
    subscription_ends_on: string | null;
  } | null;
  payments: ApiPayment[];
};

export type ApiGroupDetail = {
  group: {
    id: string;
    organization_id: string;
    location_id: string | null;
    name: string;
    capacity: number | null;
    min_age: number | null;
    max_age: number | null;
    is_active: boolean;
  };
  schedules: ApiGroupSchedule[];
  members: ApiGroupMemberDetail[];
};

export type ApiPaymentReminder = {
  payment_id: string;
  student_id: string;
  student_name: string;
  contact_name: string | null;
  contact_phone: string | null;
  amount_minor: number;
  currency: string;
  due_date: string;
  days_from_due: number;
  stage: "upcoming_3" | "due_today" | "overdue_1" | "overdue_3" | "overdue_7" | "overdue_14" | "overdue_30";
  label: string;
  last_reminder_at: string | null;
};

export type ApiStudentAttendanceHistoryItem = {
  session_id: string;
  group_id: string;
  group_name: string;
  starts_at: string;
  duration_minutes: number;
  topic: string | null;
  lesson_status: "scheduled" | "completed" | "cancelled";
  status: "present" | "absent" | "late" | "excused";
  note: string | null;
};

export function loadStudentAttendanceHistory(studentId: string, session: Session) {
  return apiGet<ApiStudentAttendanceHistoryItem[]>(`/students/${studentId}/attendance-history`, session);
}

export type ApiGroupRosterStudent = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  age: number | null;
};

export function loadGroupRoster(groupId: string, session: Session) {
  return apiGet<ApiGroupRosterStudent[]>(`/groups/${groupId}/roster`, session);
}

export function loadGroupDetail(groupId: string, session: Session) {
  return apiGet<ApiGroupDetail>(`/groups/${groupId}/detail`, session);
}

export function loadPaymentReminders(session: Session) {
  return apiGet<ApiPaymentReminder[]>("/payment-reminders", session);
}

export function recordPaymentReminder(paymentId: string, stage: ApiPaymentReminder["stage"], channel: "manual" | "sms" | "email" | "messenger" | "phone", session: Session) {
  return apiPost(`/payments/${paymentId}/reminders`, { stage, channel }, session);
}


export type TeachingBundle = {
  schedules: ApiGroupSchedule[];
  lessons: ApiLessonSession[];
};

export async function loadTeaching(session: Session): Promise<TeachingBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  if (membership?.role === "accountant") return { schedules: [], lessons: [] };
  const [schedules, lessons] = await Promise.all([
    apiGet<ApiGroupSchedule[]>("/group-schedules", session),
    apiGet<ApiLessonSession[]>("/lesson-sessions", session),
  ]);
  return { schedules, lessons };
}

export function loadAttendance(sessionId: string, session: Session) {
  return apiGet<ApiAttendance[]>(`/lesson-sessions/${sessionId}/attendance`, session);
}


export type OverviewReport = {
  funnel: Array<{ status: WorkspaceLead["crm_status"]; count: number }>;
  active_students: number;
  active_groups: number;
  enrolled_students: number;
  group_capacity: number;
  active_staff: number;
  active_locations: number;
  attendance: {
    present: number;
    absent: number;
    late: number;
    excused: number;
    total: number;
    attendance_rate: number;
  };
  payments: {
    paid_minor: number;
    pending_minor: number;
    overdue_minor: number;
    paid_count: number;
    pending_count: number;
    overdue_count: number;
  };
};

export async function loadOverviewReport(session: Session): Promise<OverviewReport | null> {
  return apiGet<OverviewReport>("/reports/overview", session);
}


export type ApiAuditEvent = {
  id: string;
  organization_id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  actor_email: string | null;
  entity_type: string;
  entity_id: string | null;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string;
};

export function loadAuditEvents(entityType: string, entityId: string, session: Session) {
  const query = new URLSearchParams({ entity_type: entityType, entity_id: entityId, limit: "100" });
  return apiGet<ApiAuditEvent[]>(`/audit-events?${query.toString()}`, session);
}


export async function resetPassword(input: {
  reset_token: string;
  password: string;
}): Promise<Session> {
  const result = await request<{ access_token: string; user: AuthUser }>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const organizationId = result.user.memberships[0]?.organization_id;
  if (!organizationId) throw new Error("Для цього користувача немає доступної організації");
  const session: Session = {
    accessToken: result.access_token,
    user: result.user,
    organizationId,
  };
  saveSession(session);
  return session;
}
