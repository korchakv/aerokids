export type Membership = {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  organization_timezone: string;
  organization_currency: string;
  organization_locale: string;
  role: "owner" | "admin" | "manager" | "teacher" | "accountant";
};

export type AuthUser = {
  id: string;
  email: string;
  full_name: string | null;
  memberships: Membership[];
};

export type Session = {
  accessToken: string;
  user: AuthUser;
  organizationId: string;
};

const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const STORAGE_KEY = "school-crm-session";

export const apiEnabled = Boolean(API_URL);

const API_FIELD_LABELS: Record<string, string> = {
  items: "дані",
  email: "email",
  password: "пароль",
  full_name: "ім’я та прізвище",
  first_name: "ім’я",
  last_name: "прізвище",
  child_first_name: "ім’я дитини",
  child_last_name: "прізвище дитини",
  child_age: "вік дитини",
  contact_name: "ім’я відповідального",
  phone: "телефон",
  child_phone: "телефон дитини",
  name: "назва",
  capacity: "місткість",
  location_id: "локація",
  group_id: "група",
  student_id: "учень",
  staff_id: "працівник",
  plan_id: "тариф",
  starts_at: "дата і час",
  start_time: "час початку",
  end_time: "час завершення",
  duration_minutes: "тривалість",
  schedule_slots: "розклад",
  amount_minor: "сума",
  due_date: "дата оплати",
  topic: "тема заняття",
  notes: "примітки",
  note: "коментар",
  source: "джерело",
  role: "роль",
};

