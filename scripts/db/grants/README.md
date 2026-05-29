# Runtime Grants

These SQL files are environment-specific runtime grants.

- `dev_rob_bot.sql` (legacy rehearsal role file, retained for compatibility)
- `dev_rehearsal_prod_roles.sql`
- `prod_rob_bot.sql`
- `prod_rob_webhook.sql`

Run manually as `doadmin`.

These are intentionally separate from required DB build versions.  
`scripts/check_db.py` validates runtime permissions from the active runtime user.

Current manual DB build order before applying grants:

1. `scripts/db/build/001_core_schema.sql`
2. `scripts/db/build/002_indexes.sql`
3. `scripts/db/build/003_achievements.sql`
4. `scripts/db/build/004_sub_send_names.sql`
5. `scripts/db/build/005_count_recovery.sql`
