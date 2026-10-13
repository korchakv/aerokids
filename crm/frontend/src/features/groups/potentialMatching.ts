import type { Lead } from "../leads/model";
import type { AvailabilitySlot } from "../../components/ScheduleEditors";
import type { PotentialGroupMemberDraft, PotentialGroupSlotDraft } from "./potentialGroups";

const LESSON_MINUTES = 60;

function toMinutes(value: string) {
  const [hours, minutes] = value.slice(0, 5).split(":").map(Number);
  return hours * 60 + minutes;
}

function clock(value: number) {
  const normalized = ((value % 1440) + 1440) % 1440;
  return `${String(Math.floor(normalized / 60)).padStart(2, "0")}:${String(normalized % 60).padStart(2, "0")}`;
}

export function availabilitySnapshot(lead: Lead) {
  return (lead.availability ?? []).map((item) => ({
    weekday: item.weekday,
    start_time: item.start_time.slice(0, 5),
    end_time: item.end_time.slice(0, 5),
    preference: item.preference ?? "preferred",
    note: item.note ?? null,
  })).sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time) || a.end_time.localeCompare(b.end_time));
}

export function generatePotentialGroups(waiting: Lead[], toleranceHours = 2): Array<{ members: PotentialGroupMemberDraft[]; slots: PotentialGroupSlotDraft[] }> {
  const withAvailability = waiting.filter((lead) => (lead.availability ?? []).some((slot) => slot.preference !== "avoid"));
  const toleranceMinutes = Math.max(0, Math.min(4, toleranceHours)) * 60;
  const byMembers = new Map<string, { members: PotentialGroupMemberDraft[]; slots: PotentialGroupSlotDraft[] }>();

  for (let weekday = 0; weekday < 7; weekday += 1) {
    for (let start = 8 * 60; start <= 20 * 60 + 45; start += 30) {
      const compatible = withAvailability.map((lead) => {
        const windows = (lead.availability ?? []).filter((slot) => slot.weekday === weekday && slot.preference !== "avoid");
        const windowsForStart = windows.filter((window) => {
          const from = toMinutes(window.start_time);
          const until = toMinutes(window.end_time);
          return start >= from - toleranceMinutes && start <= until - LESSON_MINUTES + toleranceMinutes;
        });
        if (!windowsForStart.length) return null;
        const exact = windowsForStart.some((window) => start >= toMinutes(window.start_time) && start + LESSON_MINUTES <= toMinutes(window.end_time));
        return { lead, exact };
      }).filter((item): item is { lead: Lead; exact: boolean } => Boolean(item));

      if (compatible.length < 2) continue;
      compatible.sort((a, b) => Number(b.exact) - Number(a.exact) || a.lead.child.localeCompare(b.lead.child, "uk-UA"));

      // Prefer balanced, non-overlapping groups; then retain overlapping alternatives.
      const slices: typeof compatible[] = [];
      const groupCount = Math.ceil(compatible.length / 8);
      const baseSize = Math.floor(compatible.length / groupCount);
      const largerGroupCount = compatible.length % groupCount;
      let cursor = 0;
      for (let groupIndex = 0; groupIndex < groupCount; groupIndex += 1) {
        const size = baseSize + (groupIndex < largerGroupCount ? 1 : 0);
        const slice = compatible.slice(cursor, cursor + size);
        cursor += size;
        if (slice.length >= 2) slices.push(slice);
      }
      // Keep a few overlapping alternatives after the balanced first pass.
      for (let offset = 0; offset + 2 < compatible.length && slices.length < 6; offset += 4) {
        const slice = compatible.slice(offset, offset + 8);
        if (slice.length >= 2) slices.push(slice);
      }

      for (const slice of slices) {
        const ids = slice.map(({ lead }) => lead.id).sort();
        const key = ids.join("|");
        let proposal = byMembers.get(key);
        if (!proposal) {
          proposal = {
            members: slice.map(({ lead }) => ({ student_id: lead.id, response: "not_contacted", availability_snapshot: availabilitySnapshot(lead) })),
            slots: [],
          };
          byMembers.set(key, proposal);
        }
        if (proposal.slots.length < 14) {
          const candidate = {
            weekday,
            start_time: clock(start),
            end_time: clock(start + LESSON_MINUTES),
            exact_match: slice.every((item) => item.exact),
          };
          if (!proposal.slots.some((slot) => slot.weekday === candidate.weekday && slot.start_time === candidate.start_time)) proposal.slots.push(candidate);
        }
      }
    }
  }

  return [...byMembers.values()]
    .filter((proposal) => proposal.slots.length > 0)
    .sort((a, b) => b.members.length - a.members.length || b.slots.filter((slot) => slot.exact_match).length - a.slots.filter((slot) => slot.exact_match).length)
    .slice(0, 40);
}

export function hasAvailabilityChanged(snapshot: PotentialGroupMemberDraft["availability_snapshot"], lead: Lead | undefined) {
  if (!lead || lead.status !== "Очікує групу") return true;
  const normalizedSnapshot = snapshot.map((item) => ({
    weekday: item.weekday,
    start_time: item.start_time.slice(0, 5),
    end_time: item.end_time.slice(0, 5),
    preference: item.preference ?? "preferred",
    note: item.note ?? null,
  })).sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time) || a.end_time.localeCompare(b.end_time));
  return JSON.stringify(normalizedSnapshot) !== JSON.stringify(availabilitySnapshot(lead));
}

export function findSharedDayNeedsCoordination(waiting: Lead[], toleranceHours = 2) {
  const tolerance = Math.max(0, Math.min(4, toleranceHours)) * 60;
  const pairs: Array<[Lead, Lead, number]> = [];
  for (let firstIndex = 0; firstIndex < waiting.length; firstIndex += 1) {
    const first = waiting[firstIndex];
    for (let secondIndex = firstIndex + 1; secondIndex < waiting.length; secondIndex += 1) {
      const second = waiting[secondIndex];
      let closestGap = Number.POSITIVE_INFINITY;
      let hasSharedDay = false;
      let hasPossibleTime = false;
      const dayWindows: Array<[AvailabilitySlot, AvailabilitySlot]> = [];
      for (const a of first.availability ?? []) {
        if (a.preference === "avoid") continue;
        for (const b of second.availability ?? []) {
          if (b.preference === "avoid" || a.weekday !== b.weekday) continue;
          hasSharedDay = true;
          dayWindows.push([a, b]);
          const gap = Math.max(toMinutes(a.start_time) - toMinutes(b.end_time), toMinutes(b.start_time) - toMinutes(a.end_time), 0);
          closestGap = Math.min(closestGap, gap);
        }
      }
      if (hasSharedDay) {
        for (let start = 8 * 60; start <= 20 * 60 + 45; start += 30) {
          const accepts = (window: (typeof dayWindows)[number][0]) => start >= toMinutes(window.start_time) - tolerance && start <= toMinutes(window.end_time) - LESSON_MINUTES + tolerance;
          if (dayWindows.some(([a, b]) => accepts(a) && accepts(b))) { hasPossibleTime = true; break; }
        }
      }
      if (hasSharedDay && !hasPossibleTime) pairs.push([first, second, closestGap]);
    }
  }
  return pairs.sort((a, b) => a[2] - b[2]);
}