const KNOWN_API_MESSAGES: Record<string, string> = {
  "Invalid bootstrap secret": "Невірний службовий ключ початкового налаштування.",
  "Only an owner can invite another owner": "Лише власник може запросити іншого власника.",
  "Direct organization creation is disabled when authentication is required": "Створення нової організації напряму зараз недоступне.",
  "Use /auth/me to list your organizations": "Не вдалося отримати список організацій. Оновіть сторінку та спробуйте ще раз.",
  "Organization not found": "Організацію не знайдено. Оновіть сторінку або виберіть іншу організацію.",
  "Invalid form submission": "Форму не вдалося прийняти. Перевірте введені дані та спробуйте ще раз.",
  "Group has no available seats": "У цій групі немає вільних місць. Збільште місткість або оберіть іншу групу.",
  "Too many form submissions. Please try again later.": "Забагато заявок за короткий час. Зачекайте кілька хвилин і спробуйте ще раз.",
  "Organization slug already exists": "Організація з такою адресою вже існує. Виберіть іншу адресу.",
  "Organization currency cannot be changed after payments have been created": "Валюту організації не можна змінити після створення оплат.",
  "Not found": "Запис не знайдено. Можливо, його вже видалили або у вас немає до нього доступу.",
  "min_age cannot be greater than max_age": "Мінімальний вік не може бути більшим за максимальний.",
  "Student is already enrolled in this group": "Учень уже зарахований до цієї групи.",
  "Duplicate students are not allowed": "У списку є той самий учень кілька разів. Приберіть дубль.",
  "Selected students exceed group capacity": "Обрано більше учнів, ніж дозволяє місткість групи. Збільште місткість або приберіть зайвих учнів.",
  "Duplicate group schedule slots are not allowed": "У розкладі повторюється однаковий день і час. Приберіть дубль.",
  "Could not form group; check name and enrollments": "Не вдалося створити групу. Перевірте назву, місткість і вибраних учнів.",
  "Student is already enrolled in a group": "Учень уже зарахований до групи. Спочатку перевірте його поточну групу.",
  "This group already has the same schedule slot": "У цієї групи вже є заняття в такий день і час.",
  "Duplicate students in attendance payload": "Один і той самий учень доданий у відвідування кілька разів. Оновіть сторінку та спробуйте ще раз.",
  "Subscription plan name already exists": "Тариф із такою назвою вже існує. Виберіть іншу назву.",
  "Discount cannot exceed subscription price": "Знижка не може бути більшою за вартість абонемента.",
  "Cancelled subscription cannot be renewed": "Скасований абонемент не можна продовжити.",
  "Subscription cannot be paused": "Цей абонемент зараз не можна поставити на паузу.",
  "Pause must start inside the subscription period": "Дата початку паузи має бути в межах дії абонемента.",
  "Subscription already has an active or scheduled pause": "Для цього абонемента вже є активна або запланована пауза.",
  "Resume date must be after pause start": "Дата відновлення має бути пізнішою за дату початку паузи.",
  "Subscription has no active pause": "У цього абонемента немає активної паузи.",
  "through_date cannot be in the past": "Дата не може бути в минулому.",
  "Charge amount must be greater than zero": "Сума нарахування має бути більшою за нуль.",
  "This subscription period has already been charged": "За цей період абонемента нарахування вже створено.",
  "Subscription belongs to another student": "Цей абонемент належить іншому учню.",
  "This charge cannot accept payments": "Для цього нарахування зараз не можна прийняти оплату.",
  "Payment amount exceeds outstanding balance": "Сума оплати більша за залишок до сплати.",
  "This charge cannot be marked as paid": "Це нарахування не можна позначити як сплачене.",
  "Payment is already fully settled": "Це нарахування вже повністю сплачене.",
  "Cancelled charge cannot be adjusted": "Скасоване нарахування не можна коригувати.",
  "Adjustment exceeds charge amount": "Сума коригування більша за суму нарахування.",
  "Refund the overpaid amount before decreasing the charge": "Спочатку поверніть переплату, а потім зменшуйте нарахування.",
  "Cancelled charge cannot be refunded": "За скасованим нарахуванням не можна зробити повернення.",
  "Refund exceeds net amount received": "Сума повернення більша за фактично отриману оплату.",
  "Only unpaid pending charges can be cancelled": "Скасувати можна лише несплачене нарахування, яке ще очікує оплати.",
  "Payment no longer needs a reminder": "Для цієї оплати нагадування вже не потрібне.",
  "Reminder stage is no longer current": "Це нагадування вже неактуальне. Оновіть дані.",
  "This reminder stage was already recorded": "Цей етап нагадування вже зафіксовано.",
  "Staff email already exists in this organization": "Працівник із таким email уже є в цій організації.",
  "Remove this staff member from teaching groups before disabling teaching": "Спочатку приберіть працівника з груп, де він викладає, а потім вимикайте можливість викладати.",
  "Inactive staff member cannot be assigned": "Неактивного працівника не можна призначити.",
  "Staff member is not marked as able to teach": "Цього працівника не позначено як такого, що може викладати.",
  "Location name already exists": "Локація з такою назвою вже існує.",
  "Duplicate availability slots are not allowed": "У побажаннях щодо часу є однакові проміжки. Приберіть дубль.",
  "No access to this group": "У вас немає доступу до цієї групи.",
  "Too many login attempts. Please try again later.": "Забагато спроб входу. Зачекайте кілька хвилин і спробуйте ще раз.",
  "Bootstrap is only available for an empty CRM database": "Початкове налаштування доступне лише для порожньої CRM.",
  "Incorrect email or password": "Невірний email або пароль.",
  "User is inactive or unavailable": "Цей користувач неактивний або недоступний.",
  "Invitation is invalid": "Запрошення недійсне. Попросіть створити нове.",
  "This invitation has already been accepted": "Це запрошення вже використано.",
  "Invitation has expired": "Термін дії запрошення закінчився. Попросіть створити нове.",
  "This email already has an account; use its existing password": "Для цього email уже є обліковий запис. Увійдіть із чинним паролем.",
  "User not found": "Користувача не знайдено.",
  "User is not a member of this organization": "Цей користувач не має доступу до вибраної організації.",
  "Only an owner can reset another owner": "Лише власник може скинути пароль іншому власнику.",
  "Reset link is invalid or already used": "Посилання для скидання пароля недійсне або вже використане.",
  "Reset link is invalid or expired": "Посилання для скидання пароля недійсне або прострочене.",
  "Invalid X-Organization-Id": "Не вдалося визначити організацію. Оновіть сторінку та спробуйте ще раз.",
  "Authentication required": "Потрібно увійти в CRM.",
  "No access to this organization": "У вас немає доступу до цієї організації.",
  "Insufficient role for this action": "У вас немає прав для цієї дії.",
};

function hasUkrainianText(value: string): boolean {
  return /[А-Яа-яІіЇїЄєҐґ]/.test(value);
}

