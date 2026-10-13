import type { AvailabilitySlot } from "../../components/ScheduleEditors";

export type PotentialResponse = "not_contacted" | "awaiting" | "agreed" | "declined";
export type PotentialGroupMemberDraft = {
  student_id: string;
  response: PotentialResponse;
  availability_snapshot: AvailabilitySlot[];
};
export type PotentialGroupSlotDraft = {
  weekday: number;
  start_time: string;
  end_time: string;
  exact_match: boolean;
};
export type PotentialGroupProposal = {
  id: string;
  created_at: string;
  updated_at: string;
  members: PotentialGroupMemberDraft[];
  slots: PotentialGroupSlotDraft[];
  stale: boolean;
};
