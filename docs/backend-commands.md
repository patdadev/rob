# Backend Commands

Use `scripts/rob` (or install the global wrapper) for operations.

## Install global command

```bash
scripts/install-rob-global.sh
```

## Core command groups

```bash
rob status
rob logs bot
rob logs webhook
rob restart bot
rob restart webhook

rob maintenance status
rob maintenance on "reason"
rob maintenance off

rob queue status
rob queue flush

rob leaderboard refresh
rob leaderboard status --guild-id <guild_id>
rob leaderboard preview --guild-id <guild_id>
rob leaderboard diagnose --guild-id <guild_id>
rob leaderboard repair-send-dommes --guild-id <guild_id> --dry-run
rob leaderboard repair-send-dommes --guild-id <guild_id>

rob throne status --guild-id <guild_id>
rob throne dommes --guild-id <guild_id>
rob throne subs --guild-id <guild_id>
rob throne invalidate-test-sends

rob sends list --status all --guild-id <guild_id> --limit 25
rob sends backfill-public-ids
rob sends mark-posted <send_id>

rob guild scan --guild-id <guild_id>
rob guild set-channel --guild-id <guild_id> --field leaderboard_channel_id --channel-id <channel_id>
rob guild set-role --guild-id <guild_id> --field domme_role_id --role-id <role_id>

rob count status
rob count set <number>

rob inactivity status --guild-id <guild_id>
rob inactivity on --guild-id <guild_id>
rob inactivity off --guild-id <guild_id>
```

## DB build vs data migration

- DB schema build is manual SQL in `scripts/db/build/` (run as `doadmin`).
- Runtime grants are environment-specific SQL in `scripts/db/grants/`.
- SQLite -> PostgreSQL data migration tooling is in `scripts/data_migration/`.
- Deploy scripts do not run schema build SQL.

## Deploy gate

Deploy scripts run `scripts/check_db.py` and stop on failure with:

> Database check failed.  
> This database has not been built for Rob v2 yet, or runtime grants are incomplete.  
> Run `001_core_schema.sql`, `002_indexes.sql`, and the correct runtime grants SQL, then rerun deploy.