function requestAction(path: string, method = "GET"): string {
  if (path.includes("/attendance")) return method === "GET" ? "завантажити відвідування" : "зберегти відвідування";
  if (path.includes("/lesson-sessions")) return method === "GET" ? "завантажити заняття" : "зберегти заняття";
  if (path.includes("/groups")) return method === "GET" ? "завантажити групи" : "зберегти групу";
  if (path.includes("/intake")) return "зберегти заявку";
  if (path.includes("/trial-lessons")) return "зберегти пробне заняття";
  if (path.includes("/students")) return method === "GET" ? "завантажити дані учня" : "зберегти дані учня";
  if (path.includes("/staff") || path.includes("/organization-invitations")) return "зберегти дані працівника";
  if (path.includes("/locations")) return "зберегти локацію";
  if (path.includes("/payments") || path.includes("/billing/") || path.includes("/student-subscriptions")) return "виконати операцію з оплатою";
  if (path.includes("/auth/login")) return "увійти в CRM";
  if (path.includes("/preferences")) return "зберегти побажання";
  return method === "GET" ? "завантажити дані" : "виконати дію";
}

function actionFallback(path: string, method = "GET"): string {
  return `Не вдалося ${requestAction(path, method)}. Спробуйте ще раз.`;
}

function translateKnownMessage(message: string): string | null {
  const clean = message.trim().replace(/^Value error,\s*/i, "");
  if (!clean) return null;
  if (KNOWN_API_MESSAGES[clean]) return KNOWN_API_MESSAGES[clean];
  if (/^Student .+ is not waiting for a group$/i.test(clean)) {
    return "Цей учень ще не переведений у статус «Очікує групу». Спочатку змініть його статус.";
  }
  if (/^Місткість групи не може бути меншою/i.test(clean)) return clean;
  if (hasUkrainianText(clean)) return clean;
  return null;
}

function validationField(loc: unknown[]): string {
  const parts = loc
    .filter((part) => part !== "body")
    .map((part) => {
      if (typeof part === "number") return `запис ${part + 1}`;
      const key = String(part);
      return API_FIELD_LABELS[key] ?? key.replaceAll("_", " ");
    });
  return parts.join(" → ");
}

function validationIssueMessage(item: unknown, path: string): string | null {
  if (!item || typeof item !== "object") return null;
  const row = item as { msg?: unknown; loc?: unknown[]; type?: unknown; ctx?: Record<string, unknown> };
  const loc = Array.isArray(row.loc) ? row.loc : [];
  const field = validationField(loc);
  const fieldKey = String(loc.at(-1) ?? "");
  const type = typeof row.type === "string" ? row.type : "";
  const raw = typeof row.msg === "string" ? row.msg : "";
  const ctx = row.ctx ?? {};

  if (path.includes("/attendance") && fieldKey === "items" && (type.includes("too_short") || /at least 1 item/i.test(raw))) {
    return "Немає учнів для збереження відвідування. Додайте учнів до групи або відкрийте інше заняття.";
  }
  if (type === "missing" || /Field required/i.test(raw)) {
    return field ? `Заповніть поле «${field}».` : "Заповніть усі обов’язкові поля.";
  }
  if (type.includes("list_type")) {
    return field ? `Перевірте список «${field}».` : "Перевірте список даних.";
  }
  if (type.includes("too_short") || /at least 1 item/i.test(raw)) {
    return field ? `Додайте хоча б один запис у «${field}».` : "Додайте хоча б один запис.";
  }
  if (type.includes("string_too_short")) {
    const min = typeof ctx.min_length === "number" ? ` щонайменше ${ctx.min_length} символи` : "";
    return field ? `Поле «${field}» має містити${min || " більше символів"}.` : "Введене значення закоротке.";
  }
  if (type.includes("string_too_long")) {
    const max = typeof ctx.max_length === "number" ? ` не більше ${ctx.max_length} символів` : "";
    return field ? `Поле «${field}» має містити${max || " менше символів"}.` : "Введене значення задовге.";
  }
  if (type.includes("greater_than_equal")) {
    const min = ctx.ge ?? ctx.limit_value;
    return field ? `Поле «${field}» має бути не менше ${String(min ?? "мінімального значення")}.` : "Значення замале.";
  }
  if (type.includes("less_than_equal")) {
    const max = ctx.le ?? ctx.limit_value;
    return field ? `Поле «${field}» має бути не більше ${String(max ?? "максимального значення")}.` : "Значення завелике.";
  }
  if (type.includes("int_") || type.includes("float_") || /valid (integer|number)/i.test(raw)) {
    return field ? `У полі «${field}» потрібно вказати число.` : "Вкажіть коректне число.";
  }
  if (type.includes("date") || type.includes("time") || type.includes("datetime")) {
    return field ? `Перевірте дату або час у полі «${field}».` : "Перевірте дату та час.";
  }
  if (type.includes("uuid")) {
    return field ? `Оберіть коректне значення для поля «${field}».` : "Оберіть коректний запис.";
  }

  const translated = translateKnownMessage(raw);
  if (translated) return field ? `${field}: ${translated}` : translated;
  return field ? `Перевірте поле «${field}».` : null;
}

