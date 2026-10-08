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

export type WorkspacePageOptions = {
  q?: string;
  limit?: number;
  offset?: number;
  sort?: string;
  order?: "asc" | "desc";
};

function workspacePageQuery(options: WorkspacePageOptions = {}): string {
  const params = new URLSearchParams();
  if (options.q?.trim()) params.set("q", options.q.trim());
  if (options.limit != null) params.set("limit", String(options.limit));
  if (options.offset != null) params.set("offset", String(options.offset));
  if (options.sort) params.set("sort", options.sort);
  if (options.order) params.set("order", options.order);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function loadWorkspaceLeadsPage(
  session: Session,
  options: WorkspacePageOptions = {},
): Promise<PageResult<WorkspaceLead>> {
  return apiGet<PageResult<WorkspaceLead>>(`/workspace/leads-page${workspacePageQuery(options)}`, session);
}

export function loadWorkspaceStudentsPage(
  session: Session,
  options: WorkspacePageOptions = {},
): Promise<PageResult<WorkspaceStudent>> {
  return apiGet<PageResult<WorkspaceStudent>>(`/workspace/students-page${workspacePageQuery(options)}`, session);
}

export function loadWorkspaceGroupsPage(
  session: Session,
  options: WorkspacePageOptions = {},
): Promise<PageResult<WorkspaceGroup>> {
  return apiGet<PageResult<WorkspaceGroup>>(`/workspace/groups-page${workspacePageQuery(options)}`, session);
}

