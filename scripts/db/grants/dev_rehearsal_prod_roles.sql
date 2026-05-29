-- Rehearsal-only runtime grants for production-style roles on rob_dev_v2.
-- This is rehearsal-only.
-- Run manually as doadmin when validating prod credentials before prod cutover.
-- This does not mean production runtime should normally point at the dev database.

\connect rob_dev_v2

-- ---------------------------------------------------------------------------
-- prod_rob_bot on rob_dev_v2 (rehearsal only; mirrors bot runtime grants)
-- ---------------------------------------------------------------------------
GRANT CONNECT ON DATABASE rob_dev_v2 TO prod_rob_bot;
GRANT USAGE ON SCHEMA public TO prod_rob_bot;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public
TO prod_rob_bot;
GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA public
TO prod_rob_bot;

REVOKE CREATE ON SCHEMA public FROM prod_rob_bot;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO prod_rob_bot;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO prod_rob_bot;

-- ---------------------------------------------------------------------------
-- prod_rob_webhook on rob_dev_v2 (rehearsal only; mirrors webhook runtime grants)
-- ---------------------------------------------------------------------------
GRANT CONNECT ON DATABASE rob_dev_v2 TO prod_rob_webhook;
GRANT USAGE ON SCHEMA public TO prod_rob_webhook;

GRANT SELECT ON
  db_build_version,
  bot_settings,
  bot_users,
  dommes,
  subs,
  vib_settings,
  vib_leaderboard,
  user_achievements,
  achievement_events
TO prod_rob_webhook;

GRANT SELECT, INSERT, UPDATE ON
  sends,
  bot_users
TO prod_rob_webhook;

GRANT SELECT, INSERT ON
  user_achievements,
  achievement_events
TO prod_rob_webhook;

GRANT SELECT, UPDATE ON
  dommes,
  bot_settings
TO prod_rob_webhook;

GRANT USAGE, SELECT, UPDATE
ON SEQUENCE sends_id_seq
TO prod_rob_webhook;

GRANT USAGE, SELECT, UPDATE
ON SEQUENCE bot_users_id_seq
TO prod_rob_webhook;

GRANT USAGE, SELECT, UPDATE
ON SEQUENCE user_achievements_id_seq
TO prod_rob_webhook;

GRANT USAGE, SELECT, UPDATE
ON SEQUENCE achievement_events_id_seq
TO prod_rob_webhook;

REVOKE CREATE ON SCHEMA public FROM prod_rob_webhook;
REVOKE DELETE ON TABLE sends FROM prod_rob_webhook;
REVOKE DELETE ON TABLE bot_users FROM prod_rob_webhook;
REVOKE DELETE ON TABLE user_achievements FROM prod_rob_webhook;
REVOKE DELETE ON TABLE achievement_events FROM prod_rob_webhook;

-- Rehearsal roles must not receive CREATE, ALTER, DROP, or TRUNCATE grants.
