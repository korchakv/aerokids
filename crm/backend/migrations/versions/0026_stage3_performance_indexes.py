"""stage 3 pagination performance indexes

Revision ID: 0026_stage3_performance_indexes
Revises: 0025_subscription_rule_snapshots
"""
from alembic import op

revision = "0026_stage3_performance_indexes"
down_revision = "0025_subscription_rule_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_students_org_status_created",
        "students",
        ["organization_id", "student_status", "created_at"],
    )
    op.create_index(
        "ix_students_org_status_source",
        "students",
        ["organization_id", "student_status", "source"],
    )
    op.create_index(
        "ix_students_org_status_next_contact",
        "students",
        ["organization_id", "student_status", "next_contact_at"],
    )
    op.create_index(
        "ix_student_contacts_org_student_primary",
        "student_contacts",
        ["organization_id", "student_id", "is_primary"],
    )
    op.create_index(
        "ix_trial_lessons_org_student_start",
        "trial_lessons",
        ["organization_id", "student_id", "starts_at"],
    )
    op.create_index(
        "ix_payments_org_status_due_created",
        "payments",
        ["organization_id", "status", "due_date", "created_at"],
    )
    op.create_index(
        "ix_group_staff_org_group_primary",
        "group_staff",
        ["organization_id", "group_id", "is_primary"],
    )
    op.create_index(
        "ix_audit_events_org_created",
        "audit_events",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_audit_events_org_entity_created",
        "audit_events",
        ["organization_id", "entity_type", "entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_org_entity_created", table_name="audit_events")
    op.drop_index("ix_audit_events_org_created", table_name="audit_events")
    op.drop_index("ix_group_staff_org_group_primary", table_name="group_staff")
    op.drop_index("ix_payments_org_status_due_created", table_name="payments")
    op.drop_index("ix_trial_lessons_org_student_start", table_name="trial_lessons")
    op.drop_index("ix_student_contacts_org_student_primary", table_name="student_contacts")
    op.drop_index("ix_students_org_status_next_contact", table_name="students")
    op.drop_index("ix_students_org_status_source", table_name="students")
    op.drop_index("ix_students_org_status_created", table_name="students")
