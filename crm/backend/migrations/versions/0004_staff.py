"""staff memberships and assignments

Revision ID: 0004_staff
Revises: 0003_payments
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_staff"
down_revision = "0003_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(160)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.Enum("OWNER","ADMIN","MANAGER","TEACHER","ACCOUNTANT", name="staffrole"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])

    op.create_table(
        "staff",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(40)),
        sa.Column("role", sa.Enum("OWNER","ADMIN","MANAGER","TEACHER","ACCOUNTANT", name="staffrole", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "email", name="uq_staff_org_email"),
    )
    op.create_index("ix_staff_organization_id", "staff", ["organization_id"])
    op.create_index("ix_staff_user_id", "staff", ["user_id"])

    op.create_table(
        "staff_locations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("staff_id", sa.Uuid(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("locations.id"), nullable=False),
        sa.UniqueConstraint("staff_id", "location_id", name="uq_staff_location"),
    )
    op.create_index("ix_staff_locations_organization_id", "staff_locations", ["organization_id"])
    op.create_index("ix_staff_locations_staff_id", "staff_locations", ["staff_id"])
    op.create_index("ix_staff_locations_location_id", "staff_locations", ["location_id"])

    op.create_table(
        "group_staff",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("staff_id", sa.Uuid(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("group_id", "staff_id", name="uq_group_staff"),
    )
    op.create_index("ix_group_staff_organization_id", "group_staff", ["organization_id"])
    op.create_index("ix_group_staff_group_id", "group_staff", ["group_id"])
    op.create_index("ix_group_staff_staff_id", "group_staff", ["staff_id"])


def downgrade() -> None:
    op.drop_table("group_staff")
    op.drop_table("staff_locations")
    op.drop_table("staff")
    op.drop_table("organization_memberships")
    op.drop_table("users")
