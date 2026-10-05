"""persistent authentication login throttling

Revision ID: 0018_auth_login_throttle
Revises: 0017_attendance_usage
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_auth_login_throttle"
down_revision = "0017_attendance_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_login_throttles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "fingerprint_hash", name="uq_auth_login_throttle"),
    )
    op.create_index("ix_auth_login_throttles_scope", "auth_login_throttles", ["scope"])


def downgrade() -> None:
    op.drop_table("auth_login_throttles")
