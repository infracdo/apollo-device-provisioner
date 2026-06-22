"""add_onu_olt_deviceid_to_pppoe_users

Revision ID: b0cc1d38bc5b
Revises: e075bbf5c984
Create Date: 2025-11-20 17:53:00.016838

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b0cc1d38bc5b'
down_revision = 'e075bbf5c984'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add onu_olt_deviceid column to pppoe_users table
    op.add_column('pppoe_users', sa.Column('onu_olt_deviceid', sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Remove onu_olt_deviceid column from pppoe_users table
    op.drop_column('pppoe_users', 'onu_olt_deviceid')
