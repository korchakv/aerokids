from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.core import CrmStatus, EnrollmentStatus, StudentStatus, TrialStatus


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
