import type { EntityId } from "../leads/model";

export type LocationDemo = {
  id: EntityId;
  name: string;
  address: string;
  isActive: boolean;
};
