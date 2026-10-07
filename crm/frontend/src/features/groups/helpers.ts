import type { DraftScheduleSlot } from "../../components/ScheduleEditors";
import type { Lead } from "../leads/model";
import type { GroupItem } from "./types";
import { SCHEDULE_DAY_NAMES } from "../teaching/model";

export function scheduleDraftLabel(slots: DraftScheduleSlot[]) { return slots.map((slot) => `${SCHEDULE_DAY_NAMES[slot.weekday] ?? "Невідомий день"} · ${slot.start_time.slice(0, 5)}`).join("; "); }

export function hasDuplicateSlots(slots: DraftScheduleSlot[]) { return new Set(slots.map((slot) => `${slot.weekday}:${slot.start_time}`)).size !== slots.length; }


export function scheduleSlots(group: GroupItem) {
  if (!group.schedule || group.schedule === "Розклад не задано") return [];
  return group.schedule.split(";").flatMap((part) => {
    const [daysPart, timePart] = part.split("·").map((x) => x.trim());
    const time = timePart || "—";
    return (daysPart || "").split("/").map((day) => ({ day: day.trim(), time })).filter((item) => item.day);
  });
}


export function ageRange(items: Lead[]) {
  const ages = items.map((x) => x.age);
  if (!ages.length) return "—";
  const min = Math.min(...ages);
  const max = Math.max(...ages);
  return min === max ? String(min) : min + "–" + max;
}