function statusFallback(status: number, path: string, method = "GET"): string {
  if (status === 401) return "Сесія завершилась або дані входу некоректні. Увійдіть у CRM ще раз.";
  if (status === 403) return "У вас немає прав для цієї дії.";
  if (status === 404) return "Запис не знайдено. Оновіть сторінку та спробуйте ще раз.";
  if (status === 409) return "Не вдалося зберегти зміни через конфлікт даних. Оновіть сторінку та перевірте, чи такий запис уже не існує.";
  if (status === 422) return `${actionFallback(path, method)} Перевірте заповнені поля.`;
  if (status === 429) return "Забагато спроб за короткий час. Зачекайте кілька хвилин і спробуйте ще раз.";
  if (status >= 500) return "Сталася помилка на сервері. Спробуйте ще раз трохи пізніше. Якщо помилка повторюється — повідомте адміністратору.";
  return actionFallback(path, method);
}

function humanizeApiDetail(detail: unknown, fallback: string, path: string): string {
  if (typeof detail === "string" && detail.trim()) {
    return translateKnownMessage(detail) ?? fallback;
  }
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => validationIssueMessage(item, path)).filter((item): item is string => Boolean(item));
    return messages.length ? Array.from(new Set(messages)).join(" ") : fallback;
  }
  if (detail && typeof detail === "object") {
    const row = detail as { message?: unknown; code?: unknown };
    if (typeof row.message === "string" && row.message.trim()) {
      return translateKnownMessage(row.message) ?? fallback;
    }
    if (typeof row.code === "string" && row.code.trim()) {
      return translateKnownMessage(row.code) ?? fallback;
    }
  }
  return fallback;
}

async function responseError(response: Response, path: string, method = "GET"): Promise<Error> {
  const fallback = statusFallback(response.status, path, method);
  try {
    const body = await response.json();
    return new Error(humanizeApiDetail(body?.detail, fallback, path));
  } catch {
    return new Error(fallback);
  }
}

function emitMutationSaved(path: string, method: string) {
  if (method === "GET") return;
  if (path.startsWith("/auth/")) return;
  if (path === "/billing/renewals/run") return;
  if (path === "/intake/duplicate-check") return;
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("crm:saved", { detail: { path, method } }));
}

async function request<T>(path: string, init: RequestInit = {}, session?: Session): Promise<T> {
  if (!API_URL) throw new Error("CRM не підключена до сервера. Перевірте налаштування API.");
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (session) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
    headers.set("X-Organization-Id", session.organizationId);
  }

  const method = init.method ?? "GET";
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new Error("Не вдалося з’єднатися із сервером CRM. Перевірте інтернет-з’єднання та спробуйте ще раз.");
  }
  if (!response.ok) throw await responseError(response, path, method);
  emitMutationSaved(path, method);
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<Session> {
  const result = await request<{ access_token: string; user: AuthUser }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  const organizationId = result.user.memberships[0]?.organization_id;
  if (!organizationId) throw new Error("Для цього користувача немає доступної організації");
  const session = { accessToken: result.access_token, user: result.user, organizationId };
  saveSession(session);
  return session;
}

export async function refreshMe(session: Session): Promise<Session> {
  const user = await request<AuthUser>("/auth/me", {
    headers: { Authorization: `Bearer ${session.accessToken}` },
  });
  const organizationId = user.memberships.some((m) => m.organization_id === session.organizationId)
    ? session.organizationId
    : user.memberships[0]?.organization_id;
  if (!organizationId) throw new Error("Немає доступної організації");
  const updated = { ...session, user, organizationId };
  saveSession(updated);
  return updated;
}

