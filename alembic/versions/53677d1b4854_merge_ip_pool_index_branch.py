"""merge ip_pool index branch

Revision ID: 53677d1b4854
Revises: 6f94455d0318, 0aff9f6c9542
Create Date: 2026-07-27 17:28:02.170594

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '53677d1b4854'
down_revision = ('6f94455d0318', '0aff9f6c9542')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
