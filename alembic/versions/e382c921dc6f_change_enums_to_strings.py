"""change_enums_to_strings

Revision ID: e382c921dc6f
Revises: 001_initial
Create Date: 2025-10-21 10:37:04.751870

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e382c921dc6f'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change device_type from enum to varchar
    op.execute("ALTER TABLE devices ALTER COLUMN device_type TYPE varchar(50) USING device_type::text")
    
    # Change protocol from enum to varchar  
    op.execute("ALTER TABLE devices ALTER COLUMN protocol TYPE varchar(50) USING protocol::text")
    
    # Drop the old enum types
    op.execute("DROP TYPE IF EXISTS devicetype")
    op.execute("DROP TYPE IF EXISTS connectionprotocol")


def downgrade() -> None:
    # Recreate enum types
    op.execute("CREATE TYPE devicetype AS ENUM ('olt', 'router', 'switch')")
    op.execute("CREATE TYPE connectionprotocol AS ENUM ('ssh', 'telnet', 'api', 'snmp')")
    
    # Change columns back to enum
    op.execute("ALTER TABLE devices ALTER COLUMN device_type TYPE devicetype USING device_type::devicetype")
    op.execute("ALTER TABLE devices ALTER COLUMN protocol TYPE connectionprotocol USING protocol::connectionprotocol")
