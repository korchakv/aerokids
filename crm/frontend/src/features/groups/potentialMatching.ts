import type { Lead } from "../leads/model";
import type { PotentialGroupMemberDraft, PotentialGroupSlotDraft } from "./potentialGroups";

export const DAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя"];
export const toMinutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5));
export const clock = (value: number) => `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
export const memberKey = (members: PotentialGroupMemberDraft[]) => members.map((m) => m.student_id).sort().join("|");
export const slotLabel = (slot: PotentialGroupSlotDraft) => `${DAYS[slot.weekday]} ${slot.start_time.slice(0, 5)}–${slot.end_time.slice(0, 5)}`;

export function availabilitySnapshot(lead: Lead) {
  return (lead.availability ?? []).map((item) => ({
    weekday: item.weekday, start_time: item.start_time.slice(0, 5), end_time: item.end_time.slice(0, 5),
    preference: item.preference ?? "preferred", note: item.note ?? null,
  })).sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time) || a.end_time.localeCompare(b.end_time) || a.preference.localeCompare(b.preference));
}

export function matchSlot(lead: Lead | undefined, slot: PotentialGroupSlotDraft, toleranceHours = 2): "preferred" | "possible" | "approximate" | "conflict" | "unknown" {
  if (!lead || !(lead.availability ?? []).some((w) => w.preference !== "avoid")) return "unknown";
  const start = toMinutes(slot.start_time), end = toMinutes(slot.end_time);
  const windows = (lead.availability ?? []).filter((w) => w.weekday === slot.weekday);
  if (windows.some((w) => w.preference === "avoid" && start < toMinutes(w.end_time) && end > toMinutes(w.start_time))) return "conflict";
  const fits = windows.filter((w) => w.preference !== "avoid" && start >= toMinutes(w.start_time) && end <= toMinutes(w.end_time));
  if (fits.some((w) => w.preference !== "possible")) return "preferred";
  if (fits.length) return "possible";
  if (windows.some((w) => w.preference !== "avoid" && start >= toMinutes(w.start_time) - toleranceHours * 60 && end <= toMinutes(w.end_time) + toleranceHours * 60)) return "approximate";
  return "conflict";
}

export function commonSlots(leads: Lead[], toleranceHours = 2): PotentialGroupSlotDraft[] {
  if (!leads.length) return [];
  const slots: PotentialGroupSlotDraft[] = [];
  for (let weekday = 0; weekday < 7; weekday++) {
    for (let start = 8 * 60; start <= 21 * 60; start += 15) {
      const slot = { weekday, start_time: clock(start), end_time: clock(start + 60), exact_match: false };
      const matches = leads.map((lead) => matchSlot(lead, slot, toleranceHours));
      if (matches.every((m) => m !== "unknown" && m !== "conflict")) slots.push({ ...slot, exact_match: matches.every((m) => m !== "approximate") });
    }
  }
  return slots;
}

export function availabilityRanges(slots: PotentialGroupSlotDraft[]) {
  const ranges: PotentialGroupSlotDraft[] = [];
  for (const slot of [...slots].sort((a, b) => a.weekday - b.weekday || Number(b.exact_match) - Number(a.exact_match) || a.start_time.localeCompare(b.start_time))) {
    const last = ranges[ranges.length - 1];
    // Merge only adjacent valid starts, never bridge a gap or an avoided period.
    if (last && last.weekday === slot.weekday && last.exact_match === slot.exact_match && toMinutes(slot.start_time) <= toMinutes(last.end_time) - 45) last.end_time = slot.end_time;
    else ranges.push({ ...slot });
  }
  return ranges;
}

export function suggestedSchedule(slots: PotentialGroupSlotDraft[]) {
  const best = [...slots].sort((a, b) => Number(b.exact_match) - Number(a.exact_match) || a.weekday - b.weekday || a.start_time.localeCompare(b.start_time));
  const chosen: PotentialGroupSlotDraft[] = [];
  for (const slot of best) if (!chosen.some((s) => s.weekday === slot.weekday) && chosen.length < 2) chosen.push(slot);
  return chosen.sort((a, b) => a.weekday - b.weekday);
}

export function generatePotentialGroups(candidates: Lead[], toleranceHours = 2, ageSpread = 3): Array<{ members: PotentialGroupMemberDraft[]; slots: PotentialGroupSlotDraft[] }> {
  const eligible = candidates.filter((lead) => lead.age > 0 && (lead.availability ?? []).some((slot) => slot.preference !== "avoid"));
  const byMembers = new Map<string, { members: PotentialGroupMemberDraft[]; slots: PotentialGroupSlotDraft[] }>();
  for (let weekday = 0; weekday < 7; weekday++) for (let start = 8 * 60; start <= 21 * 60; start += 15) {
    const slot = { weekday, start_time: clock(start), end_time: clock(start + 60), exact_match: false };
    const compatible = eligible.filter((lead) => !["unknown", "conflict"].includes(matchSlot(lead, slot, toleranceHours)));
    const locations = [...new Set(compatible.map((lead) => lead.preferredLocationId).filter(Boolean))];
    for (const location of locations.length ? locations : [undefined]) {
      const local = compatible.filter((lead) => !lead.preferredLocationId || lead.preferredLocationId === location).sort((a, b) => a.age - b.age || a.id.localeCompare(b.id));
      for (const age of [...new Set(local.map((l) => l.age))]) {
        const sameAge = local.filter((l) => l.age >= age && l.age <= age + ageSpread);
        const count = sameAge.length > 8 ? Math.ceil(sameAge.length / 6) : 1;
        const size = Math.ceil(sameAge.length / count);
        for (let i = 0; i < sameAge.length; i += Math.max(size, 1)) {
          const group = sameAge.slice(i, i + size);
          if (group.length < 2) continue;
          const members = group.map((lead) => ({ student_id: lead.id, response: "not_contacted" as const, availability_snapshot: availabilitySnapshot(lead) }));
          const key = memberKey(members);
          if (!byMembers.has(key)) byMembers.set(key, { members, slots: [] });
          const proposal = byMembers.get(key)!;
          if (!proposal.slots.some((s) => s.weekday === weekday && s.start_time === slot.start_time)) proposal.slots.push({ ...slot, exact_match: group.every((lead) => ["preferred", "possible"].includes(matchSlot(lead, slot, toleranceHours))) });
        }
      }
    }
  }
  const result = [...byMembers.values()];
  return result.filter((p) => !result.some((other) => other.members.length > p.members.length && p.members.every((m) => other.members.some((n) => n.student_id === m.student_id)) && p.slots.every((s) => other.slots.some((t) => t.weekday === s.weekday && t.start_time === s.start_time && (!s.exact_match || t.exact_match)))))
    .sort((a, b) => Math.min(2, new Set(b.slots.filter((s) => s.exact_match).map((s) => s.weekday)).size) - Math.min(2, new Set(a.slots.filter((s) => s.exact_match).map((s) => s.weekday)).size) || Math.abs(a.members.length - 6) - Math.abs(b.members.length - 6) || b.members.length - a.members.length)
    .slice(0, 12);
}

export function hasAvailabilityChanged(snapshot: PotentialGroupMemberDraft["availability_snapshot"], lead: Lead | undefined) {
  if (!lead) return true;
  return JSON.stringify(availabilitySnapshot({ ...lead, availability: snapshot })) !== JSON.stringify(availabilitySnapshot(lead));
}
