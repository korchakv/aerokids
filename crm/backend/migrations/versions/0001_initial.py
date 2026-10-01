"""initial crm schema

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table("locations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("address", sa.String(300)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_location_org_name"),
    )
    op.create_index("ix_locations_organization_id", "locations", ["organization_id"])

    op.create_table("contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contacts_organization_id", "contacts", ["organization_id"])
    op.create_index("ix_contacts_phone", "contacts", ["phone"])

    op.create_table("students",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120)),
        sa.Column("birth_date", sa.Date()),
        sa.Column("age_at_inquiry", sa.Integer()),
        sa.Column("source", sa.String(80)),
        sa.Column("crm_status", sa.Enum("NEW","CONTACTED","TRIAL_SCHEDULED","TRIAL_COMPLETED","WAITING_FOR_GROUP","ENROLLED","NO_RESPONSE","DECLINED","NOT_RELEVANT", name="crmstatus"), nullable=False),
        sa.Column("student_status", sa.Enum("PROSPECT","ACTIVE","PAUSED","ARCHIVED", name="studentstatus"), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_students_organization_id", "students", ["organization_id"])

    op.create_table("student_contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("relation", sa.String(60)),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("student_id", "contact_id", name="uq_student_contact"),
    )
    op.create_index("ix_student_contacts_organization_id", "student_contacts", ["organization_id"])
    op.create_index("ix_student_contacts_student_id", "student_contacts", ["student_id"])
    op.create_index("ix_student_contacts_contact_id", "student_contacts", ["contact_id"])

    op.create_table("trial_lessons",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("locations.id")),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Enum("SCHEDULED","COMPLETED","NO_SHOW","CANCELLED", name="trialstatus"), nullable=False),
        sa.Column("recommended_level", sa.String(80)),
        sa.Column("teacher_notes", sa.Text()),
    )
    op.create_index("ix_trial_lessons_organization_id", "trial_lessons", ["organization_id"])
    op.create_index("ix_trial_lessons_location_id", "trial_lessons", ["location_id"])
    op.create_index("ix_trial_lessons_student_id", "trial_lessons", ["student_id"])

    op.create_table("groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("locations.id")),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("capacity", sa.Integer()),
        sa.Column("min_age", sa.Integer()),
        sa.Column("max_age", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_group_org_name"),
    )
    op.create_index("ix_groups_organization_id", "groups", ["organization_id"])
    op.create_index("ix_groups_location_id", "groups", ["location_id"])

    op.create_table("enrollments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE","PAUSED","FINISHED", name="enrollmentstatus"), nullable=False),
        sa.Column("started_at", sa.Date(), nullable=False),
        sa.Column("ended_at", sa.Date()),
        sa.UniqueConstraint("student_id", "group_id", name="uq_student_group_enrollment"),
    )
    op.create_index("ix_enrollments_organization_id", "enrollments", ["organization_id"])
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.create_index("ix_enrollments_group_id", "enrollments", ["group_id"])


def downgrade() -> None:
    op.drop_table("enrollments")
    op.drop_table("groups")
    op.drop_table("trial_lessons")
    op.drop_table("student_contacts")
    op.drop_table("students")
    op.drop_table("contacts")
    op.drop_table("locations")
    op.drop_table("organizations")
