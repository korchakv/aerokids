"""subscription tariff rule snapshots

Revision ID: 0025_subscription_rule_snapshots
Revises: 0024_billing_concurrency
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_subscription_rule_snapshots"
down_revision = "0024_billing_concurrency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_rule_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("usage_mode", sa.String(length=24), nullable=False),
        sa.Column("absent_rule", sa.String(length=24), nullable=False),
        sa.Column("excused_rule", sa.String(length=24), nullable=False),
        sa.Column("late_rule", sa.String(length=24), nullable=False),
        sa.Column("end_rule", sa.String(length=24), nullable=False),
        sa.Column("renewal_trigger", sa.String(length=24), nullable=False),
        sa.Column("allow_debt", sa.Boolean(), nullable=False),
        sa.Column("max_lates", sa.Integer(), nullable=True),
        sa.Column("makeup_expiry_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["student_subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", name="uq_subscription_rule_snapshot"),
    )
    op.create_index("ix_subscription_rule_snapshots_organization_id", "subscription_rule_snapshots", ["organization_id"])
    op.create_index("ix_subscription_rule_snapshots_subscription_id", "subscription_rule_snapshots", ["subscription_id"])


def downgrade() -> None:
    op.drop_table("subscription_rule_snapshots")
