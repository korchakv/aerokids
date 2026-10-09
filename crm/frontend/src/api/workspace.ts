import type { PageResult, Session, WorkspaceBundle, WorkspaceGroup, WorkspaceLead, WorkspaceStudent } from "./types";
import { apiGet } from "./client";

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

function queryString(entries: Record<string, string | number | undefined | null>) {
  const params = new URLSearchParams();
  Object.entries(entries).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      params.set(key, String(value));
    }
  });
  const value = params.toString();
  return value ? `?${value}` : "";
}

export type StudentPageOptions = {
  q?: string;
  status?: "active" | "paused" | "archived";
  sort?: "name" | "newest" | "oldest";
  limit?: number;
  offset?: number;
};

export type GroupPageOptions = {
  q?: string;
  sort?: "name" | "size_desc" | "size_asc";
  limit?: number;
  offset?: number;
};

export function loadWorkspaceStudentsPage(
  session: Session,
  options: StudentPageOptions = {},
): Promise<PageResult<WorkspaceStudent>> {
  return apiGet<PageResult<WorkspaceStudent>>(
    `/workspace/students/page${queryString(options)}`,
    session,
  );
}

export function loadWorkspaceGroupsPage(
  session: Session,
  options: GroupPageOptions = {},
): Promise<PageResult<WorkspaceGroup>> {
  return apiGet<PageResult<WorkspaceGroup>>(
    `/workspace/groups/page${queryString(options)}`,
    session,
  );
}
