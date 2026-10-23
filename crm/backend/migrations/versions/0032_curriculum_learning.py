"""Add curriculum lessons, materials, and student learning progress."""

from alembic import op
import sqlalchemy as sa


revision = "0032_curriculum_learning"
down_revision = "0031_proposal_schedule"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("groups", sa.Column("curriculum_completed_through", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("groups", sa.Column("curriculum_baseline_date", sa.Date(), nullable=True))
    op.create_table(
        "curriculum_lessons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("outline", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "position", name="uq_curriculum_lesson_org_position"),
    )
    op.create_index("ix_curriculum_lessons_organization_id", "curriculum_lessons", ["organization_id"])
    op.add_column("lesson_sessions", sa.Column("curriculum_lesson_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("lesson_sessions") as batch:
        batch.create_foreign_key("fk_lesson_sessions_curriculum_lesson", "curriculum_lessons", ["curriculum_lesson_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_lesson_sessions_curriculum_lesson_id", ["curriculum_lesson_id"])
    op.create_table(
        "curriculum_materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=160), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("file_data", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["lesson_id"], ["curriculum_lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_curriculum_materials_organization_id", "curriculum_materials", ["organization_id"])
    op.create_index("ix_curriculum_materials_lesson_id", "curriculum_materials", ["lesson_id"])
    op.create_table(
        "student_lesson_completions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_id"], ["curriculum_lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "student_id", "lesson_id", name="uq_student_lesson_completion"),
    )
    op.create_index("ix_student_lesson_completions_organization_id", "student_lesson_completions", ["organization_id"])
    op.create_index("ix_student_lesson_completions_student_id", "student_lesson_completions", ["student_id"])
    op.create_index("ix_student_lesson_completions_lesson_id", "student_lesson_completions", ["lesson_id"])


def downgrade():
    op.drop_table("student_lesson_completions")
    op.drop_table("curriculum_materials")
    with op.batch_alter_table("lesson_sessions") as batch:
        batch.drop_index("ix_lesson_sessions_curriculum_lesson_id")
        batch.drop_constraint("fk_lesson_sessions_curriculum_lesson", type_="foreignkey")
        batch.drop_column("curriculum_lesson_id")
    op.drop_table("curriculum_lessons")
    op.drop_column("groups", "curriculum_baseline_date")
    op.drop_column("groups", "curriculum_completed_through")
