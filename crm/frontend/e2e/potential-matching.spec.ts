import { expect, test } from "@playwright/test";
import { availabilityRanges, commonSlots, generatePotentialGroups, matchSlot, suggestedSchedule } from "../src/features/groups/potentialMatching";
import type { Lead } from "../src/features/leads/model";
const lead = (id: string, age = 10, location?: string): Lead => ({ id, child: id, age, parent: "Parent", phone: "", source: "", status: "Очікує групу", preferredLocationId: location, availability: [1, 3].map((weekday) => ({ weekday, start_time: "17:00", end_time: "19:00", preference: "preferred" })) });

test("matching preserves both weekdays and compresses alternative starts", () => {
  const proposals = generatePotentialGroups([lead("a"), lead("b")], 2);
  expect(proposals).toHaveLength(1);
  expect(suggestedSchedule(proposals[0].slots).map((s) => s.weekday)).toEqual([1, 3]);
  const ranges = availabilityRanges(commonSlots([lead("a"), lead("b")], 0));
  expect(ranges).toHaveLength(2);
  expect(ranges[0]).toMatchObject({ start_time: "17:00", end_time: "19:00" });
});

test("avoided periods override broad availability and never bridge gaps", () => {
  const a = lead("a");
  a.availability!.push({ weekday: 1, start_time: "18:00", end_time: "18:30", preference: "avoid" });
  expect(matchSlot(a, { weekday: 1, start_time: "17:30", end_time: "18:30", exact_match: false }, 2)).toBe("conflict");
  const slots = commonSlots([a, lead("b")], 0).filter((s) => s.weekday === 1);
  expect(slots.map((s) => s.start_time)).toEqual(["17:00"]);
});

test("age and location separate students; unknown availability is not free time", () => {
  const unknown = { ...lead("unknown"), availability: [] };
  const proposals = generatePotentialGroups([lead("a", 8, "one"), lead("b", 9, "one"), lead("c", 14, "one"), lead("d", 15, "one"), lead("e", 9, "two"), unknown]);
  expect(proposals.map((p) => p.members.map((m) => m.student_id).sort())).toEqual(expect.arrayContaining([["a", "b"], ["c", "d"]]));
  expect(proposals.every((p) => !p.members.some((m) => ["unknown", "e"].includes(m.student_id)))).toBeTruthy();
});
