from datetime import date, datetime, time
import re
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.core import AttendanceStatus, AvailabilityPreference, CrmStatus, EnrollmentStatus, LessonStatus, PaymentMethod, PaymentStatus, StaffRole, StudentStatus, SubscriptionStatus, TrialStatus


def validate_quarter_hour(value: time) -> time:
    if value.minute % 15 or value.second or value.microsecond:
        raise ValueError("time must be on a 15-minute boundary")
    return value


def validate_datetime_quarter_hour(value: datetime) -> datetime:
    validate_quarter_hour(value.timetz().replace(tzinfo=None))
    return value


def normalize_person_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    if len(value) < 2:
        raise ValueError("Вкажіть ім’я щонайменше з 2 символів")
    if not re.fullmatch(r"[A-Za-zА-Яа-яІіЇїЄєҐґ'’\- ]+", value):
        raise ValueError("Ім’я може містити лише літери, пробіл, апостроф і дефіс")
    if re.search(r"(^|[ '\-’])[ '\-’]", value) or value[0] in "'’- " or value[-1] in "'’- ":
        raise ValueError("Перевірте написання імені")
    return value


def normalize_ua_phone(value: str) -> str:
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("380") and len(digits) == 12:
        national = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        national = digits[1:]
    elif len(digits) == 9:
        national = digits
    else:
        raise ValueError("Вкажіть український номер у форматі +380 XX XXX XX XX")

    if not re.fullmatch(r"[3-9]\d{8}", national):
        raise ValueError("Некоректний номер телефону України")
    return "+380" + national


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    if not value:
        return None
    if len(value) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", value):
        raise ValueError("Некоректна email-адреса")
    return value


def normalize_required_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    if not value:
        raise ValueError("Поле не може бути порожнім")
    return value


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value.strip())
    return value or None

def normalize_lead_source(value: str | None) -> str | None:
    if value is None:
        return None
    raw = re.sub(r"\s+", " ", value.strip()).lower()
    if not raw:
        return None
    aliases = {
        "phone": "phone",
        "iphone": "phone",
        "телефон": "phone",
        "дзвінок": "phone",
        "website": "website",
        "site": "website",
        "сайт": "website",
        "instagram": "instagram",
        "insta": "instagram",
        "recommendation": "recommendation",
        "referral": "recommendation",
        "рекомендація": "recommendation",
        "walk-in": "walk-in",
        "walk_in": "walk-in",
        "walk in": "walk-in",
        "facebook": "facebook",
        "tiktok": "tiktok",
        "google": "google",
        "maps": "maps",
        "google maps": "maps",
        "other": "other",
    }
    return aliases.get(raw, raw)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=2, max_length=100)
    timezone: str = Field(default="Europe/Kyiv", min_length=2, max_length=64)
    currency: str = Field(default="UAH", pattern=r"^[A-Z]{3}$")
    locale: str = Field(default="uk-UA", min_length=2, max_length=20)

    _name = field_validator("name")(normalize_required_text)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    timezone: str | None = Field(default=None, min_length=2, max_length=64)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    locale: str | None = Field(default=None, min_length=2, max_length=20)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str | None) -> str | None:
        return normalize_required_text(value) if value is not None else None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class OrganizationRead(ORMModel):
    id: UUID
    name: str
    slug: str
    timezone: str
    currency: str
    locale: str
    created_at: datetime


class LocationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    address: str | None = Field(default=None, max_length=300)

    _name = field_validator("name")(normalize_required_text)
    _address = field_validator("address")(normalize_optional_text)


class LocationRead(ORMModel):
    id: UUID
    organization_id: UUID
    name: str
    address: str | None
    is_active: bool


class ContactCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=8, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    _name = field_validator("full_name")(normalize_person_name)
    _phone = field_validator("phone")(normalize_ua_phone)
    _email = field_validator("email")(normalize_email)


class ContactRead(ORMModel):
    id: UUID
    organization_id: UUID
    full_name: str
    phone: str
    email: str | None
    notes: str | None


