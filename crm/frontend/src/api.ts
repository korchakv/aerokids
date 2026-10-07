import type { Membership, AuthUser, Session, StudentAvailabilitySlot, IntakeDuplicateMatch, WorkspaceLead, WorkspaceStudent, WorkspaceGroup, WorkspaceBundle, ApiLocation, ApiStaff, ApiStaffProfile, ApiSubscriptionPlan, ApiPayment, ApiStudentSubscription, OperationsBundle, InvitationStatus, ApiGroupSchedule, ApiLessonSession, ApiAttendance, ApiGroupMemberDetail, ApiGroupDetail, ApiPaymentReminder, ApiStudentAttendanceHistoryItem, ApiGroupRosterStudent, TeachingBundle, OverviewReport, ApiAuditEvent } from "./api/types";
export type { Membership, AuthUser, Session, StudentAvailabilitySlot, IntakeDuplicateMatch, WorkspaceLead, WorkspaceStudent, WorkspaceGroup, WorkspaceBundle, ApiLocation, ApiStaff, ApiStaffProfile, ApiSubscriptionPlan, ApiPayment, ApiStudentSubscription, OperationsBundle, InvitationStatus, ApiGroupSchedule, ApiLessonSession, ApiAttendance, ApiGroupMemberDetail, ApiGroupDetail, ApiPaymentReminder, ApiStudentAttendanceHistoryItem, ApiGroupRosterStudent, TeachingBundle, OverviewReport, ApiAuditEvent } from "./api/types";

export { apiEnabled, loadSession, saveSession, clearSession, apiGet, apiPost, apiPatch, apiPut, apiDelete } from "./api/client";
export { login, refreshMe, changeOrganization, getBootstrapStatus, bootstrapOwner, getInvitationStatus, acceptInvite, resetPassword } from "./api/auth";
import { apiGet, apiPost } from "./api/client";

export function checkIntakeDuplicates(input: {
  child_first_name: string;
  child_age: number;
  phone: string;
  child_phone?: string | null;
}, session: Session) {
  return apiPost<{ matches: IntakeDuplicateMatch[] }>("/intake/duplicate-check", input, session);
}






export async function loadWorkspace(session: Session): Promise<WorkspaceBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  const role = membership?.role;

  const leadsPromise = ["owner", "admin", "manager"].includes(role ?? "")
    ? apiGet<WorkspaceLead[]>("/workspace/leads", session)
    : Promise.resolve([]);

  const studentsPromise = apiGet<WorkspaceStudent[]>("/workspace/students", session);

  const groupsPromise = role === "accountant"
    ? Promise.resolve([])
    : apiGet<WorkspaceGroup[]>("/workspace/groups", session);

  const [leads, students, groups] = await Promise.all([leadsPromise, studentsPromise, groupsPromise]);
  return { leads, students, groups };
}









export async function loadOperations(session: Session): Promise<OperationsBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  const role = membership?.role;

  const operationalAccess = ["owner", "admin", "manager", "teacher"].includes(role ?? "");
  const staffAccess = ["owner", "admin"].includes(role ?? "");
  const financeAccess = ["owner", "admin", "accountant"].includes(role ?? "");

  const locationsPromise = operationalAccess
    ? apiGet<ApiLocation[]>("/locations", session)
    : Promise.resolve([]);

  const staffPromise = staffAccess
    ? apiGet<ApiStaff[]>("/staff", session).then(async (items) => Promise.all(
        items.map((item) => apiGet<ApiStaffProfile>(`/staff/${item.id}/profile`, session))
      ))
    : Promise.resolve([]);

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

export function loadStudentAttendanceHistory(studentId: string, session: Session) {
  return apiGet<ApiStudentAttendanceHistoryItem[]>(`/students/${studentId}/attendance-history`, session);
}


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



export async function loadOverviewReport(session: Session): Promise<OverviewReport | null> {
  return apiGet<OverviewReport>("/reports/overview", session);
}



export function loadAuditEvents(entityType: string, entityId: string, session: Session) {
  const query = new URLSearchParams({ entity_type: entityType, entity_id: entityId, limit: "100" });
  return apiGet<ApiAuditEvent[]>(`/audit-events?${query.toString()}`, session);
}


