-- Add is_overdue column to pppoe_users table
-- Migration: 20251107_add_is_overdue_to_pppoe_users
-- Purpose: Add overdue flag for payment management and captive portal redirect

-- Add the is_overdue column with default value false
ALTER TABLE pppoe_users 
ADD COLUMN IF NOT EXISTS is_overdue BOOLEAN DEFAULT FALSE;

-- Add index for faster queries
CREATE INDEX IF NOT EXISTS idx_pppoe_users_is_overdue 
ON pppoe_users(is_overdue);

-- Comment on column
COMMENT ON COLUMN pppoe_users.is_overdue IS 'Flag to indicate if user has overdue payments. When true, user will be redirected to captive portal via MikroTik group "overdue"';
