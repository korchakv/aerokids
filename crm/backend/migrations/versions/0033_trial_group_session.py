"""Allow trial lessons to be attached to a scheduled group session."""

from alembic import op
import sqlalchemy as sa


revision = "0033_trial_group_session"
down_revision = "0032_curriculum_learning"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("trial_lessons") as batch:
        batch.add_column(sa.Column("lesson_session_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_trial_lessons_lesson_session",
            "lesson_sessions",
            ["lesson_session_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_trial_lessons_lesson_session_id", ["lesson_session_id"])


def downgrade():
    with op.batch_alter_table("trial_lessons") as batch:
        batch.drop_index("ix_trial_lessons_lesson_session_id")
        batch.drop_constraint("fk_trial_lessons_lesson_session", type_="foreignkey")
        batch.drop_column("lesson_session_id")
