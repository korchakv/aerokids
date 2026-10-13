"""Persist potential group drafts."""
from alembic import op
import sqlalchemy as sa


revision = "0029_potential_group_proposals"
down_revision = "0028_lead_comment_kinds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "potential_group_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("members", sa.JSON(), nullable=False),
        sa.Column("slots", sa.JSON(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_potential_group_proposals_organization_id", "potential_group_proposals", ["organization_id"])
    op.create_index("ix_potential_group_proposals_created_by", "potential_group_proposals", ["created_by"])
    op.create_index("ix_potential_group_proposals_org_created", "potential_group_proposals", ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_table("potential_group_proposals")
