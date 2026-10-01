"""student preferences and availability

Revision ID: 0009_student_availability
Revises: 0008_org_settings
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_student_availability"
down_revision = "0008_org_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("students") as batch_op:
        batch_op.add_column(sa.Column("preferred_location_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_students_preferred_location_id_locations",
            "locations",
            ["preferred_location_id"],
            ["id"],
        )
        batch_op.create_index("ix_students_preferred_location_id", ["preferred_location_id"])

    op.create_table(
        "student_availability",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.UniqueConstraint("student_id", "weekday", "start_time", "end_time", name="uq_student_availability_slot"),
    )
    op.create_index("ix_student_availability_organization_id", "student_availability", ["organization_id"])
    op.create_index("ix_student_availability_student_id", "student_availability", ["student_id"])


def downgrade() -> None:
    op.drop_table("student_availability")
    with op.batch_alter_table("students") as batch_op:
        batch_op.drop_index("ix_students_preferred_location_id")
        batch_op.drop_constraint("fk_students_preferred_location_id_locations", type_="foreignkey")
        batch_op.drop_column("preferred_location_id")
