"""optional student phone

Revision ID: 0016_student_phone
Revises: 0015_billing_ledger
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_student_phone"
down_revision = "0015_billing_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.add_column(sa.Column("phone", sa.String(length=40), nullable=True))
        batch.create_index("ix_students_phone", ["phone"])


def downgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.drop_index("ix_students_phone")
        batch.drop_column("phone")
