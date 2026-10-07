"""core hardening support tables

Revision ID: 0022_core_hardening
Revises: 0021_deferred_leads
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_core_hardening"
down_revision = "0021_deferred_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "location_id", "name", name="uq_room_location_name"),
    )
    op.create_index("ix_rooms_organization_id", "rooms", ["organization_id"])
    op.create_index("ix_rooms_location_id", "rooms", ["location_id"])

    op.create_table(
        "group_room_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", name="uq_group_room_assignment"),
    )
    op.create_index("ix_group_room_assignments_organization_id", "group_room_assignments", ["organization_id"])
    op.create_index("ix_group_room_assignments_group_id", "group_room_assignments", ["group_id"])
    op.create_index("ix_group_room_assignments_room_id", "group_room_assignments", ["room_id"])

    op.create_table(
        "lesson_resource_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["lesson_sessions.id"]),
        sa.ForeignKeyConstraint(["staff_id"], ["staff.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_lesson_resource_assignment"),
    )
    op.create_index("ix_lesson_resource_assignments_organization_id", "lesson_resource_assignments", ["organization_id"])
    op.create_index("ix_lesson_resource_assignments_session_id", "lesson_resource_assignments", ["session_id"])
    op.create_index("ix_lesson_resource_assignments_staff_id", "lesson_resource_assignments", ["staff_id"])
    op.create_index("ix_lesson_resource_assignments_room_id", "lesson_resource_assignments", ["room_id"])

    op.create_table(
        "trial_resource_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("trial_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["trial_id"], ["trial_lessons.id"]),
        sa.ForeignKeyConstraint(["staff_id"], ["staff.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trial_id", name="uq_trial_resource_assignment"),
    )
    op.create_index("ix_trial_resource_assignments_organization_id", "trial_resource_assignments", ["organization_id"])
    op.create_index("ix_trial_resource_assignments_trial_id", "trial_resource_assignments", ["trial_id"])
    op.create_index("ix_trial_resource_assignments_staff_id", "trial_resource_assignments", ["staff_id"])
    op.create_index("ix_trial_resource_assignments_room_id", "trial_resource_assignments", ["room_id"])

    op.create_table(
        "group_schedule_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("slots", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_group_schedule_history_organization_id", "group_schedule_history", ["organization_id"])
    op.create_index("ix_group_schedule_history_group_id", "group_schedule_history", ["group_id"])

    op.create_table(
        "enrollment_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.Date(), nullable=False),
        sa.Column("ended_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enrollment_history_organization_id", "enrollment_history", ["organization_id"])
    op.create_index("ix_enrollment_history_student_id", "enrollment_history", ["student_id"])
    op.create_index("ix_enrollment_history_group_id", "enrollment_history", ["group_id"])

    op.create_table(
        "lesson_finalizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("finalized_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["lesson_sessions.id"]),
        sa.ForeignKeyConstraint(["finalized_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_lesson_finalization_session"),
    )
    op.create_index("ix_lesson_finalizations_organization_id", "lesson_finalizations", ["organization_id"])
    op.create_index("ix_lesson_finalizations_session_id", "lesson_finalizations", ["session_id"])

    op.create_table(
        "lesson_derived_billing",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("parent_subscription_id", sa.Uuid(), nullable=False),
        sa.Column("renewal_subscription_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("parent_credit_before_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["lesson_sessions.id"]),
        sa.ForeignKeyConstraint(["parent_subscription_id"], ["student_subscriptions.id"]),
        sa.ForeignKeyConstraint(["renewal_subscription_id"], ["student_subscriptions.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "renewal_subscription_id", name="uq_lesson_derived_renewal"),
    )
    op.create_index("ix_lesson_derived_billing_organization_id", "lesson_derived_billing", ["organization_id"])
    op.create_index("ix_lesson_derived_billing_session_id", "lesson_derived_billing", ["session_id"])

    op.create_table(
        "makeup_completion_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("target_session_id", sa.Uuid(), nullable=False),
        sa.Column("makeup_credit_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["target_session_id"], ["lesson_sessions.id"]),
        sa.ForeignKeyConstraint(["makeup_credit_id"], ["makeup_credits.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("makeup_credit_id", name="uq_makeup_completion_credit"),
    )
    op.create_index("ix_makeup_completion_links_organization_id", "makeup_completion_links", ["organization_id"])
    op.create_index("ix_makeup_completion_links_target_session_id", "makeup_completion_links", ["target_session_id"])

    op.create_table(
        "staff_capabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["staff_id"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("staff_id", "capability", name="uq_staff_capability"),
    )
    op.create_index("ix_staff_capabilities_organization_id", "staff_capabilities", ["organization_id"])
    op.create_index("ix_staff_capabilities_staff_id", "staff_capabilities", ["staff_id"])

    op.create_table(
        "individual_lesson_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("topic", sa.String(length=240), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="scheduled"),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.ForeignKeyConstraint(["staff_id"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_individual_lesson_sessions_organization_id", "individual_lesson_sessions", ["organization_id"])
    op.create_index("ix_individual_lesson_sessions_student_id", "individual_lesson_sessions", ["student_id"])
    op.create_index("ix_individual_lesson_sessions_starts_at", "individual_lesson_sessions", ["starts_at"])

    op.create_table(
        "individual_attendance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["individual_lesson_sessions.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_individual_attendance_session"),
    )
    op.create_index("ix_individual_attendance_organization_id", "individual_attendance", ["organization_id"])

    op.create_table(
        "individual_subscription_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["individual_lesson_sessions.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["student_subscriptions.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_individual_subscription_usage_session"),
    )
    op.create_index("ix_individual_subscription_usage_organization_id", "individual_subscription_usage", ["organization_id"])
    op.create_index("ix_individual_subscription_usage_subscription_id", "individual_subscription_usage", ["subscription_id"])


def downgrade() -> None:
    op.drop_table("individual_subscription_usage")
    op.drop_table("individual_attendance")
    op.drop_table("individual_lesson_sessions")
    op.drop_table("staff_capabilities")
    op.drop_table("makeup_completion_links")
    op.drop_table("lesson_derived_billing")
    op.drop_table("lesson_finalizations")
    op.drop_table("enrollment_history")
    op.drop_table("group_schedule_history")
    op.drop_table("trial_resource_assignments")
    op.drop_table("lesson_resource_assignments")
    op.drop_table("group_room_assignments")
    op.drop_table("rooms")
