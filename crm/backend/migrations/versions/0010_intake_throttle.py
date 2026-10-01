"""public intake throttling

Revision ID: 0010_intake_throttle
Revises: 0009_student_availability
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_intake_throttle"
down_revision = "0009_student_availability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_intake_throttles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "scope", "fingerprint_hash", name="uq_public_intake_throttle"),
    )
    op.create_index("ix_public_intake_throttles_organization_id", "public_intake_throttles", ["organization_id"])


def downgrade() -> None:
    op.drop_table("public_intake_throttles")
