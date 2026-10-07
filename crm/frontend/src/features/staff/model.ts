import type { EntityId } from "../leads/model";

export type StaffRoleDemo = "Власник" | "Адміністратор" | "Менеджер" | "Викладач" | "Бухгалтер";

export type StaffDemo = {
  id: EntityId;
  fullName: string;
  role: StaffRoleDemo;
  canTeach: boolean;
  email: string;
  phone: string;
  locationIds: EntityId[];
  groupIds: EntityId[];
  isActive: boolean;
};

export function staffRoleLabel(role: string): StaffRoleDemo {
  const labels: Record<string, StaffRoleDemo> = {
    owner: "Власник",
    admin: "Адміністратор",
    manager: "Менеджер",
    teacher: "Викладач",
    accountant: "Бухгалтер",
  };
  return labels[role] ?? "Викладач";
}


export function staffRoleValue(role: StaffRoleDemo) {
  const values: Record<StaffRoleDemo, string> = {
    "Власник": "owner",
    "Адміністратор": "admin",
    "Менеджер": "manager",
    "Викладач": "teacher",
    "Бухгалтер": "accountant",
  };
  return values[role];
}

