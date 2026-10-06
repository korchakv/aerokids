"""staff teaching responsibility

Revision ID: 0019_staff_can_teach
Revises: 0018_auth_login_throttle
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_staff_can_teach"
down_revision = "0018_auth_login_throttle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("staff", sa.Column("can_teach", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("organization_invitations", sa.Column("can_teach", sa.Boolean(), nullable=False, server_default=sa.false()))

    # Preserve current AeroKids behaviour: existing owners/admins and teachers
    # may already teach. Future staff explicitly choose this responsibility.
    op.execute('UPDATE staff SET can_teach = TRUE WHERE role IN (\'OWNER\', \'ADMIN\', \'TEACHER\')')
    op.execute('UPDATE organization_invitations SET can_teach = TRUE WHERE role = \'TEACHER\'')

    op.alter_column("staff", "can_teach", server_default=None)
    op.alter_column("organization_invitations", "can_teach", server_default=None)


def downgrade() -> None:
    op.drop_column("organization_invitations", "can_teach")
    op.drop_column("staff", "can_teach")
