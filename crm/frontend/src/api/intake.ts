import type { IntakeDuplicateMatch, Session } from "./types";
import { apiPost } from "./client";

export function checkIntakeDuplicates(input: {
  child_first_name: string;
  child_age: number;
  phone: string;
  child_phone?: string | null;
}, session: Session) {
  return apiPost<{ matches: IntakeDuplicateMatch[] }>("/intake/duplicate-check", input, session);
}
