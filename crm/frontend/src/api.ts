export type Membership = {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
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
      message = body.detail ?? message;
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
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as Session : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession() {
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


export type WorkspaceLead = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  age: number | null;
  source: string | null;
  crm_status: "new" | "contacted" | "trial_scheduled" | "trial_completed" | "waiting_for_group" | "enrolled" | "no_response" | "declined" | "not_relevant";
  contact_name: string | null;
  contact_phone: string | null;
  latest_trial_at: string | null;
  recommended_level: string | null;
};

export type WorkspaceStudent = {
  student_id: string;
  first_name: string;
  last_name: string | null;
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
};

export type WorkspaceBundle = {
  leads: WorkspaceLead[];
  students: WorkspaceStudent[];
  groups: WorkspaceGroup[];
};

export async function loadWorkspace(session: Session): Promise<WorkspaceBundle> {
  const [leads, students, groups] = await Promise.all([
    apiGet<WorkspaceLead[]>("/workspace/leads", session),
    apiGet<WorkspaceStudent[]>("/workspace/students", session),
    apiGet<WorkspaceGroup[]>("/workspace/groups", session),
  ]);
  return { leads, students, groups };
}
