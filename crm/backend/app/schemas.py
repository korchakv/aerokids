from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.core import AttendanceStatus, CrmStatus, EnrollmentStatus, LessonStatus, PaymentMethod, PaymentStatus, StaffRole, StudentStatus, SubscriptionStatus, TrialStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=2, max_length=100)


class OrganizationRead(ORMModel):
    id: UUID
    name: str
    slug: str
    created_at: datetime


class LocationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    address: str | None = Field(default=None, max_length=300)


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


class ContactRead(ORMModel):
    id: UUID
    organization_id: UUID
    full_name: str
    phone: str
    email: str | None
    notes: str | None


class StudentCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    birth_date: date | None = None
    age_at_inquiry: int | None = Field(default=None, ge=3, le=25)
    source: str | None = Field(default=None, max_length=80)
    notes: str | None = None


class StudentRead(ORMModel):
    id: UUID
    organization_id: UUID
    first_name: str
    last_name: str | None
    birth_date: date | None
    age_at_inquiry: int | None
    source: str | None
    crm_status: CrmStatus
    student_status: StudentStatus
    notes: str | None


class StudentContactCreate(BaseModel):
    contact_id: UUID
    relation: str | None = Field(default=None, max_length=60)
    is_primary: bool = False


class TrialLessonCreate(BaseModel):
    student_id: UUID
    location_id: UUID | None = None
    starts_at: datetime


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


class IntakeCreate(BaseModel):
    child_first_name: str = Field(min_length=1, max_length=120)
    child_age: int = Field(ge=3, le=25)
    contact_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=8, max_length=40)
    comment: str | None = None
    source: str = Field(default="website", max_length=80)


class IntakeResult(BaseModel):
    student_id: UUID
    contact_id: UUID
    crm_status: CrmStatus


class StudentStatusUpdate(BaseModel):
    crm_status: CrmStatus


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


class GroupFormationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    location_id: UUID | None = None
    capacity: int = Field(default=8, ge=1, le=100)
    min_age: int | None = Field(default=None, ge=3, le=30)
    max_age: int | None = Field(default=None, ge=3, le=30)
    student_ids: list[UUID] = Field(min_length=1)


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


class AttendanceMark(BaseModel):
    student_id: UUID
    status: AttendanceStatus
    note: str | None = Field(default=None, max_length=300)


class AttendanceBulkUpdate(BaseModel):
    items: list[AttendanceMark] = Field(min_length=1)


class AttendanceRead(ORMModel):
    id: UUID
    organization_id: UUID
    session_id: UUID
    student_id: UUID
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


class SubscriptionPlanRead(ORMModel):
    id: UUID
    organization_id: UUID
    name: str
    price_minor: int
    period_days: int
    lessons_included: int | None
    is_active: bool


class StudentSubscriptionCreate(BaseModel):
    student_id: UUID
    plan_id: UUID
    starts_on: date
    price_minor: int | None = Field(default=None, ge=0)
    discount_minor: int = Field(default=0, ge=0)
    discount_label: str | None = Field(default=None, max_length=160)


class StudentSubscriptionRead(ORMModel):
    id: UUID
    organization_id: UUID
    student_id: UUID
    plan_id: UUID
    status: SubscriptionStatus
    starts_on: date
    ends_on: date
    price_minor: int
    discount_minor: int
    discount_label: str | None


class PaymentCreate(BaseModel):
    student_id: UUID
    subscription_id: UUID | None = None
    amount_minor: int = Field(gt=0)
    due_date: date | None = None
    note: str | None = Field(default=None, max_length=300)


class PaymentMarkPaid(BaseModel):
    method: PaymentMethod
    paid_at: datetime | None = None


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


class PaymentSummary(BaseModel):
    paid_minor: int
    pending_minor: int
    overdue_minor: int
    paid_count: int
    pending_count: int
    overdue_count: int


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    role: StaffRole
    notes: str | None = None
    location_ids: list[UUID] = []


class StaffRead(ORMModel):
    id: UUID
    organization_id: UUID
    user_id: UUID | None
    full_name: str
    email: str | None
    phone: str | None
    role: StaffRole
    is_active: bool
    notes: str | None


class StaffUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    role: StaffRole | None = None
    is_active: bool | None = None
    notes: str | None = None


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


class LeadListItem(BaseModel):
    student_id: UUID
    first_name: str
    last_name: str | None
    age: int | None
    source: str | None
    crm_status: CrmStatus
    contact_name: str | None
    contact_phone: str | None
    latest_trial_id: UUID | None
    latest_trial_at: datetime | None
    recommended_level: str | None


class StudentOverviewItem(BaseModel):
    student_id: UUID
    first_name: str
    last_name: str | None
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


class AuditEventRead(ORMModel):
    id: UUID
    organization_id: UUID
    actor_user_id: UUID | None
    entity_type: str
    entity_id: UUID | None
    event_type: str
    payload: dict | None
    created_at: datetime
