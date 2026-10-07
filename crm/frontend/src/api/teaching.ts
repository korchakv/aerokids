import type {
  ApiAttendance,
  ApiGroupDetail,
  ApiGroupRosterStudent,
  ApiGroupSchedule,
  ApiLessonSession,
  ApiStudentAttendanceHistoryItem,
  Session,
  TeachingBundle,
} from "./types";
import { apiGet } from "./client";

export function loadStudentAttendanceHistory(studentId: string, session: Session) {
  return apiGet<ApiStudentAttendanceHistoryItem[]>(`/students/${studentId}/attendance-history`, session);
}

export function loadGroupRoster(groupId: string, session: Session) {
  return apiGet<ApiGroupRosterStudent[]>(`/groups/${groupId}/roster`, session);
}

export function loadGroupDetail(groupId: string, session: Session) {
  return apiGet<ApiGroupDetail>(`/groups/${groupId}/detail`, session);
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
