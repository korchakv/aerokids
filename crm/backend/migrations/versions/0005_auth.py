"""user authentication fields

Revision ID: 0005_auth
Revises: 0004_staff
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_auth"
down_revision = "0004_staff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255)))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "password_hash")
