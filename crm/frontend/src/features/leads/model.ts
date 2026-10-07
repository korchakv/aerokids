import type { AvailabilitySlot } from "../../components/ScheduleEditors";
import { cleanSpaces } from "../../utils/contact";
import { dateValue } from "../../utils/date";

export type LeadStatus = "Нова" | "Зв'язались" | "Пробне заплановано" | "Після пробного" | "Очікує групу" | "Зарахований" | "Не відповідає" | "Відмовились" | "Неактуально";

export type EntityId = string;

export type LeadKanbanColumnId = "new" | "contacted" | "trial" | "no_show" | "after_trial" | "waiting" | "deferred" | "closed";

export const leadKanbanColumns: Array<{ id: LeadKanbanColumnId; title: string; hint: string }> = [
  { id: "new", title: "Нові", hint: "Перший контакт" },
  { id: "contacted", title: "Зв’язались", hint: "В роботі" },
  { id: "trial", title: "Пробне", hint: "Заплановано" },
  { id: "no_show", title: "Не прийшов", hint: "Потрібна дія" },
  { id: "after_trial", title: "Після пробного", hint: "Очікуємо рішення" },
  { id: "waiting", title: "Очікує групу", hint: "Готовий до набору" },
  { id: "deferred", title: "Повернутись пізніше", hint: "Нагадування на майбутнє" },
  { id: "closed", title: "Закриті", hint: "Відмова / неактуально" },
];
export type Lead = {
  id: EntityId;
  createdAt?: string;
  firstName?: string;
  lastName?: string;
  child: string;
  age: number;
  parent: string;
  phone: string;
  childPhone?: string;
  source: string;
  status: LeadStatus;
  comment?: string;
  preferredLocationId?: string;
  preferredLocationName?: string;
  availability?: AvailabilitySlot[];
  trialId?: string;
  trialAt?: string;
  trialLocationId?: string;
  trialLocation?: string;
  trialResult?: "scheduled" | "completed" | "no_show" | "cancelled";
  recommendedLevel?: string;
  teacherNotes?: string;
  nextContactAt?: string;
  deferredUntil?: string;
  deferredReason?: string;
  deferredNote?: string;
  closeReason?: string;
  closeNote?: string;
};function leadIsDeferred(lead: Lead): boolean {
  return Boolean(lead.deferredUntil && dateValue(lead.deferredUntil) > Date.now());
}


export function leadKanbanColumn(lead: Lead): LeadKanbanColumnId {
  if (["Відмовились", "Не відповідає", "Неактуально"].includes(lead.status)) return "closed";
  if (leadIsDeferred(lead)) return "deferred";
  if (lead.trialResult === "no_show" && lead.status === "Зв'язались") return "no_show";
  if (lead.status === "Після пробного") return "after_trial";
  if (lead.status === "Пробне заплановано") return "trial";
  if (lead.status === "Очікує групу") return "waiting";
  if (lead.status === "Нова") return "new";
  return "contacted";
}


export function leadUrgency(lead: Lead): "overdue" | "today" | "planned" | "none" {
  const now = new Date();
  if (lead.nextContactAt) {
    const action = new Date(lead.nextContactAt);
    if (action.getTime() < now.getTime()) return "overdue";
    if (action.toDateString() === now.toDateString()) return "today";
    return "planned";
  }
  if (lead.trialResult === "no_show" || lead.status === "Після пробного" || lead.status === "Нова") return "today";
  if (lead.status === "Пробне заплановано") return "planned";
  return "none";
}


export function leadActionPriority(lead: Lead) {
  const now = Date.now();
  if (lead.nextContactAt && dateValue(lead.nextContactAt) <= now) return 0;
  if (lead.trialResult === "no_show") return 1;
  if (lead.trialResult === "cancelled") return 2;
  if (lead.status === "Після пробного" && !lead.nextContactAt) return 3;
  if (lead.status === "Нова") return 4;
  if (lead.status === "Пробне заплановано") return 5;
  if (lead.nextContactAt) return 6;
  if (lead.status === "Зв'язались") return 7;
  if (lead.status === "Очікує групу") return 8;
  return 9;
}


export function leadDisplayStatus(lead: Lead) {
  if (lead.trialResult === "no_show" && lead.status === "Зв'язались") return "Не прийшов";
  if (lead.trialResult === "cancelled" && lead.status === "Зв'язались") return "Скасували пробне";
  return lead.status;
}