export function changeOrganization(session: Session, organizationId: string): Session {
  if (!session.user.memberships.some((m) => m.organization_id === organizationId)) {
    throw new Error("Немає доступу до цієї організації");
  }
  const updated = { ...session, organizationId };
  saveSession(updated);
  return updated;
}

export function loadSession(): Session | null {
  try {
    let raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        sessionStorage.setItem(STORAGE_KEY, raw);
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    return raw ? JSON.parse(raw) as Session : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  localStorage.removeItem(STORAGE_KEY);
}

export function clearSession() {
  sessionStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(STORAGE_KEY);
}

export function apiGet<T>(path: string, session: Session) {
  return request<T>(path, {}, session);
}

export function apiPost<T>(path: string, body: unknown, session: Session) {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) }, session);
}

export function apiPatch<T>(path: string, body: unknown, session: Session) {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) }, session);
}


export type StudentAvailabilitySlot = {
  weekday: number;
  start_time: string;
  end_time: string;
  preference: "preferred" | "possible" | "avoid";
  note: string | null;
};

export type IntakeDuplicateMatch = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  age: number | null;
  crm_status: WorkspaceLead["crm_status"];
  student_status: "prospect" | "active" | "paused" | "archived";
  student_phone: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  matched_phone: string;
  matched_as: "student" | "contact" | "student_and_contact";
  likely_same_student: boolean;
};

export function checkIntakeDuplicates(input: {
  child_first_name: string;
  child_age: number;
  phone: string;
  child_phone?: string | null;
}, session: Session) {
  return apiPost<{ matches: IntakeDuplicateMatch[] }>("/intake/duplicate-check", input, session);
}


export type WorkspaceLead = {
  student_id: string;
  created_at: string;
  first_name: string;
  last_name: string | null;
  student_phone: string | null;
  age: number | null;
  source: string | null;
  comment: string | null;
  preferred_location_id: string | null;
  preferred_location_name: string | null;
  availability: StudentAvailabilitySlot[];
  crm_status: "new" | "contacted" | "trial_scheduled" | "trial_completed" | "waiting_for_group" | "enrolled" | "no_response" | "declined" | "not_relevant";
  contact_name: string | null;
  contact_phone: string | null;
  latest_trial_id: string | null;
  latest_trial_at: string | null;
  latest_trial_status: "scheduled" | "completed" | "no_show" | "cancelled" | null;
  trial_location_id: string | null;
  trial_location_name: string | null;
  recommended_level: string | null;
  teacher_notes: string | null;
  next_contact_at: string | null;
  deferred_until: string | null;
  deferred_reason: string | null;
  deferred_note: string | null;
  close_reason: string | null;
  close_note: string | null;
};

export type WorkspaceStudent = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  student_phone: string | null;
  age: number | null;
  source: string | null;
  student_status: "active" | "paused" | "archived";
  contact_name: string | null;
  contact_phone: string | null;
  group_id: string | null;
  group_name: string | null;
};

export type WorkspaceGroup = {
  group_id: string;
  name: string;
  location_id: string | null;
  location_name: string | null;
  capacity: number | null;
  enrolled_count: number;
  min_age: number | null;
  max_age: number | null;
  primary_teacher_id: string | null;
  primary_teacher_name: string | null;
};

export type WorkspaceBundle = {
  leads: WorkspaceLead[];
  students: WorkspaceStudent[];
  groups: WorkspaceGroup[];
};

export async function loadWorkspace(session: Session): Promise<WorkspaceBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  const role = membership?.role;

  const leadsPromise = ["owner", "admin", "manager"].includes(role ?? "")
    ? apiGet<WorkspaceLead[]>("/workspace/leads", session)
    : Promise.resolve([]);

  const studentsPromise = apiGet<WorkspaceStudent[]>("/workspace/students", session);

  const groupsPromise = role === "accountant"
    ? Promise.resolve([])
    : apiGet<WorkspaceGroup[]>("/workspace/groups", session);

  const [leads, students, groups] = await Promise.all([leadsPromise, studentsPromise, groupsPromise]);
  return { leads, students, groups };
}


