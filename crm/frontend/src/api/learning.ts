import { apiDelete, apiGet, apiPatch, apiPost, apiPut, apiUpload } from "./client";
import type { Session } from "./types";

export type LearningMaterial = {
  id: string;
  lesson_id: string;
  title: string;
  kind: "link" | "file";
  url: string | null;
  filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
};

export type CurriculumLesson = {
  id: string;
  organization_id: string;
  position: number;
  title: string;
  outline: string | null;
  materials: LearningMaterial[];
};

export type LearningProgress = {
  lesson_id: string;
  position: number;
  title: string;
  status: "completed" | "missed" | "before_join" | "not_started";
  manual_completion: boolean;
  automatic_completion: boolean;
};

export function loadCurriculum(session: Session) {
  return apiGet<CurriculumLesson[]>("/curriculum-lessons", session);
}

export function saveCurriculumLesson(id: string | null, body: { position?: number; title: string; outline?: string }, session: Session) {
  return id
    ? apiPatch<CurriculumLesson>(`/curriculum-lessons/${id}`, body, session)
    : apiPost<CurriculumLesson>("/curriculum-lessons", body, session);
}

export function removeCurriculumLesson(id: string, session: Session) {
  return apiDelete(`/curriculum-lessons/${id}`, session);
}

export function addMaterialLink(lessonId: string, body: { title: string; url: string }, session: Session) {
  return apiPost<LearningMaterial>(`/curriculum-lessons/${lessonId}/materials/link`, body, session);
}

export function uploadMaterial(lessonId: string, form: FormData, session: Session) {
  return apiUpload<LearningMaterial>(`/curriculum-lessons/${lessonId}/materials/file`, form, session);
}

export function removeMaterial(lessonId: string, materialId: string, session: Session) {
  return apiDelete(`/curriculum-lessons/${lessonId}/materials/${materialId}`, session);
}

export function materialFileUrl(lessonId: string, materialId: string) {
  return `/curriculum-lessons/${lessonId}/materials/${materialId}/file`;
}

export function setGroupBaseline(groupId: string, completedThrough: number, session: Session) {
  return apiPut<{ completed_through: number }>(`/groups/${groupId}/learning-baseline`, { completed_through: completedThrough }, session);
}

export function loadGroupBaseline(groupId: string, session: Session) {
  return apiGet<{ group_id: string; completed_through: number }>(`/groups/${groupId}/learning-baseline`, session);
}

export function assignSessionLesson(sessionId: string, lessonId: string | null, session: Session) {
  return apiPut<{ session_id: string; curriculum_lesson_id: string | null; topic: string; lesson_title: string | null }>(
    `/lesson-sessions/${sessionId}/curriculum-lesson`, { lesson_id: lessonId }, session,
  );
}

export function loadStudentLearningProgress(studentId: string, session: Session) {
  return apiGet<LearningProgress[]>(`/students/${studentId}/learning-progress`, session);
}

export function updateStudentLearningProgress(studentId: string, lessonId: string, completed: boolean, session: Session) {
  return apiPut(`/students/${studentId}/learning-progress/${lessonId}`, { completed }, session);
}
