# Rob v2 DB Build Scripts

These are **manual DB build scripts** for Rob v2.

- Run them manually in pgAdmin4 or `psql` as `doadmin`.
- Start with `rob_dev_v2` first.

Run in order for `rob_dev_v2` rehearsal:

1. `001_core_schema.sql`
2. `002_indexes.sql`
3. `003_achievements.sql`
4. `../grants/dev_rehearsal_prod_roles.sql`

Important:

- `rob_dev_v2` is the rehearsal database.
- `prod_rob_bot` is the bot runtime user for rehearsal and later production.
- `prod_rob_webhook` is the webhook runtime user for rehearsal and later production.
- Use `../grants/dev_rehearsal_prod_roles.sql` only when intentionally validating production-style runtime roles against `rob_dev_v2` before prod cutover.
- Production runtime should later point to `rob_prod`, not `rob_dev_v2`.
- Re-run the relevant grants file after adding `003_achievements.sql` so runtime users can access achievement tables.
- Do not run manual cleanup scripts unless you are intentionally cleaning an old database.
- These are DB build scripts, not runtime migrations.