export type ApiLocation = {
  id: string;
  organization_id: string;
  name: string;
  address: string | null;
  is_active: boolean;
};

export type ApiStaff = {
  id: string;
  organization_id: string;
  user_id: string | null;
  full_name: string;
  email: string | null;
  phone: string | null;
  role: "owner" | "admin" | "manager" | "teacher" | "accountant";
  can_teach: boolean;
  is_active: boolean;
  notes: string | null;
};

export type ApiStaffProfile = ApiStaff & {
  assignments: {
    location_ids: string[];
    group_ids: string[];
  };
};

export type ApiSubscriptionPlan = {
  id: string;
  organization_id: string;
  name: string;
  price_minor: number;
  period_days: number | null;
  lessons_included: number | null;
  usage_mode: "attendance" | "scheduled" | "period";
  absent_rule: "consume" | "dont_consume" | "choice";
  excused_rule: "consume" | "dont_consume" | "makeup";
  late_rule: "consume" | "dont_consume";
  end_rule: "lessons" | "date" | "whichever_first";
  renewal_trigger: "last_lesson" | "date" | "manual";
  allow_debt: boolean;
  max_lates: number | null;
  makeup_expiry_days: number | null;
  is_active: boolean;
};

export type ApiPayment = {
  id: string;
  organization_id: string;
  student_id: string;
  subscription_id: string | null;
  plan_id: string | null;
  amount_minor: number;
  currency: string;
  status: "pending" | "paid" | "refunded" | "cancelled";
  method: "cash" | "card" | "bank" | "other" | null;
  due_date: string | null;
  paid_at: string | null;
  note: string | null;
  adjusted_amount_minor: number;
  paid_minor: number;
  refunded_minor: number;
  balance_minor: number;
  credit_minor: number;
};

export type ApiStudentSubscription = {
  id: string;
  organization_id: string;
  student_id: string;
  plan_id: string;
  group_id: string | null;
  status: "active" | "paused" | "expired" | "cancelled";
  starts_on: string;
  ends_on: string | null;
  price_minor: number;
  period_days: number | null;
  lessons_included: number | null;
  lesson_unit_price_minor: number | null;
  credit_minor: number;
  discount_minor: number;
  discount_label: string | null;
  auto_renew: boolean;
  renewal_of_id: string | null;
  used_lessons: number;
  remaining_lessons: number | null;
  needs_renewal: boolean;
};

export type OperationsBundle = {
  locations: ApiLocation[];
  staff: ApiStaffProfile[];
  plans: ApiSubscriptionPlan[];
  payments: ApiPayment[];
  subscriptions: ApiStudentSubscription[];
};

export async function loadOperations(session: Session): Promise<OperationsBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  const role = membership?.role;

  const operationalAccess = ["owner", "admin", "manager", "teacher"].includes(role ?? "");
  const staffAccess = ["owner", "admin"].includes(role ?? "");
  const financeAccess = ["owner", "admin", "accountant"].includes(role ?? "");

  const locationsPromise = operationalAccess
    ? apiGet<ApiLocation[]>("/locations", session)
    : Promise.resolve([]);

  const staffPromise = staffAccess
    ? apiGet<ApiStaff[]>("/staff", session).then(async (items) => Promise.all(
        items.map((item) => apiGet<ApiStaffProfile>(`/staff/${item.id}/profile`, session))
      ))
    : Promise.resolve([]);

  const plansPromise = financeAccess
    ? apiGet<ApiSubscriptionPlan[]>("/subscription-plans", session)
    : Promise.resolve([]);

  const paymentsPromise = financeAccess
    ? apiGet<ApiPayment[]>("/payments", session)
    : Promise.resolve([]);

  const subscriptionsPromise = financeAccess
    ? apiGet<ApiStudentSubscription[]>("/student-subscriptions", session)
    : Promise.resolve([]);

  const [locations, staff, plans, payments, subscriptions] = await Promise.all([
    locationsPromise,
    staffPromise,
    plansPromise,
    paymentsPromise,
    subscriptionsPromise,
  ]);

  return { locations, staff, plans, payments, subscriptions };
}


export function runBillingRenewals(session: Session) {
  return apiPost<{ resumed_subscriptions: number; created_subscriptions: number; skipped_stale_subscriptions: number; created_payment_ids: string[] }>("/billing/renewals/run", {}, session);
}

