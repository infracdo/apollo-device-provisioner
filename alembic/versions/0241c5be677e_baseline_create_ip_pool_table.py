"""baseline create ip_pool table

Revision ID: 0241c5be677e
Revises: 6f94455d0318
Create Date: 2026-07-10 11:53:18.995291

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, CIDR

# revision identifiers, used by Alembic.
revision = '0241c5be677e'
down_revision = 'b4bad40e219f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ip_pool',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mikrotik_id', sa.Integer(), nullable=False),
        sa.Column('start_ip', INET(), nullable=False),
        sa.Column('subnet', CIDR(), nullable=False),
        sa.Column('counter', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ip_pool_id'), 'ip_pool', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ip_pool_id'), table_name='ip_pool')
    op.drop_table('ip_pool')