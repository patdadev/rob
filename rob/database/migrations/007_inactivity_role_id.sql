ALTER TABLE guild_settings
ADD COLUMN IF NOT EXISTS inactive_role_id BIGINT;