export function leadPrimaryActionLabel(lead: Lead) {
  if (["Відмовились", "Не відповідає", "Неактуально"].includes(lead.status)) return "Повернути в роботу";
  if (lead.status === "Зарахований") return "Відкрити картку учня";
  if (lead.status === "Нова") return "Позначити «Зв'язались»";
  if (lead.trialResult === "no_show" || lead.trialResult === "cancelled") return "Перезаписати на пробне";
  if (lead.status === "Пробне заплановано") return "Внести результат пробного";
  if (lead.status === "Після пробного") return "Рішення після пробного";
  if (lead.status === "Очікує групу") return "Зарахувати учня";
  return "Записати на пробне";
}


export function leadNextAction(lead: Lead) {
  if (leadIsDeferred(lead) && lead.deferredUntil) {
    const when = new Date(lead.deferredUntil);
    return `Повернутись: ${when.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit", year: "2-digit" })}`;
  }
  if (lead.status === "Відмовились") return "Закрито: відмовились";
  if (lead.status === "Не відповідає") return "Закрито: не відповідає";
  if (lead.status === "Неактуально") return "Закрито: неактуально";
  if (lead.status === "Зарахований") return "Учень зарахований";
  if (lead.nextContactAt) {
    const when = new Date(lead.nextContactAt);
    const overdue = when.getTime() < Date.now();
    return `${overdue ? "Прострочено: " : "Зв'язатися: "}${when.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })} · ${when.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}`;
  }
  if (lead.trialResult === "no_show") return "Зателефонувати / перезаписати";
  if (lead.trialResult === "cancelled") return "Узгодити нову дату";
  if (lead.status === "Після пробного") return "Уточнити рішення";
  if (lead.status === "Нова") return "Перший контакт";
  if (lead.status === "Пробне заплановано" && lead.trialAt) {
    const when = new Date(lead.trialAt);
    return `Пробне ${when.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })} · ${when.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}`;
  }
  if (lead.status === "Очікує групу") return "Підібрати групу";
  return "Продовжити контакт";
}


export function leadActionMeta(lead: Lead): { type: "call" | "trial" | "decision" | "group" | "closed" | "general"; icon: string; label: string } {
  if (leadIsDeferred(lead)) return { type: "general", icon: "◷", label: "Пізніше" };
  if (["Відмовились", "Не відповідає", "Неактуально"].includes(lead.status)) return { type: "closed", icon: "×", label: "Закрито" };
  if (lead.status === "Пробне заплановано") return { type: "trial", icon: "◷", label: "Пробне" };
  if (lead.trialResult === "no_show" || lead.trialResult === "cancelled" || lead.nextContactAt || lead.status === "Нова" || lead.status === "Зв'язались") return { type: "call", icon: "☎", label: "Контакт" };
  if (lead.status === "Після пробного") return { type: "decision", icon: "?", label: "Рішення" };
  if (lead.status === "Очікує групу") return { type: "group", icon: "→", label: "Група" };
  return { type: "general", icon: "•", label: "Дія" };
}


export function canonicalLeadSource(source: string | null | undefined) {
  const value = (source ?? "").trim().toLowerCase();
  const aliases: Record<string, string> = {
    iphone: "phone",
    телефон: "phone",
    дзвінок: "phone",
    site: "website",
    сайт: "website",
    insta: "instagram",
    referral: "recommendation",
    рекомендація: "recommendation",
    "walk_in": "walk-in",
    "walk in": "walk-in",
    "google maps": "maps",
  };
  return aliases[value] ?? value;
}


export function leadMissingDetails(lead: Lead): string[] {
  const missing: string[] = [];
  if (!lead.lastName?.trim()) missing.push("прізвище дитини");
  const contactName = cleanSpaces(lead.parent ?? "");
  if (!contactName || contactName === "Контакт не вказано") {
    missing.push("ім’я відповідальної особи");
  } else if (contactName.split(" ").filter(Boolean).length < 2) {
    missing.push("прізвище відповідальної особи");
  }
  return missing;
}


export function leadSourceLabel(source: string | null | undefined) {
  const labels: Record<string, string> = {
    phone: "Телефон",
    website: "Сайт",
    instagram: "Instagram",
    recommendation: "Рекомендація",
    "walk-in": "Зайшли особисто",
    walk_in: "Зайшли особисто",
    facebook: "Facebook",
    tiktok: "TikTok",
    google: "Google",
    maps: "Google Maps",
    other: "Інше",
  };
  if (!source) return "Не вказано";
  const canonical = canonicalLeadSource(source);
  return labels[canonical] ?? source;
}
