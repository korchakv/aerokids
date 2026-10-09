import type { Dispatch, SetStateAction } from "react";
import type { WorkspaceBundle, WorkspaceGroup, WorkspaceStudent } from "../../api";
import type { GroupItem } from "../groups/types";
import type { EntityId, Lead, LeadStatus } from "../leads/model";


export function workspaceStudentToLead(item: WorkspaceStudent): Lead {
  return {
    id: item.student_id,
    firstName: item.first_name,
    lastName: item.last_name ?? undefined,
    child: [item.first_name, item.last_name].filter(Boolean).join(" "),
    age: item.age ?? 0,
    parent: item.contact_name ?? "Контакт не вказано",
    phone: item.contact_phone ?? "",
    childPhone: item.student_phone ?? undefined,
    source: item.source ?? "CRM",
    status: "Зарахований",
    groupId: item.group_id ?? undefined,
    groupName: item.group_name ?? undefined,
  };
}

export function workspaceStudentLifecycle(item: WorkspaceStudent): "Активний" | "Пауза" | "Архів" {
  return item.student_status === "paused" ? "Пауза" : item.student_status === "archived" ? "Архів" : "Активний";
}

export function workspaceGroupToGroupItem(group: WorkspaceGroup, members: EntityId[] = []): GroupItem {
  return {
    id: group.group_id,
    name: group.name,
    ages: ageLabel(group.min_age, group.max_age),
    schedule: "Розклад не задано",
    location: group.location_name ?? "Локацію не вказано",
    capacity: group.capacity ?? Math.max(group.enrolled_count, 1),
    members,
    memberCount: group.enrolled_count,
    teacherName: group.primary_teacher_name ?? undefined,
  };
}

export function applyWorkspace(
  bundle: WorkspaceBundle,
  setLeads: Dispatch<SetStateAction<Lead[]>>,
  setGroups: Dispatch<SetStateAction<GroupItem[]>>,
  setStudentStates: Dispatch<SetStateAction<Record<EntityId, "Активний" | "Пауза" | "Архів">>>,
) {
  const prospects: Lead[] = bundle.leads.map((item) => ({
    id: item.student_id,
    createdAt: item.created_at,
    firstName: item.first_name,
    lastName: item.last_name ?? undefined,
    child: [item.first_name, item.last_name].filter(Boolean).join(" "),
    age: item.age ?? 0,
    parent: item.contact_name ?? "Контакт не вказано",
    phone: item.contact_phone ?? "",
    childPhone: item.student_phone ?? undefined,
    source: item.source ?? "CRM",
    comment: item.comment ?? undefined,
    preferredLocationId: item.preferred_location_id ?? undefined,
    preferredLocationName: item.preferred_location_name ?? undefined,
    availability: item.availability.map((slot) => ({
      weekday: slot.weekday,
      start_time: slot.start_time.slice(0, 5),
      end_time: slot.end_time.slice(0, 5),
      preference: slot.preference ?? "preferred",
      note: slot.note,
    })),
    status: crmStatusLabel(item.crm_status),
    trialId: item.latest_trial_id ?? undefined,
    trialAt: item.latest_trial_at ?? undefined,
    trialLocationId: item.trial_location_id ?? undefined,
    trialLocation: item.trial_location_name ?? undefined,
    recommendedLevel: item.recommended_level ?? undefined,
    teacherNotes: item.teacher_notes ?? undefined,
    trialResult: item.latest_trial_status ?? undefined,
    nextContactAt: item.next_contact_at ?? undefined,
    deferredUntil: item.deferred_until ?? undefined,
    deferredReason: item.deferred_reason ?? undefined,
    deferredNote: item.deferred_note ?? undefined,
    closeReason: item.close_reason ?? undefined,
    closeNote: item.close_note ?? undefined,
  }));

  const students: Lead[] = bundle.students.map(workspaceStudentToLead);

  const states: Record<EntityId, "Активний" | "Пауза" | "Архів"> = {};
  bundle.students.forEach((item) => {
    states[item.student_id] = workspaceStudentLifecycle(item);
  });

  const groups: GroupItem[] = bundle.groups.map((group) =>
    workspaceGroupToGroupItem(
      group,
      bundle.students.filter((student) => student.group_id === group.group_id).map((student) => student.student_id),
    )
  );

  setLeads([...prospects, ...students]);
  setGroups(groups);
  setStudentStates(states);
}


export function crmStatusValue(status: LeadStatus) {
  const values: Record<LeadStatus, string> = {
    "Нова": "new",
    "Зв'язались": "contacted",
    "Пробне заплановано": "trial_scheduled",
    "Після пробного": "trial_completed",
    "Очікує групу": "waiting_for_group",
    "Зарахований": "enrolled",
    "Не відповідає": "no_response",
    "Відмовились": "declined",
    "Неактуально": "not_relevant",
  };
  return values[status];
}


export function crmStatusLabel(status: WorkspaceBundle["leads"][number]["crm_status"]): LeadStatus {
  const labels: Record<WorkspaceBundle["leads"][number]["crm_status"], LeadStatus> = {
    new: "Нова",
    contacted: "Зв'язались",
    trial_scheduled: "Пробне заплановано",
    trial_completed: "Після пробного",
    waiting_for_group: "Очікує групу",
    enrolled: "Зарахований",
    no_response: "Не відповідає",
    declined: "Відмовились",
    not_relevant: "Неактуально",
  };
  return labels[status];
}


export function ageLabel(min: number | null, max: number | null) {
  if (min == null && max == null) return "—";
  if (min != null && max != null) return min === max ? String(min) : `${min}–${max}`;
  return String(min ?? max);
}

