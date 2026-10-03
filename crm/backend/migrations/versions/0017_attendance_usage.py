"""attendance usage and makeup ledger

Revision ID: 0017_attendance_usage
Revises: 0016_student_phone
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_attendance_usage"
down_revision = "0016_student_phone"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("subscription_plans") as batch:
        batch.add_column(sa.Column("usage_mode", sa.String(length=24), nullable=False, server_default="attendance"))
        batch.add_column(sa.Column("absent_rule", sa.String(length=24), nullable=False, server_default="choice"))
        batch.add_column(sa.Column("excused_rule", sa.String(length=24), nullable=False, server_default="makeup"))
        batch.add_column(sa.Column("late_rule", sa.String(length=24), nullable=False, server_default="consume"))
        batch.add_column(sa.Column("end_rule", sa.String(length=24), nullable=False, server_default="whichever_first"))
        batch.add_column(sa.Column("renewal_trigger", sa.String(length=24), nullable=False, server_default="last_lesson"))
        batch.add_column(sa.Column("allow_debt", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("max_lates", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("makeup_expiry_days", sa.Integer(), nullable=True))
    with op.batch_alter_table("student_subscriptions") as batch:
        batch.add_column(sa.Column("group_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_student_subscriptions_group", "groups", ["group_id"], ["id"])
        batch.create_index("ix_student_subscriptions_group_id", ["group_id"])
    op.create_table("subscription_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), sa.ForeignKey("student_subscriptions.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column("attendance_id", sa.Uuid(), sa.ForeignKey("attendance.id"), nullable=True),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "student_id", name="uq_subscription_usage_session_student"))
    for col in ["organization_id","subscription_id","student_id","session_id","attendance_id"]:
        op.create_index(f"ix_subscription_usage_{col}", "subscription_usage", [col])
    op.create_table("makeup_credits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("original_session_id", sa.Uuid(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column("target_session_id", sa.Uuid(), sa.ForeignKey("lesson_sessions.id"), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("original_session_id", "student_id", name="uq_makeup_original_student"))
    for col in ["organization_id","student_id","original_session_id","target_session_id"]:
        op.create_index(f"ix_makeup_credits_{col}", "makeup_credits", [col])

def downgrade() -> None:
    op.drop_table("makeup_credits")
    op.drop_table("subscription_usage")
    with op.batch_alter_table("student_subscriptions") as batch:
        batch.drop_index("ix_student_subscriptions_group_id")
        batch.drop_constraint("fk_student_subscriptions_group", type_="foreignkey")
        batch.drop_column("group_id")
    with op.batch_alter_table("subscription_plans") as batch:
        for name in ["makeup_expiry_days","max_lates","allow_debt","renewal_trigger","end_rule","late_rule","excused_rule","absent_rule","usage_mode"]:
            batch.drop_column(name)
