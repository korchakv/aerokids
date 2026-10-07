"""attendance reconciliation and notification outbox

Revision ID: 0023_reconciliation_outbox
Revises: 0022_core_hardening
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_reconciliation_outbox"
down_revision = "0022_core_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("consume_lesson", sa.Boolean(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["lesson_sessions.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "student_id", name="uq_attendance_decision_session_student"),
    )
    op.create_index("ix_attendance_decisions_organization_id", "attendance_decisions", ["organization_id"])
    op.create_index("ix_attendance_decisions_session_id", "attendance_decisions", ["session_id"])
    op.create_index("ix_attendance_decisions_student_id", "attendance_decisions", ["student_id"])

    op.create_table(
        "individual_derived_billing",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("parent_subscription_id", sa.Uuid(), nullable=False),
        sa.Column("renewal_subscription_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("parent_credit_before_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["individual_lesson_sessions.id"]),
        sa.ForeignKeyConstraint(["parent_subscription_id"], ["student_subscriptions.id"]),
        sa.ForeignKeyConstraint(["renewal_subscription_id"], ["student_subscriptions.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "renewal_subscription_id", name="uq_individual_derived_renewal"),
    )
    op.create_index("ix_individual_derived_billing_organization_id", "individual_derived_billing", ["organization_id"])
    op.create_index("ix_individual_derived_billing_session_id", "individual_derived_billing", ["session_id"])

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("template_key", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_outbox_organization_id", "notification_outbox", ["organization_id"])
    op.create_index("ix_notification_outbox_kind", "notification_outbox", ["kind"])
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"])


def downgrade() -> None:
    op.drop_table("notification_outbox")
    op.drop_table("individual_derived_billing")
    op.drop_table("attendance_decisions")
