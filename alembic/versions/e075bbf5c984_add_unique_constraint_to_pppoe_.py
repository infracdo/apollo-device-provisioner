"""Add unique constraint to pppoe_accounting_requests

Revision ID: e075bbf5c984
Revises: 93be8f8d6ecf
Create Date: 2025-11-07 16:55:25.495146

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e075bbf5c984'
down_revision = '93be8f8d6ecf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unique constraint on acct_session_id and acct_status_type
    # This allows upsert operations: each session can have one Start, one Stop, multiple Alive records
    op.create_unique_constraint(
        'uq_pppoe_accounting_session_status',
        'pppoe_accounting_requests',
        ['acct_session_id', 'acct_status_type']
    )


def downgrade() -> None:
    # Remove the unique constraint
    op.drop_constraint(
        'uq_pppoe_accounting_session_status',
        'pppoe_accounting_requests',
        type_='unique'
    )
