# Runtime Grants

These SQL files are environment-specific runtime grants.

- `dev_rob_bot.sql`
- `prod_rob_bot.sql`
- `prod_rob_webhook.sql`

Run manually as `doadmin`.

These are intentionally separate from required DB build versions.  
`scripts/check_db.py` validates runtime permissions from the active runtime user.