class StudentCreate(BaseModel):
    first_name: str = Field(min_length=2, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    birth_date: date | None = None
    age_at_inquiry: int | None = Field(default=None, ge=3, le=25)
    source: str | None = Field(default=None, max_length=80)
    notes: str | None = None

    _first_name = field_validator("first_name")(normalize_person_name)

    @field_validator("last_name")
    @classmethod
    def valid_last_name(cls, value: str | None) -> str | None:
        return normalize_person_name(value) if value else None

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return normalize_ua_phone(value) if value and value.strip() else None

    @field_validator("source")
    @classmethod
    def valid_source(cls, value: str | None) -> str | None:
        return normalize_lead_source(value)


class StudentRead(ORMModel):
    id: UUID
    organization_id: UUID
    first_name: str
    last_name: str | None
    phone: str | None
    birth_date: date | None
    age_at_inquiry: int | None
    source: str | None
    preferred_location_id: UUID | None
    crm_status: CrmStatus
    student_status: StudentStatus
    next_contact_at: datetime | None
    lead_close_reason: str | None
    lead_close_note: str | None
    notes: str | None


class StudentContactCreate(BaseModel):
    contact_id: UUID
    relation: str | None = Field(default=None, max_length=60)
    is_primary: bool = False


class TrialLessonCreate(BaseModel):
    student_id: UUID
    location_id: UUID | None = None
    starts_at: datetime

    _quarter_hour = field_validator("starts_at")(validate_datetime_quarter_hour)


class TrialLessonRead(ORMModel):
    id: UUID
    organization_id: UUID
    location_id: UUID | None
    student_id: UUID
    starts_at: datetime
    status: TrialStatus
    recommended_level: str | None
    teacher_notes: str | None


class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    location_id: UUID | None = None
    capacity: int | None = Field(default=None, ge=1, le=100)
    min_age: int | None = Field(default=None, ge=3, le=30)
    max_age: int | None = Field(default=None, ge=3, le=30)

    _name = field_validator("name")(normalize_required_text)


class GroupRead(ORMModel):
    id: UUID
    organization_id: UUID
    location_id: UUID | None
    name: str
    capacity: int | None
    min_age: int | None
    max_age: int | None
    is_active: bool


class EnrollmentCreate(BaseModel):
    student_id: UUID
    group_id: UUID
    started_at: date | None = None


class EnrollmentRead(ORMModel):
    id: UUID
    organization_id: UUID
    student_id: UUID
    group_id: UUID
    status: EnrollmentStatus
    started_at: date
    ended_at: date | None
    schedule_match: str | None
    schedule_note: str | None


class IntakeCreate(BaseModel):
    child_first_name: str = Field(min_length=2, max_length=120)
    child_last_name: str | None = Field(default=None, max_length=120)
    child_phone: str | None = Field(default=None, max_length=40)
    child_age: int = Field(ge=3, le=25)
    contact_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=8, max_length=40)
    comment: str | None = None
    source: str = Field(default="website", max_length=80)
    website: str | None = Field(default=None, max_length=200)

    _child_name = field_validator("child_first_name")(normalize_person_name)

    @field_validator("child_last_name")
    @classmethod
    def valid_child_last_name(cls, value: str | None) -> str | None:
        return normalize_person_name(value) if value else None

    @field_validator("child_phone")
    @classmethod
    def valid_child_phone(cls, value: str | None) -> str | None:
        return normalize_ua_phone(value) if value and value.strip() else None

    @field_validator("source")
    @classmethod
    def valid_intake_source(cls, value: str) -> str:
        return normalize_lead_source(value) or "website"

    _contact_name = field_validator("contact_name")(normalize_person_name)
    _phone = field_validator("phone")(normalize_ua_phone)


class IntakeResult(BaseModel):
    student_id: UUID
    contact_id: UUID
    crm_status: CrmStatus


