import type { OverviewReport, Session } from "./types";
import { apiGet } from "./client";

export async function loadOverviewReport(session: Session): Promise<OverviewReport | null> {
  return apiGet<OverviewReport>("/reports/overview", session);
}
