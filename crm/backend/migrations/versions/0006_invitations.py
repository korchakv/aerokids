"""organization invitations

Revision ID: 0006_invitations
Revises: 0005_auth
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_invitations"
down_revision = "0005_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("OWNER","ADMIN","MANAGER","TEACHER","ACCOUNTANT", name="staffrole", create_type=False), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_org_invites_organization_id", "organization_invitations", ["organization_id"])
    op.create_index("ix_org_invites_email", "organization_invitations", ["email"])
    op.create_index("ix_org_invites_token_hash", "organization_invitations", ["token_hash"])
    op.create_index("ix_org_invites_invited_by", "organization_invitations", ["invited_by_user_id"])


def downgrade() -> None:
    op.drop_table("organization_invitations")
