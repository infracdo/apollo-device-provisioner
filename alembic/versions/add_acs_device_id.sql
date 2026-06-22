-- Add acs_device_id column to pppoe_users table
-- Migration: add_acs_device_id
-- Date: 2025-11-04

-- Add the column
ALTER TABLE pppoe_users 
ADD COLUMN acs_device_id VARCHAR(255);

-- Create index for faster lookups
CREATE INDEX ix_pppoe_users_acs_device_id ON pppoe_users(acs_device_id);

-- Verify the change
-- SELECT column_name, data_type, character_maximum_length, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name = 'pppoe_users' AND column_name = 'acs_device_id';
