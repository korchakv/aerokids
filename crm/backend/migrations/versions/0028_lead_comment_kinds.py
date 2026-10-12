"""Tag lead history entries with the action that created them."""
from alembic import op
import sqlalchemy as sa


revision = "0028_lead_comment_kinds"
down_revision = "0027_lead_comment_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lead_comments",
        sa.Column("kind", sa.String(length=40), server_default="note", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("lead_comments", "kind")
