import type { AvailabilitySlot, AvailabilityWindowDraft } from "../../components/ScheduleEditors";

export function groupAvailabilitySlots(slots: AvailabilitySlot[]): AvailabilityWindowDraft[] {
  const grouped = new Map<string, AvailabilityWindowDraft>();
  slots.forEach((slot) => {
    const preference = slot.preference ?? "preferred";
    const note = slot.note ?? null;
    const key = [slot.start_time.slice(0, 5), slot.end_time.slice(0, 5), preference, note ?? ""].join("|");
    const existing = grouped.get(key);
    if (existing) {
      if (!existing.weekdays.includes(slot.weekday)) existing.weekdays.push(slot.weekday);
      return;
    }
    grouped.set(key, {
      id: `availability-${grouped.size + 1}-${slot.weekday}`,
      weekdays: [slot.weekday],
      start_time: slot.start_time.slice(0, 5),
      end_time: slot.end_time.slice(0, 5),
      preference,
      note,
    });
  });
  return [...grouped.values()].map((window) => ({ ...window, weekdays: [...window.weekdays].sort((a, b) => a - b) }));
}


export function flattenAvailabilityWindows(windows: AvailabilityWindowDraft[]): AvailabilitySlot[] {
  return windows.flatMap((window) =>
    [...new Set(window.weekdays)].sort((a, b) => a - b).map((weekday) => ({
      weekday,
      start_time: window.start_time,
      end_time: window.end_time,
      preference: window.preference,
      note: window.note ?? null,
    }))
  );
}


export function availabilityLabel(slots: AvailabilitySlot[]) {
  if (!slots.length) return "Не вказано";
  const dayNames = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];
  const groups = new Map<string, string[]>();
  slots.forEach((slot) => {
    const key = `${slot.start_time.slice(0, 5)}–${slot.end_time.slice(0, 5)}`;
    const days = groups.get(key) ?? [];
    days.push(dayNames[slot.weekday] ?? "?");
    groups.set(key, days);
  });
  return [...groups.entries()].map(([time, days]) => `${days.join("/")} · ${time}`).join("; ");
}


