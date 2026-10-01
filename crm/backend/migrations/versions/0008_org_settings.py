"""organization settings

Revision ID: 0008_org_settings
Revises: 0007_audit
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_org_settings"
down_revision = "0007_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Kyiv"))
    op.add_column("organizations", sa.Column("currency", sa.String(length=3), nullable=False, server_default="UAH"))
    op.add_column("organizations", sa.Column("locale", sa.String(length=20), nullable=False, server_default="uk-UA"))


def downgrade() -> None:
    op.drop_column("organizations", "locale")
    op.drop_column("organizations", "currency")
    op.drop_column("organizations", "timezone")
