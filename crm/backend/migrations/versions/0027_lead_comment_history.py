from alembic import op
import sqlalchemy as sa
import uuid


revision = "0027_lead_comment_history"
down_revision = "0026_stage3_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_comments_organization_id", "lead_comments", ["organization_id"])
    op.create_index("ix_lead_comments_student_id", "lead_comments", ["student_id"])
    op.create_index("ix_lead_comments_author_user_id", "lead_comments", ["author_user_id"])
    op.create_index("ix_lead_comments_student_created", "lead_comments", ["student_id", "created_at"])

    # Preserve comments already stored on student records as the first history entry.
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, organization_id, notes, created_at FROM students WHERE notes IS NOT NULL AND length(trim(notes)) > 0"))
    for row in rows:
        connection.execute(
            sa.text("INSERT INTO lead_comments (id, organization_id, student_id, author_user_id, body, created_at, updated_at) VALUES (:id, :org, :student, NULL, :body, :created, :created)"),
            {
                "id": str(uuid.uuid4()),
                "org": str(row.organization_id),
                "student": str(row.id),
                "body": row.notes,
                "created": row.created_at,
            },
        )


def downgrade() -> None:
    op.drop_table("lead_comments")
