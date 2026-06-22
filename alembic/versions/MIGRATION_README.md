# Database Migration: Add acs_device_id to pppoe_users

## Overview
Adds the `acs_device_id` field to the `pppoe_users` table to store GenieACS device identifiers.

## Field Details
- **Column Name**: `acs_device_id`
- **Type**: VARCHAR(255)
- **Nullable**: Yes
- **Indexed**: Yes
- **Purpose**: Store GenieACS device ID (e.g., "E007C2-MH80-MHAR08DF4BD9")

## Migration Methods

### Method 1: Using Alembic (Recommended)
```bash
cd /home/mcandres/sandbox/APOLLO/apollo-device-provisioner
alembic upgrade head
```

### Method 2: Manual SQL Execution
```bash
psql -U your_username -d your_database -f alembic/versions/add_acs_device_id.sql
```

Or using psql interactive:
```sql
\i alembic/versions/add_acs_device_id.sql
```

### Method 3: Direct SQL (if database is running)
```sql
ALTER TABLE pppoe_users ADD COLUMN acs_device_id VARCHAR(255);
CREATE INDEX ix_pppoe_users_acs_device_id ON pppoe_users(acs_device_id);
```

## API Changes

### GET /api/v1/pppoe/users/by-username/{username}
Now returns `acs_device_id` in the response:
```json
{
  "id": 7,
  "user_name": "MYB-779",
  "acs_device_id": "E007C2-MH80-MHAR08DF4BD9",
  ...
}
```

### PATCH /api/v1/pppoe/users/{username}/onu
Now accepts `acs_device_id` in the request body:
```json
{
  "onu_serial_number": "MHAR08F6C2D9",
  "onu_mac_address": "00:11:22:33:44:55",
  "onu_olt_ip": "10.42.1.1",
  "onu_olt_interface": "gpon-onu_1/1/2:1",
  "acs_device_id": "E007C2-MH80-MHAR08DF4BD9"
}
```

## Usage Example

Update ACS device ID for a user:
```bash
curl -X PATCH http://localhost:8000/api/v1/pppoe/users/MYB-779/onu \
  -H "Content-Type: application/json" \
  -d '{
    "acs_device_id": "E007C2-MH80-MHAR08DF4BD9"
  }'
```

Retrieve user with ACS device ID:
```bash
curl http://localhost:8000/api/v1/pppoe/users/by-username/MYB-779
```

## Rollback

To remove the column:
```sql
DROP INDEX IF EXISTS ix_pppoe_users_acs_device_id;
ALTER TABLE pppoe_users DROP COLUMN acs_device_id;
```

Or with Alembic:
```bash
alembic downgrade -1
```

## Verification

Check if migration was successful:
```sql
SELECT column_name, data_type, character_maximum_length, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'pppoe_users' AND column_name = 'acs_device_id';
```

Expected result:
```
 column_name   | data_type | character_maximum_length | is_nullable 
---------------+-----------+-------------------------+-------------
 acs_device_id | varchar   |                     255 | YES
```