class IntakeDuplicateCheck(BaseModel):
    child_first_name: str = Field(min_length=2, max_length=120)
    child_age: int = Field(ge=3, le=25)
    phone: str = Field(min_length=8, max_length=40)
    child_phone: str | None = Field(default=None, max_length=40)

    _child_name = field_validator("child_first_name")(normalize_person_name)
    _phone = field_validator("phone")(normalize_ua_phone)

    @field_validator("child_phone")
    @classmethod
    def valid_child_phone(cls, value: str | None) -> str | None:
        return normalize_ua_phone(value) if value and value.strip() else None


class IntakeDuplicateMatch(BaseModel):
    student_id: UUID
    first_name: str
    last_name: str | None
    age: int | None
    crm_status: CrmStatus
    student_status: StudentStatus
    student_phone: str | None
    contact_name: str | None
    contact_phone: str | None
    matched_phone: str
    matched_as: str
    likely_same_student: bool


class IntakeDuplicateResult(BaseModel):
    matches: list[IntakeDuplicateMatch]


class StudentStatusUpdate(BaseModel):
    crm_status: CrmStatus


class LeadOutcomeUpdate(BaseModel):
    crm_status: CrmStatus
    next_contact_at: datetime | None = None
    close_reason: str | None = Field(default=None, max_length=80)
    close_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_outcome(self):
        allowed = {
            CrmStatus.CONTACTED,
            CrmStatus.TRIAL_COMPLETED,
            CrmStatus.WAITING_FOR_GROUP,
            CrmStatus.DECLINED,
            CrmStatus.NO_RESPONSE,
            CrmStatus.NOT_RELEVANT,
        }
        if self.crm_status not in allowed:
            raise ValueError("Unsupported lead outcome status")
        if self.crm_status == CrmStatus.DECLINED and not self.close_reason:
            raise ValueError("close_reason is required when lead is declined")
        if self.crm_status not in {CrmStatus.DECLINED, CrmStatus.NO_RESPONSE, CrmStatus.NOT_RELEVANT}:
            self.close_reason = None
            self.close_note = None
        return self


class TrialLessonUpdate(BaseModel):
    starts_at: datetime | None = None
    location_id: UUID | None = None

    @field_validator("starts_at")
    @classmethod
    def quarter_hour(cls, value: datetime | None) -> datetime | None:
        return validate_datetime_quarter_hour(value) if value else value


class TrialLessonComplete(BaseModel):
    status: TrialStatus = TrialStatus.COMPLETED
    recommended_level: str | None = Field(default=None, max_length=80)
    teacher_notes: str | None = None


class StudentDetail(StudentRead):
    contacts: list[ContactRead] = []
    trial_lessons: list[TrialLessonRead] = []


class WaitingCandidate(BaseModel):
    student_id: UUID
    first_name: str
    last_name: str | None
    age: int | None
    recommended_level: str | None
    source: str | None


