from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AttendanceDecision(Base):
    __tablename__ = "attendance_decisions"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_decision_session_student"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lesson_sessions.id"), index=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"), index=True, nullable=False)
    consume_lesson: Mapped[bool | None] = mapped_column(Boolean)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IndividualDerivedBilling(Base):
    __tablename__ = "individual_derived_billing"
    __table_args__ = (UniqueConstraint("session_id", "renewal_subscription_id", name="uq_individual_derived_renewal"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("individual_lesson_sessions.id"), index=True, nullable=False)
    parent_subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student_subscriptions.id"), index=True, nullable=False)
    renewal_subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student_subscriptions.id"), index=True, nullable=False)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True, nullable=False)
    parent_credit_before_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    template_key: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
