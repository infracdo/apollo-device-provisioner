"""
Alembic Migration Script

Initialize database tables.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('manufacturer', sa.String(length=100), nullable=False),
        sa.Column('device_type', sa.Enum('olt', 'router', 'switch', name='devicetype'), nullable=False),
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=True),
        sa.Column('protocol', sa.Enum('ssh', 'telnet', 'api', 'snmp', name='connectionprotocol'), nullable=True),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('password', sa.Text(), nullable=False),
        sa.Column('enable_password', sa.Text(), nullable=True),
        sa.Column('api_token', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('verify_ssl', sa.Boolean(), nullable=True),
        sa.Column('timeout', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_devices_id'), 'devices', ['id'], unique=False)
    op.create_index(op.f('ix_devices_name'), 'devices', ['name'], unique=True)
    
    # Create onus table
    op.create_table(
        'onus',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('serial_no', sa.String(length=100), nullable=False),
        sa.Column('frame', sa.Integer(), nullable=True),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('ont_id', sa.Integer(), nullable=False),
        sa.Column('line_profile_id', sa.Integer(), nullable=True),
        sa.Column('service_profile_id', sa.Integer(), nullable=True),
        sa.Column('vlan', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('wan_mode', sa.String(length=20), nullable=True),
        sa.Column('upload_speed', sa.Integer(), nullable=True),
        sa.Column('download_speed', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('provisioned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_onus_id'), 'onus', ['id'], unique=False)
    op.create_index(op.f('ix_onus_serial_no'), 'onus', ['serial_no'], unique=True)
    
    # Create queues table
    op.create_table(
        'queues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('queue_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('target_ip', sa.String(length=100), nullable=False),
        sa.Column('upload_kbps', sa.Integer(), nullable=False),
        sa.Column('download_kbps', sa.Integer(), nullable=False),
        sa.Column('min_upload_kbps', sa.Integer(), nullable=True),
        sa.Column('min_download_kbps', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('parent_queue', sa.String(length=255), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_queues_id'), 'queues', ['id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_queues_id'), table_name='queues')
    op.drop_table('queues')
    op.drop_index(op.f('ix_onus_serial_no'), table_name='onus')
    op.drop_index(op.f('ix_onus_id'), table_name='onus')
    op.drop_table('onus')
    op.drop_index(op.f('ix_devices_name'), table_name='devices')
    op.drop_index(op.f('ix_devices_id'), table_name='devices')
    op.drop_table('devices')
