"""Add acs_device_id to pppoe_users

Revision ID: add_acs_device_id
Revises: f9a3b2c5d6e7
Create Date: 2025-11-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_acs_device_id'
down_revision = 'f9a3b2c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    """Add acs_device_id column to pppoe_users table"""
    op.add_column(
        'pppoe_users',
        sa.Column('acs_device_id', sa.String(length=255), nullable=True)
    )
    op.create_index(
        'ix_pppoe_users_acs_device_id',
        'pppoe_users',
        ['acs_device_id'],
        unique=False
    )


def downgrade():
    """Remove acs_device_id column from pppoe_users table"""
    op.drop_index('ix_pppoe_users_acs_device_id', table_name='pppoe_users')
    op.drop_column('pppoe_users', 'acs_device_id')
