import type { Dispatch, SetStateAction } from "react";
import type { TeachingBundle } from "../../api";
import type { EntityId } from "../leads/model";
import type { GroupItem } from "../groups/types";

export type LessonItem = {
  id: EntityId;
  groupId: EntityId;
  startsAt: string;
  duration: number;
  topic: string;
  notes?: string;
  status?: "scheduled" | "completed" | "cancelled";
  attendancePresent?: number;
  attendanceAbsent?: number;
  attendanceLate?: number;
  attendanceExcused?: number;
  attendanceTotal?: number;
};

export const SCHEDULE_DAY_NAMES = ["Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя"];

export function applyTeaching(
  bundle: TeachingBundle,
  setLessons: Dispatch<SetStateAction<LessonItem[]>>,
  setGroups: Dispatch<SetStateAction<GroupItem[]>>,
) {
  setLessons(bundle.lessons.map((item) => ({
    id: item.id,
    groupId: item.group_id,
    startsAt: item.starts_at,
    duration: item.duration_minutes,
    topic: item.topic ?? "Заняття",
    notes: item.notes ?? undefined,
    status: item.status,
    attendancePresent: item.attendance_present,
    attendanceAbsent: item.attendance_absent,
    attendanceLate: item.attendance_late,
    attendanceExcused: item.attendance_excused,
    attendanceTotal: item.attendance_total,
  })));

  const byGroup = new Map<EntityId, TeachingBundle["schedules"]>();
  bundle.schedules.forEach((item) => {
    const list = byGroup.get(item.group_id) ?? [];
    list.push(item);
    byGroup.set(item.group_id, list);
  });

  setGroups((items) => items.map((group) => {
    const schedules = byGroup.get(group.id) ?? [];
    return {
      ...group,
      schedule: schedules.length ? scheduleLabel(schedules) : "Розклад не задано",
    };
  }));
}


export function scheduleLabel(items: TeachingBundle["schedules"]) {
  return [...items]
    .sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time))
    .map((item) => `${SCHEDULE_DAY_NAMES[item.weekday] ?? "Невідомий день"} · ${item.start_time.slice(0, 5)}`)
    .join("; ");
}

