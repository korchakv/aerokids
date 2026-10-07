import type { AuthUser, InvitationStatus, Session } from "./types";
import { request, saveSession } from "./client";

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