export function apiPut<T>(path: string, body: unknown, session: Session) {
  return request<T>(path, { method: "PUT", body: JSON.stringify(body) }, session);
}

export async function apiDelete(path: string, session: Session): Promise<void> {
  if (!API_URL) throw new Error("CRM не підключена до сервера. Перевірте налаштування API.");
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
        "X-Organization-Id": session.organizationId,
      },
    });
  } catch {
    throw new Error("Не вдалося з’єднатися із сервером CRM. Перевірте інтернет-з’єднання та спробуйте ще раз.");
  }
  if (!response.ok) throw await responseError(response, path, "DELETE");
  emitMutationSaved(path, "DELETE");
}


export async function getBootstrapStatus(): Promise<boolean> {
  const result = await request<{ available: boolean }>("/auth/bootstrap-status");
  return result.available;
}

export async function bootstrapOwner(input: {
  organization_name: string;
  organization_slug: string;
  full_name: string;
  email: string;
  password: string;
}, bootstrapSecret?: string): Promise<Session> {
  const result = await request<{
    organization_id: string;
    user_id: string;
    access_token: string;
    token_type: string;
  }>("/auth/bootstrap", {
    method: "POST",
    headers: bootstrapSecret ? { "X-Bootstrap-Secret": bootstrapSecret } : undefined,
    body: JSON.stringify(input),
  });

  const user = await request<AuthUser>("/auth/me", {
    headers: { Authorization: `Bearer ${result.access_token}` },
  });
  const session: Session = {
    accessToken: result.access_token,
    user,
    organizationId: result.organization_id,
  };
  saveSession(session);
  return session;
}


export type InvitationStatus = "valid" | "accepted" | "expired" | "invalid";

export async function getInvitationStatus(inviteToken: string): Promise<InvitationStatus> {
  const result = await request<{ status: InvitationStatus }>("/auth/invite-status", {
    method: "POST",
    body: JSON.stringify({ invite_token: inviteToken }),
  });
  return result.status;
}


export async function acceptInvite(input: {
  invite_token: string;
  full_name: string;
  password: string;
}): Promise<Session> {
  const result = await request<{ access_token: string; user: AuthUser }>("/auth/accept-invite", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const organizationId = result.user.memberships[0]?.organization_id;
  if (!organizationId) throw new Error("Запрошення не надало доступу до організації");
  const session: Session = {
    accessToken: result.access_token,
    user: result.user,
    organizationId,
  };
  saveSession(session);
  return session;
}


export type ApiGroupSchedule = {
  id: string;
  organization_id: string;
  group_id: string;
  weekday: number;
  start_time: string;
  duration_minutes: number;
  is_active: boolean;
};

export type ApiLessonSession = {
  id: string;
  organization_id: string;
  group_id: string;
  location_id: string | null;
  starts_at: string;
  duration_minutes: number;
  topic: string | null;
  notes: string | null;
  status: "scheduled" | "completed" | "cancelled";
  attendance_present: number;
  attendance_absent: number;
  attendance_late: number;
  attendance_excused: number;
  attendance_total: number;
};

export type ApiAttendance = {
  id: string;
  organization_id: string;
  session_id: string;
  student_id: string;
  status: "present" | "absent" | "late" | "excused";
  note: string | null;
};

export type ApiGroupMemberDetail = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  student_phone: string | null;
  age: number | null;
  contact_name: string | null;
  contact_phone: string | null;
  enrollment_started_at: string;
  enrollment_status: "active" | "paused" | "finished";
  attendance: {
    present: number;
    absent: number;
    late: number;
    excused: number;
    total: number;
    attendance_rate: number;
  };
  billing: {
    status: "current" | "upcoming" | "due" | "overdue" | "no_plan";
    plan_name: string | null;
    lessons_used: number | null;
    lessons_included: number | null;
    lessons_remaining: number | null;
    amount_due_minor: number;
    next_due_date: string | null;
    last_paid_at: string | null;
    last_paid_minor: number | null;
    subscription_ends_on: string | null;
  } | null;
  payments: ApiPayment[];
};

