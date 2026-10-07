import { DAY_NAMES } from "../../components/ScheduleEditors";
import type { Lead } from "../leads/model";

export type CandidateMatch = {
  state: "match" | "partial" | "conflict" | "unknown";
  icon: string;
  label: string;
  detail: string;
};
export function candidateCompatibility(
  lead: Lead,
  schedule: Array<{ weekday: number; start_time: string; duration_minutes: number }>,
  locationId: string | null,
): CandidateMatch {
  if (!schedule.length || !(lead.availability?.length)) {
    return { state: "unknown", icon: "?", label: "Побажаний час не вказаний", detail: "Уточнити графік у батьків" };
  }
  let full = 0, partial = 0, conflicts = 0, preferred = 0;
  const details: string[] = [];
  schedule.forEach((lesson) => {
    const lessonStart = timeToMinutes(lesson.start_time);
    const lessonEnd = lessonStart + lesson.duration_minutes;
    const sameDay = lead.availability!.filter((x) => x.weekday === lesson.weekday);
    const acceptable = sameDay.filter((x) => (x.preference ?? "preferred") !== "avoid");
    const avoided = sameDay.filter((x) => (x.preference ?? "preferred") === "avoid");
    const fits = acceptable.filter((x) => timeToMinutes(x.start_time) <= lessonStart && timeToMinutes(x.end_time) >= lessonEnd);
    const avoidOverlap = avoided.some((x) => lessonStart < timeToMinutes(x.end_time) && lessonEnd > timeToMinutes(x.start_time));
    if (avoidOverlap && !fits.length) {
      conflicts++;
      details.push(`${DAY_NAMES[lesson.weekday]} ${lesson.start_time} — потрапляє в небажаний час`);
      return;
    }
    if (fits.length) {
      full++;
      if (fits.some((x) => (x.preference ?? "preferred") === "preferred")) preferred++;
      details.push(`${DAY_NAMES[lesson.weekday]} ${lesson.start_time} — підходить`);
      if (avoidOverlap) {
        partial++;
        details.push(`${DAY_NAMES[lesson.weekday]} ${lesson.start_time} — також перетинає небажаний час`);
      }
      return;
    }
    const close = acceptable.find((x) => {
      const start = timeToMinutes(x.start_time), end = timeToMinutes(x.end_time);
      return (lessonStart < end && lessonEnd > start) || Math.max(start - lessonEnd, lessonStart - end, 0) <= 60;
    });
    if (close) {
      partial++;
      details.push(`${DAY_NAMES[lesson.weekday]}: сім’я бажає ${close.start_time.slice(0, 5)}–${close.end_time.slice(0, 5)}`);
    } else conflicts++;
  });
  const locationMismatch = Boolean(lead.preferredLocationId && locationId && lead.preferredLocationId !== locationId);
  const locationDetail = locationMismatch ? "Бажана локація відрізняється" : "";
  const explanation = [...details, locationDetail].filter(Boolean).join("; ");
  if (!full && !partial) return { state: "conflict", icon: "!", label: "Потрібне узгодження", detail: explanation || "Збігів немає" };
  if (partial || conflicts || locationMismatch || preferred === 0) {
    const possibleOnly = matchingOnlyPossible(full, preferred) ? "Час позначений лише як можливий" : "";
    return { state: "partial", icon: "⚠", label: "Частковий збіг", detail: [explanation, possibleOnly].filter(Boolean).join("; ") || "Потрібне уточнення" };
  }
  return { state: "match", icon: "✓", label: "Графік підходить", detail: explanation };
}


export function matchingOnlyPossible(full: number, preferred: number) {
  return full > 0 && preferred === 0;
}


export function MatchBadge({ match }: { match: CandidateMatch }) {
  return <span className={"candidateSource candidateCompatibility " + match.state}>{match.icon} {match.label}</span>;
}


export function MatchExplanation({ match }: { match: CandidateMatch }) {
  return <small className={"matchExplanation " + match.state}>{match.detail}</small>;
}


export function timeToMinutes(value: string) {
  const [hours, minutes] = value.slice(0, 5).split(":").map(Number);
  return hours * 60 + minutes;
}


