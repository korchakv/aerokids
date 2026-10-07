export function dayOffsetForDate(value: string | Date) {
  const current = new Date();
  current.setHours(0, 0, 0, 0);
  const target = typeof value === "string" ? new Date(value) : new Date(value);
  target.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - current.getTime()) / (24 * 60 * 60 * 1000));
}

export function weekdayLong(value: string) {
  const text = new Date(value).toLocaleDateString("uk-UA", { weekday: "long" });
  return text ? text.charAt(0).toLocaleUpperCase("uk-UA") + text.slice(1) : "";
}

export function dateValue(value?: string, fallback = 0) {
  if (!value) return fallback;
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : fallback;
}

export function lessonWeekdayLabel(value: string) {
  const names = ["Нд", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : names[date.getDay()];
}

export function addLocalDays(value: Date, amount: number) {
  const next = new Date(value);
  next.setHours(12, 0, 0, 0);
  next.setDate(next.getDate() + amount);
  return next;
}

export function startOfLocalWeek(value: Date) {
  const next = new Date(value);
  next.setHours(12, 0, 0, 0);
  const mondayOffset = (next.getDay() + 6) % 7;
  next.setDate(next.getDate() - mondayOffset);
  return next;
}

export function localDateInput(value: Date) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

export function defaultPaymentDueDate() {
  const now = new Date();
  return localDateInput(new Date(now.getFullYear(), now.getMonth() + 1, 0));
}

export function toLocalDateTimeInput(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
