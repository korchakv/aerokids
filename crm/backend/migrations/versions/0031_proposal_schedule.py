"""Separate proposed alternatives from the selected family schedule."""
from alembic import op
import sqlalchemy as sa
revision = "0031_proposal_schedule"
down_revision = "0030_student_school_shift"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("group_schedules", sa.Column("starts_on", sa.Date(), nullable=True))
    op.add_column("potential_group_proposals", sa.Column("selected_slots", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("potential_group_proposals", sa.Column("schedule_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("potential_group_proposals", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("potential_group_proposals") as batch:
        batch.add_column(sa.Column("formed_group_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_proposal_formed_group", "groups", ["formed_group_id"], ["id"])

def downgrade():
    op.drop_column("group_schedules", "starts_on")
    with op.batch_alter_table("potential_group_proposals") as batch:
        batch.drop_constraint("fk_proposal_formed_group", type_="foreignkey")
        batch.drop_column("formed_group_id")
    for name in ("version", "schedule_history", "selected_slots"):
        op.drop_column("potential_group_proposals", name)
