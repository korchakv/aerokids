"""lead follow-up reason and note

Revision ID: 0021_lead_followup_meta
Revises: 0020_tariff_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_lead_followup_meta"
down_revision = "0020_tariff_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.add_column(sa.Column("follow_up_reason", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("follow_up_note", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.drop_column("follow_up_note")
        batch.drop_column("follow_up_reason")
