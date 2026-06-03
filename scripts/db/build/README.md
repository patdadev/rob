# Rob v2 DB Build Scripts

These are **manual DB build scripts** for Rob v2.

- Run them manually in pgAdmin4 or `psql` as `doadmin`.
- For production bootstrap, use `../manual/setup_rob_prod.sql`.
- For rehearsals, start with `rob_dev_v2` first.

Run in order:

1. `001_core_schema.sql`
2. `002_indexes.sql`
3. `004_sub_send_names.sql`
4. `005_count_recovery.sql`
5. `006_send_change_requests.sql`
6. `007_send_update_requests.sql`
7. `008_dm_preferences.sql`
8. `../grants/dev_rehearsal_prod_roles.sql`

`003_achievements.sql` is retired. `008_dm_preferences.sql` drops the
achievements tables/sequences if they still exist, removes the prior
`003_achievements` row from `db_build_version`, and installs the DM
notification preference columns and `domme_onboarding_state` table.

Important:

- Do not run prod grants against dev databases.
- Re-run the relevant grants file after adding new build files so runtime users can access new tables.
- Do not run manual cleanup scripts unless you are intentionally cleaning an old database.
- These are DB build scripts, not runtime migrations.
