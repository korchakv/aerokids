"""payments and subscriptions

Revision ID: 0003_payments
Revises: 0002_attendance
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_payments"
down_revision = "0002_attendance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("lessons_included", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_subscription_plan_org_name"),
    )
    op.create_index("ix_subscription_plans_organization_id", "subscription_plans", ["organization_id"])

    op.create_table(
        "student_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "PAUSED", "EXPIRED", "CANCELLED", name="subscriptionstatus"), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("discount_minor", sa.Integer(), nullable=False),
        sa.Column("discount_label", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_student_subscriptions_organization_id", "student_subscriptions", ["organization_id"])
    op.create_index("ix_student_subscriptions_student_id", "student_subscriptions", ["student_id"])
    op.create_index("ix_student_subscriptions_plan_id", "student_subscriptions", ["plan_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), sa.ForeignKey("student_subscriptions.id")),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "PAID", "REFUNDED", "CANCELLED", name="paymentstatus"), nullable=False),
        sa.Column("method", sa.Enum("CASH", "CARD", "BANK", "OTHER", name="paymentmethod")),
        sa.Column("due_date", sa.Date()),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_organization_id", "payments", ["organization_id"])
    op.create_index("ix_payments_student_id", "payments", ["student_id"])
    op.create_index("ix_payments_subscription_id", "payments", ["subscription_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("student_subscriptions")
    op.drop_table("subscription_plans")