class GroupFormationScheduleSlot(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_minutes: int = Field(default=60, ge=15, le=360)

    @field_validator("start_time")
    @classmethod
    def quarter_hour(cls, value: str) -> str:
        validate_quarter_hour(time.fromisoformat(value))
        return value


class GroupFormationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    location_id: UUID | None = None
    capacity: int = Field(default=8, ge=1, le=100)
    min_age: int | None = Field(default=None, ge=3, le=30)
    max_age: int | None = Field(default=None, ge=3, le=30)
    student_ids: list[UUID] = Field(default_factory=list)
    schedule_slots: list[GroupFormationScheduleSlot] = Field(default_factory=list)

    _name = field_validator("name")(normalize_required_text)

    @model_validator(mode="after")
    def unique_schedule_slots(self):
        keys = [(slot.weekday, slot.start_time) for slot in self.schedule_slots]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate group schedule slots are not allowed")
        return self


class GroupFormationResult(BaseModel):
    group: GroupRead
    enrolled_student_ids: list[UUID]


class StudentLifecycleUpdate(BaseModel):
    student_status: StudentStatus


class StudentGroupInfo(BaseModel):
    group_id: UUID
    group_name: str
    enrollment_id: UUID
    enrollment_status: EnrollmentStatus
    started_at: date
    location_id: UUID | None


class StudentProfile(StudentDetail):
    groups: list[StudentGroupInfo] = []


class StudentTransfer(BaseModel):
    to_group_id: UUID
    started_at: date | None = None


class GroupScheduleCreate(BaseModel):
    group_id: UUID
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_minutes: int = Field(default=60, ge=15, le=360)

    @field_validator("start_time")
    @classmethod
    def quarter_hour(cls, value: str) -> str:
        validate_quarter_hour(time.fromisoformat(value))
        return value


class GroupScheduleRead(ORMModel):
    id: UUID
    organization_id: UUID
    group_id: UUID
    weekday: int
    start_time: time
    duration_minutes: int
    is_active: bool


class LessonSessionCreate(BaseModel):
    group_id: UUID
    location_id: UUID | None = None
    starts_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=360)
    topic: str | None = Field(default=None, max_length=240)
    notes: str | None = None

    _quarter_hour = field_validator("starts_at")(validate_datetime_quarter_hour)


class LessonSessionRead(ORMModel):
    id: UUID
    organization_id: UUID
    group_id: UUID
    location_id: UUID | None
    starts_at: datetime
    duration_minutes: int
    topic: str | None
    notes: str | None
    status: LessonStatus
    attendance_present: int = 0
    attendance_absent: int = 0
    attendance_late: int = 0
    attendance_excused: int = 0
    attendance_total: int = 0


class LessonSessionUpdate(BaseModel):
    topic: str | None = Field(default=None, max_length=240)
    notes: str | None = Field(default=None, max_length=4000)

    _topic = field_validator("topic")(normalize_optional_text)
    _notes = field_validator("notes")(normalize_optional_text)


class AttendanceMark(BaseModel):
    student_id: UUID
    status: AttendanceStatus
    note: str | None = Field(default=None, max_length=300)
    consume_lesson: bool | None = None


class AttendanceBulkUpdate(BaseModel):
    items: list[AttendanceMark] = Field(min_length=1)


class AttendanceRead(ORMModel):
    id: UUID
    organization_id: UUID
    session_id: UUID
    student_id: UUID
    status: AttendanceStatus
    note: str | None


class StudentAttendanceHistoryItem(BaseModel):
    session_id: UUID
    group_id: UUID
    group_name: str
    starts_at: datetime
    duration_minutes: int
    topic: str | None
    lesson_status: LessonStatus
    status: AttendanceStatus
    note: str | None


class GroupRosterStudent(BaseModel):
    student_id: UUID
    first_name: str
    last_name: str | None
    age: int | None


class SubscriptionPlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    price_minor: int = Field(ge=0)
    period_days: int = Field(default=30, ge=1, le=366)
    lessons_included: int | None = Field(default=None, ge=1, le=365)
    usage_mode: Literal["attendance", "scheduled", "period"] = "attendance"
    absent_rule: Literal["consume", "dont_consume", "choice"] = "choice"
    excused_rule: Literal["consume", "dont_consume", "makeup"] = "makeup"
    late_rule: Literal["consume", "dont_consume"] = "consume"
    end_rule: Literal["lessons", "date", "whichever_first"] = "whichever_first"
    renewal_trigger: Literal["last_lesson", "date", "manual"] = "last_lesson"
    allow_debt: bool = True
    max_lates: int | None = Field(default=None, ge=1, le=100)
    makeup_expiry_days: int | None = Field(default=None, ge=1, le=366)

    _name = field_validator("name")(normalize_required_text)


class SubscriptionPlanRead(ORMModel):
    id: UUID
    organization_id: UUID
    name: str
    price_minor: int
    period_days: int
    lessons_included: int | None
    usage_mode: str
    absent_rule: str
    excused_rule: str
    late_rule: str
    end_rule: str
    renewal_trigger: str
    allow_debt: bool
    max_lates: int | None
    makeup_expiry_days: int | None
    is_active: bool


