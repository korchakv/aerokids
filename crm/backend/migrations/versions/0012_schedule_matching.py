"""Add soft availability preferences and enrollment match notes.

Revision ID: 0012_schedule_matching
Revises: 0011_password_reset
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_schedule_matching"
down_revision = "0011_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A string enum is intentionally non-native so this remains portable to SQLite.
    preference = sa.Enum("PREFERRED", "POSSIBLE", "AVOID", name="availabilitypreference", native_enum=False)
    with op.batch_alter_table("student_availability") as batch:
        batch.add_column(sa.Column("preference", preference, nullable=False, server_default="PREFERRED"))
        batch.add_column(sa.Column("note", sa.String(length=300), nullable=True))
    with op.batch_alter_table("enrollments") as batch:
        batch.add_column(sa.Column("schedule_match", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("schedule_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("enrollments") as batch:
        batch.drop_column("schedule_note")
        batch.drop_column("schedule_match")
    with op.batch_alter_table("student_availability") as batch:
        batch.drop_column("note")
        batch.drop_column("preference")
