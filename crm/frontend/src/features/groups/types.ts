import type { EntityId } from "../leads/model";

export type GroupItem = {
  id: EntityId;
  name: string;
  ages: string;
  schedule: string;
  location: string;
  capacity: number;
  members: EntityId[];
  memberCount?: number;
  teacherName?: string;
};
