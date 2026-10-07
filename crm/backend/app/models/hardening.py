from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", "name", name="uq_room_location_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GroupRoomAssignment(Base):
    __tablename__ = "group_room_assignments"
    __table_args__ = (UniqueConstraint("group_id", name="uq_group_room_assignment"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id"), index=True, nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True, nullable=False)


class LessonResourceAssignment(Base):
    __tablename__ = "lesson_resource_assignments"
    __table_args__ = (UniqueConstraint("session_id", name="uq_lesson_resource_assignment"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lesson_sessions.id"), index=True, nullable=False)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff.id"), index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id"), index=True)


class TrialResourceAssignment(Base):
    __tablename__ = "trial_resource_assignments"
    __table_args__ = (UniqueConstraint("trial_id", name="uq_trial_resource_assignment"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    trial_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trial_lessons.id"), index=True, nullable=False)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff.id"), index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id"), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)


class GroupScheduleHistory(Base):
    __tablename__ = "group_schedule_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id"), index=True, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"), index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id"), index=True)
    slots: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class EnrollmentHistory(Base):
    __tablename__ = "enrollment_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), index=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"), index=True, nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id"), index=True, nullable=False)
    started_at: Mapped[date] = mapped_column(Date, nullable=False)
    ended_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LessonFinalization(Base):
    __tablename__ = "lesson_finalizations"
    __table_args__ = (UniqueConstraint("session_id", name="uq_lesson_finalization_session"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lesson_sessions.id"), index=True, nullable=False)
    finalized_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LessonDerivedBilling(Base):
    __tablename__ = "lesson_derived_billing"
    __table_args__ = (
        UniqueConstraint("session_id", "renewal_subscription_id", name="uq_lesson_derived_renewal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lesson_sessions.id"), index=True, nullable=False)
    parent_subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student_subscriptions.id"), index=True, nullable=False)
    renewal_subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student_subscriptions.id"), index=True, nullable=False)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True, nullable=False)
    parent_credit_before_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MakeupCompletionLink(Base):
    __tablename__ = "makeup_completion_links"
    __table_args__ = (UniqueConstraint("makeup_credit_id", name="uq_makeup_completion_credit"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    target_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lesson_sessions.id"), index=True, nullable=False)
    makeup_credit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("makeup_credits.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class StaffCapability(Base):
    __tablename__ = "staff_capabilities"
    __table_args__ = (UniqueConstraint("staff_id", "capability", name="uq_staff_capability"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"), index=True, nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class IndividualLessonSession(Base):
    __tablename__ = "individual_lesson_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"), index=True, nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"), index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id"), index=True)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(240))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="scheduled", nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IndividualAttendance(Base):
    __tablename__ = "individual_attendance"
    __table_args__ = (UniqueConstraint("session_id", name="uq_individual_attendance_session"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("individual_lesson_sessions.id"), index=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IndividualSubscriptionUsage(Base):
    __tablename__ = "individual_subscription_usage"
    __table_args__ = (UniqueConstraint("session_id", name="uq_individual_subscription_usage_session"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("individual_lesson_sessions.id"), index=True, nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student_subscriptions.id"), index=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"), index=True, nullable=False)
    units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
