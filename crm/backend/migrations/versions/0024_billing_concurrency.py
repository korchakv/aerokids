"""billing concurrency and query indexes

Revision ID: 0024_billing_concurrency
Revises: 0023_reconciliation_outbox
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_billing_concurrency"
down_revision = "0023_reconciliation_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    active_renewal_predicate = sa.text("renewal_of_id IS NOT NULL AND status <> 'CANCELLED'")
    op.create_index(
        "uq_student_subscription_active_renewal",
        "student_subscriptions",
        ["renewal_of_id"],
        unique=True,
        postgresql_where=active_renewal_predicate,
        sqlite_where=active_renewal_predicate,
    )
    op.create_index(
        "ix_enrollments_org_group_status",
        "enrollments",
        ["organization_id", "group_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_enrollments_org_student_status",
        "enrollments",
        ["organization_id", "student_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_lesson_sessions_org_group_start",
        "lesson_sessions",
        ["organization_id", "group_id", "starts_at"],
        unique=False,
    )
    op.create_index(
        "ix_payments_org_student_status_due",
        "payments",
        ["organization_id", "student_id", "status", "due_date"],
        unique=False,
    )
    op.create_index(
        "ix_students_org_lifecycle_crm",
        "students",
        ["organization_id", "student_status", "crm_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_students_org_lifecycle_crm", table_name="students")
    op.drop_index("ix_payments_org_student_status_due", table_name="payments")
    op.drop_index("ix_lesson_sessions_org_group_start", table_name="lesson_sessions")
    op.drop_index("ix_enrollments_org_student_status", table_name="enrollments")
    op.drop_index("ix_enrollments_org_group_status", table_name="enrollments")
    op.drop_index("uq_student_subscription_active_renewal", table_name="student_subscriptions")
