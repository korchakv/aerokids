import type { Session, WorkspaceBundle, WorkspaceGroup, WorkspaceLead, WorkspaceStudent } from "./types";
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