class StudentSubscriptionCreate(BaseModel):
    student_id: UUID
    plan_id: UUID
    group_id: UUID | None = None
    starts_on: date
    price_minor: int | None = Field(default=None, ge=0)
    discount_minor: int = Field(default=0, ge=0)
    discount_label: str | None = Field(default=None, max_length=160)
    auto_renew: bool = False


class StudentSubscriptionRead(ORMModel):
    id: UUID
    organization_id: UUID
    student_id: UUID
    plan_id: UUID
    group_id: UUID | None
    status: SubscriptionStatus
    starts_on: date
    ends_on: date
    price_minor: int
    discount_minor: int
    discount_label: str | None
    auto_renew: bool
    renewal_of_id: UUID | None
    used_lessons: int = 0
    remaining_lessons: int | None = None
    needs_renewal: bool = False


class PaymentCreate(BaseModel):
    student_id: UUID
    subscription_id: UUID | None = None
    amount_minor: int = Field(gt=0)
    due_date: date | None = None
    note: str | None = Field(default=None, max_length=300)


class SubscriptionChargeCreate(BaseModel):
    student_id: UUID
    plan_id: UUID
    group_id: UUID | None = None
    starts_on: date
    due_date: date | None = None
    discount_minor: int = Field(default=0, ge=0)
    discount_label: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=300)
    auto_renew: bool = False


class PaymentMarkPaid(BaseModel):
    method: PaymentMethod
    paid_at: datetime | None = None


class PaymentReceiptCreate(BaseModel):
    amount_minor: int = Field(gt=0)
    method: PaymentMethod
    paid_at: datetime | None = None
    note: str | None = Field(default=None, max_length=300)


class PaymentRefundCreate(BaseModel):
    amount_minor: int = Field(gt=0)
    note: str = Field(min_length=2, max_length=300)
    occurred_at: datetime | None = None
    reduce_charge: bool = True


class PaymentAdjustmentCreate(BaseModel):
    direction: Literal["increase", "decrease"]
    amount_minor: int = Field(gt=0)
    reason: str = Field(min_length=2, max_length=300)


class PaymentTransactionRead(ORMModel):
    id: UUID
    organization_id: UUID
    payment_id: UUID
    student_id: UUID
    kind: str
    amount_minor: int
    method: PaymentMethod | None
    note: str | None
    occurred_at: datetime


class PaymentRead(ORMModel):
    id: UUID
    organization_id: UUID
    student_id: UUID
    subscription_id: UUID | None
    plan_id: UUID | None = None
    amount_minor: int
    currency: str
    status: PaymentStatus
    method: PaymentMethod | None
    due_date: date | None
    paid_at: datetime | None
    note: str | None
    adjusted_amount_minor: int = 0
    paid_minor: int = 0
    refunded_minor: int = 0
    balance_minor: int = 0


class SubscriptionChargeResult(BaseModel):
    subscription: StudentSubscriptionRead
    payment: PaymentRead


class PaymentSummary(BaseModel):
    paid_minor: int
    pending_minor: int
    overdue_minor: int
    paid_count: int
    pending_count: int
    overdue_count: int


class GroupMemberAttendanceSummary(BaseModel):
    present: int
    absent: int
    late: int
    excused: int
    total: int
    attendance_rate: float


class GroupMemberBillingSummary(BaseModel):
    status: Literal["current", "upcoming", "due", "overdue", "no_plan"]
    plan_name: str | None = None
    lessons_used: int | None = None
    lessons_included: int | None = None
    lessons_remaining: int | None = None
    amount_due_minor: int = 0
    next_due_date: date | None = None
    last_paid_at: datetime | None = None
    last_paid_minor: int | None = None
    subscription_ends_on: date | None = None


