import type { AvailabilitySlot } from "../../components/ScheduleEditors";

export type PotentialResponse = "not_contacted" | "awaiting" | "agreed" | "declined" | "other_time" | "reconfirm";
export type PotentialGroupMemberDraft = {
  student_id: string;
  response: PotentialResponse;
  availability_snapshot: AvailabilitySlot[];
  note?: string;
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
  selected_slots: PotentialGroupSlotDraft[];
  schedule_history: Array<{ at: string; before: PotentialGroupSlotDraft[]; after: PotentialGroupSlotDraft[]; responses?: Array<{student_id: string; response: PotentialResponse}>; after_responses?: Array<{student_id: string; response: PotentialResponse}> }>;
  version: number;
  formed_group_id?: string | null;
  stale: boolean;
};
