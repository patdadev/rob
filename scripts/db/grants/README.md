# Runtime Grants

These SQL files are environment-specific runtime grants.

- `dev_rob_bot.sql`
- `prod_rob_bot.sql`
- `prod_rob_webhook.sql`
- `dev_rehearsal_prod_roles.sql` (optional rehearsal only)

Run manually as `doadmin`.

`dev_rehearsal_prod_roles.sql` grants production-style roles (`prod_rob_bot` and `prod_rob_webhook`) access to `rob_dev_v2` for controlled rehearsal only. This does not mean production runtime should normally point at the dev database; production runtime should later point to `rob_prod`.

These are intentionally separate from required DB build versions.  
`scripts/check_db.py` validates runtime permissions from the active runtime user.
