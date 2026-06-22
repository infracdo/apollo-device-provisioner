"""add pppoe_users table

Revision ID: f9a3b2c5d6e7
Revises: e382c921dc6f
Create Date: 2025-01-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'f9a3b2c5d6e7'
down_revision = 'e382c921dc6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create pppoe_users table
    op.create_table(
        'pppoe_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_name', sa.String(length=255), nullable=False),
        sa.Column('user_password', sa.String(length=255), nullable=False),
        sa.Column('nas_ip_address', sa.String(length=45), nullable=True),
        sa.Column('service_type', sa.String(length=50), nullable=False, server_default='Framed-User'),
        sa.Column('framed_protocol', sa.String(length=50), nullable=False, server_default='PPP'),
        sa.Column('framed_ip_address', sa.String(length=45), nullable=True),
        sa.Column('framed_ip_netmask', sa.String(length=45), nullable=True),
        sa.Column('framed_pool', sa.String(length=100), nullable=True),
        sa.Column('mikrotik_rate_limit', sa.String(length=100), nullable=False, server_default='5M/5M'),
        sa.Column('mikrotik_address_list', sa.String(length=100), nullable=True),
        sa.Column('mikrotik_group', sa.String(length=100), nullable=True),
        sa.Column('mikrotik_recv_limit_gigawords', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mikrotik_xmit_limit_gigawords', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('onu_serial_number', sa.String(length=100), nullable=True),
        sa.Column('onu_mac_address', sa.String(length=17), nullable=True),
        sa.Column('onu_olt_ip', sa.String(length=45), nullable=True),
        sa.Column('onu_olt_interface', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_pppoe_users_id', 'pppoe_users', ['id'], unique=False)
    op.create_index('ix_pppoe_users_user_name', 'pppoe_users', ['user_name'], unique=True)
    op.create_index('ix_pppoe_users_nas_ip_address', 'pppoe_users', ['nas_ip_address'], unique=False)
    op.create_index('ix_pppoe_users_mikrotik_address_list', 'pppoe_users', ['mikrotik_address_list'], unique=False)
    op.create_index('ix_pppoe_users_mikrotik_group', 'pppoe_users', ['mikrotik_group'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_pppoe_users_mikrotik_group', table_name='pppoe_users')
    op.drop_index('ix_pppoe_users_mikrotik_address_list', table_name='pppoe_users')
    op.drop_index('ix_pppoe_users_nas_ip_address', table_name='pppoe_users')
    op.drop_index('ix_pppoe_users_user_name', table_name='pppoe_users')
    op.drop_index('ix_pppoe_users_id', table_name='pppoe_users')
    
    # Drop table
    op.drop_table('pppoe_users')