class GroupMemberDetail(BaseModel):
    student_id: UUID
    first_name: str
    last_name: str | None
    student_phone: str | None
    age: int | None
    contact_name: str | None
    contact_phone: str | None
    enrollment_started_at: date
    enrollment_status: EnrollmentStatus
    attendance: GroupMemberAttendanceSummary
    billing: GroupMemberBillingSummary | None = None
    payments: list[PaymentRead] = Field(default_factory=list)


class GroupDetail(BaseModel):
    group: GroupRead
    schedules: list[GroupScheduleRead] = Field(default_factory=list)
    members: list[GroupMemberDetail] = Field(default_factory=list)


class PaymentReminderCandidate(BaseModel):
    payment_id: UUID
    student_id: UUID
    student_name: str
    contact_name: str | None
    contact_phone: str | None
    amount_minor: int
    currency: str
    due_date: date
    days_from_due: int
    stage: Literal["upcoming_3", "due_today", "overdue_1", "overdue_3", "overdue_7", "overdue_14", "overdue_30"]
    label: str
    last_reminder_at: datetime | None = None


class PaymentReminderMark(BaseModel):
    stage: Literal["upcoming_3", "due_today", "overdue_1", "overdue_3", "overdue_7", "overdue_14", "overdue_30"]
    channel: Literal["manual", "sms", "email", "messenger", "phone"] = "manual"


