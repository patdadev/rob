# Runtime Grants

These SQL files are environment-specific runtime grants.

- `dev_rob_bot.sql` (legacy rehearsal role file, retained for compatibility)
- `dev_rehearsal_prod_roles.sql`
- `prod_rob_bot.sql`
- `prod_rob_webhook.sql`
- `dev_rehearsal_prod_roles.sql` (optional rehearsal only)

Run manually as `doadmin`.

`dev_rehearsal_prod_roles.sql` grants production-style roles (`prod_rob_bot` and `prod_rob_webhook`) access to `rob_dev_v2` for controlled rehearsal only. This does not mean production runtime should normally point at the dev database; production runtime should later point to `rob_prod`.

These are intentionally separate from required DB build versions.  
`scripts/check_db.py` validates runtime permissions from the active runtime user.

Current manual DB build order before applying grants:

1. `scripts/db/build/001_core_schema.sql`
2. `scripts/db/build/002_indexes.sql`
3. `scripts/db/build/004_sub_send_names.sql`
4. `scripts/db/build/005_count_recovery.sql`
5. `scripts/db/build/006_send_change_requests.sql`
6. `scripts/db/build/007_send_update_requests.sql`
7. `scripts/db/build/008_dm_preferences.sql`
8. `scripts/db/build/009_terms_acceptance.sql`
9. `scripts/db/build/010_age_verification.sql`

For one-shot production bootstrap, you can instead run:

- `scripts/db/manual/setup_rob_prod.sql`

That file creates `rob_prod`, creates the production runtime users, runs the build order above, and then applies `prod_rob_bot.sql` and `prod_rob_webhook.sql`.
