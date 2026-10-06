"""deferred lead follow-up

Revision ID: 0021_deferred_leads
Revises: 0020_tariff_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_deferred_leads"
down_revision = "0020_tariff_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.add_column(sa.Column("deferred_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("deferred_reason", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("deferred_note", sa.String(length=500), nullable=True))
        batch.create_index("ix_students_deferred_until", ["deferred_until"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.drop_index("ix_students_deferred_until")
        batch.drop_column("deferred_note")
        batch.drop_column("deferred_reason")
        batch.drop_column("deferred_until")
