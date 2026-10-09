// Shared frontend API contracts. Keep these data-only so feature modules can depend on them without importing request logic.

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

export type PageResult<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type WorkspaceBundle = {
  leads: WorkspaceLead[];
  students: WorkspaceStudent[];
  groups: WorkspaceGroup[];
};

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

export type InvitationStatus = "valid" | "accepted" | "expired" | "invalid";

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

export type ApiGroupRosterStudent = {
  student_id: string;
  first_name: string;
  last_name: string | null;
  age: number | null;
};

export type TeachingBundle = {
  schedules: ApiGroupSchedule[];
  lessons: ApiLessonSession[];
};

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
