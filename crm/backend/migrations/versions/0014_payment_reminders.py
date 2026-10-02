"""payment reminders

Revision ID: 0014_payment_reminders
Revises: 0013_lead_followup
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_payment_reminders"
down_revision = "0013_lead_followup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", "stage", name="uq_payment_reminder_stage"),
    )
    op.create_index("ix_payment_reminders_organization_id", "payment_reminders", ["organization_id"])
    op.create_index("ix_payment_reminders_payment_id", "payment_reminders", ["payment_id"])
    op.create_index("ix_payment_reminders_student_id", "payment_reminders", ["student_id"])
    op.create_index("ix_payment_reminders_created_by_user_id", "payment_reminders", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_reminders_created_by_user_id", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_student_id", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_payment_id", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_organization_id", table_name="payment_reminders")
    op.drop_table("payment_reminders")
