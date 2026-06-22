"""add_onu_secondary_serial_number_to_pppoe_users

Revision ID: a8ae09092e5c
Revises: 8daa98a468b5
Create Date: 2025-12-04 16:54:40.934283

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8ae09092e5c'
down_revision = '8daa98a468b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add onu_secondary_serial_number column to pppoe_users table
    op.add_column('pppoe_users', sa.Column('onu_secondary_serial_number', sa.String(length=100), nullable=True))


def downgrade() -> None:
    # Remove onu_secondary_serial_number column from pppoe_users table
    op.drop_column('pppoe_users', 'onu_secondary_serial_number')