export type ApiGroupDetail = {
  group: {
    id: string;
    organization_id: string;
    location_id: string | null;
    name: string;
    capacity: number | null;
    min_age: number | null;
    max_age: number | null;
    is_active: boolean;
  };
  schedules: ApiGroupSchedule[];
  members: ApiGroupMemberDetail[];
};

export type ApiPaymentReminder = {
  payment_id: string;
  student_id: string;
  student_name: string;
  contact_name: string | null;
  contact_phone: string | null;
  amount_minor: number;
  currency: string;
  due_date: string;
  days_from_due: number;
  stage: "upcoming_3" | "due_today" | "overdue_1" | "overdue_3" | "overdue_7" | "overdue_14" | "overdue_30";
  label: string;
  last_reminder_at: string | null;
};

export type ApiStudentAttendanceHistoryItem = {
  session_id: string;
  group_id: string;
  group_name: string;
  starts_at: string;
  duration_minutes: number;
  topic: string | null;
  lesson_status: "scheduled" | "completed" | "cancelled";
  status: "present" | "absent" | "late" | "excused";
  note: string | null;
};

export function loadStudentAttendanceHistory(studentId: string, session: Session) {
  return apiGet<ApiStudentAttendanceHistoryItem[]>(`/students/${studentId}/attendance-history`, session);
}

export type ApiGroupRosterStudent = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  age: number | null;
};

export function loadGroupRoster(groupId: string, session: Session) {
  return apiGet<ApiGroupRosterStudent[]>(`/groups/${groupId}/roster`, session);
}

export function loadGroupDetail(groupId: string, session: Session) {
  return apiGet<ApiGroupDetail>(`/groups/${groupId}/detail`, session);
}

export function loadPaymentReminders(session: Session) {
  return apiGet<ApiPaymentReminder[]>("/payment-reminders", session);
}

export function recordPaymentReminder(paymentId: string, stage: ApiPaymentReminder["stage"], channel: "manual" | "sms" | "email" | "messenger" | "phone", session: Session) {
  return apiPost(`/payments/${paymentId}/reminders`, { stage, channel }, session);
}


export type TeachingBundle = {
  schedules: ApiGroupSchedule[];
  lessons: ApiLessonSession[];
};

export async function loadTeaching(session: Session): Promise<TeachingBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  if (membership?.role === "accountant") return { schedules: [], lessons: [] };
  const [schedules, lessons] = await Promise.all([
    apiGet<ApiGroupSchedule[]>("/group-schedules", session),
    apiGet<ApiLessonSession[]>("/lesson-sessions", session),
  ]);
  return { schedules, lessons };
}

export function loadAttendance(sessionId: string, session: Session) {
  return apiGet<ApiAttendance[]>(`/lesson-sessions/${sessionId}/attendance`, session);
}


export type OverviewReport = {
  funnel: Array<{ status: WorkspaceLead["crm_status"]; count: number }>;
  active_students: number;
  active_groups: number;
  enrolled_students: number;
  group_capacity: number;
  active_staff: number;
  active_locations: number;
  attendance: {
    present: number;
    absent: number;
    late: number;
    excused: number;
    total: number;
    attendance_rate: number;
  };
  payments: {
    paid_minor: number;
    pending_minor: number;
    overdue_minor: number;
    paid_count: number;
    pending_count: number;
    overdue_count: number;
  };
};

export async function loadOverviewReport(session: Session): Promise<OverviewReport | null> {
  return apiGet<OverviewReport>("/reports/overview", session);
}


export type ApiAuditEvent = {
  id: string;
  organization_id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  actor_email: string | null;
  entity_type: string;
  entity_id: string | null;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string;
};

export function loadAuditEvents(entityType: string, entityId: string, session: Session) {
  const query = new URLSearchParams({ entity_type: entityType, entity_id: entityId, limit: "100" });
  return apiGet<ApiAuditEvent[]>(`/audit-events?${query.toString()}`, session);
}


export async function resetPassword(input: {
  reset_token: string;
  password: string;
}): Promise<Session> {
  const result = await request<{ access_token: string; user: AuthUser }>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const organizationId = result.user.memberships[0]?.organization_id;
  if (!organizationId) throw new Error("Для цього користувача немає доступної організації");
  const session: Session = {
    accessToken: result.access_token,
    user: result.user,
    organizationId,
  };
  saveSession(session);
  return session;
}
