"""lead follow-up and close reason

Revision ID: 0013_lead_followup
Revises: 0012_schedule_matching
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_lead_followup"
down_revision = "0012_schedule_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("students", sa.Column("next_contact_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("students", sa.Column("lead_close_reason", sa.String(length=80), nullable=True))
    op.add_column("students", sa.Column("lead_close_note", sa.String(length=500), nullable=True))
    op.create_index("ix_students_next_contact_at", "students", ["next_contact_at"])


def downgrade() -> None:
    op.drop_index("ix_students_next_contact_at", table_name="students")
    op.drop_column("students", "lead_close_note")
    op.drop_column("students", "lead_close_reason")
    op.drop_column("students", "next_contact_at")
