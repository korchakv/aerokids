"""Store a student's school shift as a scheduling hint."""
from alembic import op
import sqlalchemy as sa


revision = "0030_student_school_shift"
down_revision = "0029_potential_group_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("students", sa.Column("school_shift", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("students", "school_shift")
