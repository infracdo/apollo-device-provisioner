"""change_onu_olt_deviceid_to_integer

Revision ID: 8daa98a468b5
Revises: b0cc1d38bc5b
Create Date: 2025-11-20 18:19:23.065247

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8daa98a468b5'
down_revision = 'b0cc1d38bc5b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Change onu_olt_deviceid from VARCHAR to INTEGER"""
    # For PostgreSQL, we need to explicitly cast the column
    # First, update any non-numeric values to NULL
    op.execute("""
        UPDATE pppoe_users 
        SET onu_olt_deviceid = NULL 
        WHERE onu_olt_deviceid IS NOT NULL 
        AND onu_olt_deviceid !~ '^[0-9]+$'
    """)
    
    # Now alter the column type with explicit casting
    op.execute("""
        ALTER TABLE pppoe_users 
        ALTER COLUMN onu_olt_deviceid 
        TYPE INTEGER 
        USING CASE 
            WHEN onu_olt_deviceid ~ '^[0-9]+$' THEN onu_olt_deviceid::INTEGER 
            ELSE NULL 
        END
    """)


def downgrade() -> None:
    """Change onu_olt_deviceid back to VARCHAR"""
    op.alter_column('pppoe_users', 'onu_olt_deviceid',
                    type_=sa.String(255),
                    existing_nullable=True)
