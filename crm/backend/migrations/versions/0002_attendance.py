"""attendance and scheduling

Revision ID: 0002_attendance
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_attendance"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("group_id", "weekday", "start_time", name="uq_group_schedule_slot"),
    )
    op.create_index("ix_group_schedules_organization_id", "group_schedules", ["organization_id"])
    op.create_index("ix_group_schedules_group_id", "group_schedules", ["group_id"])

    op.create_table(
        "lesson_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("locations.id")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(240)),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.Enum("SCHEDULED", "COMPLETED", "CANCELLED", name="lessonstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lesson_sessions_organization_id", "lesson_sessions", ["organization_id"])
    op.create_index("ix_lesson_sessions_group_id", "lesson_sessions", ["group_id"])
    op.create_index("ix_lesson_sessions_location_id", "lesson_sessions", ["location_id"])
    op.create_index("ix_lesson_sessions_starts_at", "lesson_sessions", ["starts_at"])

    op.create_table(
        "attendance",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("status", sa.Enum("PRESENT", "ABSENT", "LATE", "EXCUSED", name="attendancestatus"), nullable=False),
        sa.Column("note", sa.String(300)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),
    )
    op.create_index("ix_attendance_organization_id", "attendance", ["organization_id"])
    op.create_index("ix_attendance_session_id", "attendance", ["session_id"])
    op.create_index("ix_attendance_student_id", "attendance", ["student_id"])


def downgrade() -> None:
    op.drop_table("attendance")
    op.drop_table("lesson_sessions")
    op.drop_table("group_schedules")
