# Rob v2 DB Build Scripts

These are **manual DB build scripts** for Rob v2.

- Run them manually in pgAdmin4 or `psql` as `doadmin`.
- Start with `rob_dev_v2` first.

Run in order:

1. `001_core_schema.sql`
2. `002_indexes.sql`
3. `003_achievements.sql`
4. `004_sub_send_names.sql`
5. `005_count_recovery.sql`
6. `../grants/dev_rehearsal_prod_roles.sql`

Important:

- Do not run prod grants against dev databases.
- Re-run the relevant grants file after adding new build files so runtime users can access new tables.
- Do not run manual cleanup scripts unless you are intentionally cleaning an old database.
- These are DB build scripts, not runtime migrations.
