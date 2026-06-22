"""Add is_overdue column to pppoe_users

Revision ID: add_is_overdue
Revises: add_acs_device_id
Create Date: 2025-11-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_overdue'
down_revision = 'add_acs_device_id'
branch_labels = None
depends_on = None


def upgrade():
    """Add is_overdue column to pppoe_users table for captive portal redirect"""
    op.add_column(
        'pppoe_users',
        sa.Column('is_overdue', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_index(
        'ix_pppoe_users_is_overdue',
        'pppoe_users',
        ['is_overdue'],
        unique=False
    )


def downgrade():
    """Remove is_overdue column from pppoe_users table"""
    op.drop_index('ix_pppoe_users_is_overdue', table_name='pppoe_users')
    op.drop_column('pppoe_users', 'is_overdue')