class PaymentCancel(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


class SubscriptionAutoRenewUpdate(BaseModel):
    auto_renew: bool


class SubscriptionPauseCreate(BaseModel):
    starts_on: date
    resume_on: date | None = None
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_pause_dates(self):
        if self.resume_on is not None and self.resume_on <= self.starts_on:
            raise ValueError("resume_on must be after starts_on")
        return self


class SubscriptionResumeCreate(BaseModel):
    resumes_on: date | None = None


class SubscriptionPauseRead(ORMModel):
    id: UUID
    organization_id: UUID
    subscription_id: UUID
    student_id: UUID
    starts_on: date
    ends_on: date | None
    resumed_at: datetime | None
    note: str | None


class BillingRenewalRun(BaseModel):
    through_date: date | None = None


class BillingRenewalResult(BaseModel):
    resumed_subscriptions: int
    created_subscriptions: int
    skipped_stale_subscriptions: int = 0
    created_payment_ids: list[UUID] = Field(default_factory=list)


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    role: StaffRole
    can_teach: bool = False
    notes: str | None = None
    location_ids: list[UUID] = []

    _name = field_validator("full_name")(normalize_person_name)
    _email = field_validator("email")(normalize_email)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return normalize_ua_phone(value) if value and value.strip() else None


class StaffRead(ORMModel):
    id: UUID
    organization_id: UUID
    user_id: UUID | None
    full_name: str
    email: str | None
    phone: str | None
    role: StaffRole
    can_teach: bool
    is_active: bool
    notes: str | None


class StaffUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    role: StaffRole | None = None
    can_teach: bool | None = None
    is_active: bool | None = None
    notes: str | None = None

    @field_validator("full_name")
    @classmethod
    def valid_name(cls, value: str | None) -> str | None:
        return normalize_person_name(value) if value else None

    _email = field_validator("email")(normalize_email)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return normalize_ua_phone(value) if value and value.strip() else None


class StaffLocationAssignment(BaseModel):
    location_ids: list[UUID]


class StaffGroupAssignment(BaseModel):
    group_id: UUID
    is_primary: bool = False


class StaffAssignmentInfo(BaseModel):
    location_ids: list[UUID] = []
    group_ids: list[UUID] = []


class StaffProfile(StaffRead):
    assignments: StaffAssignmentInfo


class OrganizationMembershipCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    full_name: str | None = Field(default=None, max_length=160)
    role: StaffRole

    _email = field_validator("email")(normalize_email)

    @field_validator("full_name")
    @classmethod
    def valid_full_name(cls, value: str | None) -> str | None:
        return normalize_person_name(value) if value else None


class OrganizationMembershipRead(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    email: str
    full_name: str | None
    role: StaffRole
    is_active: bool


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    address: str | None = Field(default=None, max_length=300)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str | None) -> str | None:
        return normalize_required_text(value) if value is not None else None

    _address = field_validator("address")(normalize_optional_text)


class FunnelCount(BaseModel):
    status: CrmStatus
    count: int


class AttendanceSummary(BaseModel):
    present: int
    absent: int
    late: int
    excused: int
    total: int
    attendance_rate: float


class OverviewReport(BaseModel):
    funnel: list[FunnelCount]
    active_students: int
    active_groups: int
    enrolled_students: int
    group_capacity: int
    active_staff: int
    active_locations: int
    attendance: AttendanceSummary
    payments: PaymentSummary


class StudentAvailabilitySlot(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    preference: AvailabilityPreference = AvailabilityPreference.PREFERRED
    note: str | None = Field(default=None, max_length=300)

    _start_quarter = field_validator("start_time")(validate_quarter_hour)
    _end_quarter = field_validator("end_time")(validate_quarter_hour)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class StudentPreferencesUpdate(BaseModel):
    preferred_location_id: UUID | None = None
    availability: list[StudentAvailabilitySlot] = Field(default_factory=list)


class StudentPreferencesRead(BaseModel):
    preferred_location_id: UUID | None
    preferred_location_name: str | None
    availability: list[StudentAvailabilitySlot]


class ScheduleMatchSlot(BaseModel):
    weekday: int
    start_time: str
    end_time: str
    detail: str


class GroupMatchPreviewRequest(BaseModel):
    location_id: UUID | None = None
    schedule_slots: list[GroupFormationScheduleSlot]
    student_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_students(self):
        if len(self.student_ids) != len(set(self.student_ids)):
            raise ValueError("Duplicate students are not allowed")
        return self


class StudentScheduleMatch(BaseModel):
    student_id: UUID
    status: Literal["match", "partial", "conflict", "unknown"]
    summary: str
    matching_slots: list[ScheduleMatchSlot]
    partial_slots: list[ScheduleMatchSlot]
    conflicting_slots: list[ScheduleMatchSlot]


class GroupMatchPreviewResponse(BaseModel):
    students: list[StudentScheduleMatch]


class LeadListItem(BaseModel):
    student_id: UUID
    created_at: datetime
    first_name: str
    last_name: str | None
    student_phone: str | None
    age: int | None
    source: str | None
    comment: str | None
    preferred_location_id: UUID | None
    preferred_location_name: str | None
    availability: list[StudentAvailabilitySlot] = Field(default_factory=list)
    crm_status: CrmStatus
    contact_name: str | None
    contact_phone: str | None
    latest_trial_id: UUID | None
    latest_trial_at: datetime | None
    latest_trial_status: TrialStatus | None
    trial_location_id: UUID | None
    trial_location_name: str | None
    recommended_level: str | None
    teacher_notes: str | None
    next_contact_at: datetime | None
    close_reason: str | None
    close_note: str | None


class StudentOverviewItem(BaseModel):
    student_id: UUID
    first_name: str
    last_name: str | None
    student_phone: str | None
    age: int | None
    source: str | None
    student_status: StudentStatus
    contact_name: str | None
    contact_phone: str | None
    group_id: UUID | None
    group_name: str | None


class GroupOverviewItem(BaseModel):
    group_id: UUID
    name: str
    location_id: UUID | None
    location_name: str | None
    capacity: int | None
    enrolled_count: int
    min_age: int | None
    max_age: int | None
    primary_teacher_id: UUID | None = None
    primary_teacher_name: str | None = None


class AuditEventRead(ORMModel):
    id: UUID
    organization_id: UUID
    actor_user_id: UUID | None
    actor_name: str | None = None
    actor_email: str | None = None
    entity_type: str
    entity_id: UUID | None
    event_type: str
    payload: dict | None
    created_at: datetime
