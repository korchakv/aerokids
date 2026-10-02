"""billing ledger renewals and pauses

Revision ID: 0015_billing_ledger
Revises: 0014_payment_reminders
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_billing_ledger"
down_revision = "0014_payment_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("student_subscriptions") as batch:
        batch.add_column(sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("renewal_of_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_student_subscriptions_renewal_of_id",
            "student_subscriptions",
            ["renewal_of_id"],
            ["id"],
        )
        batch.create_index("ix_student_subscriptions_renewal_of_id", ["renewal_of_id"])

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("payment_id", sa.Uuid(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_payment_transactions_organization_id", "payment_transactions", ["organization_id"])
    op.create_index("ix_payment_transactions_payment_id", "payment_transactions", ["payment_id"])
    op.create_index("ix_payment_transactions_student_id", "payment_transactions", ["student_id"])
    op.create_index("ix_payment_transactions_kind", "payment_transactions", ["kind"])
    op.create_index("ix_payment_transactions_actor_user_id", "payment_transactions", ["actor_user_id"])

    op.create_table(
        "subscription_pauses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), sa.ForeignKey("student_subscriptions.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscription_pauses_organization_id", "subscription_pauses", ["organization_id"])
    op.create_index("ix_subscription_pauses_subscription_id", "subscription_pauses", ["subscription_id"])
    op.create_index("ix_subscription_pauses_student_id", "subscription_pauses", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_subscription_pauses_student_id", table_name="subscription_pauses")
    op.drop_index("ix_subscription_pauses_subscription_id", table_name="subscription_pauses")
    op.drop_index("ix_subscription_pauses_organization_id", table_name="subscription_pauses")
    op.drop_table("subscription_pauses")

    op.drop_index("ix_payment_transactions_actor_user_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_kind", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_student_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_payment_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_organization_id", table_name="payment_transactions")
    op.drop_table("payment_transactions")

    with op.batch_alter_table("student_subscriptions") as batch:
        batch.drop_index("ix_student_subscriptions_renewal_of_id")
        batch.drop_constraint("fk_student_subscriptions_renewal_of_id", type_="foreignkey")
        batch.drop_column("renewal_of_id")
        batch.drop_column("auto_renew")
