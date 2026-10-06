"""tariff lifecycle snapshots and credit

Revision ID: 0020_tariff_lifecycle
Revises: 0019_staff_can_teach
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_tariff_lifecycle"
down_revision = "0019_staff_can_teach"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subscription_plans") as batch:
        batch.alter_column("period_days", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("student_subscriptions") as batch:
        batch.alter_column("ends_on", existing_type=sa.Date(), nullable=True)
        batch.add_column(sa.Column("period_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("lessons_included", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("credit_minor", sa.Integer(), nullable=False, server_default="0"))

    # Freeze the plan rules that were in effect when each existing subscription
    # was created so future tariff edits do not rewrite historical periods.
    op.execute(
        """
        UPDATE student_subscriptions
        SET period_days = (
            SELECT subscription_plans.period_days
            FROM subscription_plans
            WHERE subscription_plans.id = student_subscriptions.plan_id
        ),
        lessons_included = (
            SELECT subscription_plans.lessons_included
            FROM subscription_plans
            WHERE subscription_plans.id = student_subscriptions.plan_id
        )
        """
    )


def downgrade() -> None:
    # Restore a concrete 30-day period before making the legacy columns required.
    op.execute("UPDATE subscription_plans SET period_days = 30 WHERE period_days IS NULL")
    op.execute(
        """
        UPDATE student_subscriptions
        SET ends_on = starts_on + 29
        WHERE ends_on IS NULL
        """
    )
    with op.batch_alter_table("student_subscriptions") as batch:
        batch.drop_column("credit_minor")
        batch.drop_column("lessons_included")
        batch.drop_column("period_days")
        batch.alter_column("ends_on", existing_type=sa.Date(), nullable=False)

    with op.batch_alter_table("subscription_plans") as batch:
        batch.alter_column("period_days", existing_type=sa.Integer(), nullable=False)
