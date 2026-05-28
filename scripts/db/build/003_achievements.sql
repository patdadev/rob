-- Rob v2 achievements schema.
-- Run manually as doadmin in pgAdmin4/psql.

CREATE TABLE IF NOT EXISTS user_achievements (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    discord_user_id BIGINT NOT NULL,
    achievement_key TEXT NOT NULL,
    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (guild_id, discord_user_id, achievement_key)
);

CREATE TABLE IF NOT EXISTS achievement_events (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    discord_user_id BIGINT NOT NULL,
    achievement_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_achievements_guild_user
ON user_achievements (guild_id, discord_user_id);

CREATE INDEX IF NOT EXISTS idx_user_achievements_key
ON user_achievements (achievement_key);

CREATE INDEX IF NOT EXISTS idx_achievement_events_guild_user
ON achievement_events (guild_id, discord_user_id);

CREATE INDEX IF NOT EXISTS idx_achievement_events_key
ON achievement_events (achievement_key);

INSERT INTO db_build_version (version, notes)
VALUES ('003_achievements', 'Rob v2 achievements unlock state and event logging')
ON CONFLICT (version) DO NOTHING;

