CREATE TABLE IF NOT EXISTS age_verifications (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    discord_user_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'yoti',
    age_threshold INTEGER NOT NULL DEFAULT 18,
    yoti_session_id TEXT,
    yoti_reference_id TEXT,
    yoti_method TEXT,
    yoti_result_summary TEXT,
    manual_review_reason TEXT,
    reviewed_by_user_id BIGINT,
    verified_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (guild_id, discord_user_id)
);

CREATE INDEX IF NOT EXISTS idx_age_verifications_guild_user
    ON age_verifications (guild_id, discord_user_id);

CREATE INDEX IF NOT EXISTS idx_age_verifications_yoti_session_id
    ON age_verifications (yoti_session_id);

CREATE INDEX IF NOT EXISTS idx_age_verifications_status
    ON age_verifications (status);

INSERT INTO db_build_version (version, notes)
VALUES (
    '010_age_verification',
    'Test-guild-only Yoti age verification session tracking'
)
ON CONFLICT (version) DO NOTHING;
