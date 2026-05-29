# Database Build (Manual SQL)

Rob v2 schema build is manual and admin-driven.

## Important terminology

- **DB build scripts**: SQL files that create/alter schema.
- **Data migration**: moving legacy SQLite data into PostgreSQL.
- **Rehearsal database**: `rob_dev_v2`, used to validate production-style runtime users before `rob_prod` is built or used.

Only SQLite -> PostgreSQL transfer should be called a migration.

## Run order for `rob_dev_v2` rehearsal

Execute as `doadmin` in pgAdmin4 or `psql`:

1. `scripts/db/build/001_core_schema.sql`
2. `scripts/db/build/002_indexes.sql`
3. `scripts/db/build/003_achievements.sql`
4. `scripts/db/grants/dev_rehearsal_prod_roles.sql`

The rehearsal grants intentionally use production-style runtime users against the rehearsal database:

- `rob_dev_v2` is the rehearsal database.
- `prod_rob_bot` is the bot runtime user.
- `prod_rob_webhook` is the webhook runtime user.
- Production runtime should later point to `rob_prod`, not `rob_dev_v2`.

Configure bot/webhook servers with `prod_rob_bot` and `prod_rob_webhook` credentials against `rob_dev_v2` for rehearsal, then run `scripts/check_db.py` once from each runtime credential.

## Webhook reinstall rehearsal

The webhook server can be reset/reinstalled and configured with:

```env
DATABASE_URL=postgresql://prod_rob_webhook:...@.../rob_dev_v2?sslmode=require
```

Then run:

```bash
PYTHONPATH=. python3 -m scripts.check_db
```

Expected outcome:

- `prod_rob_webhook` can connect to `rob_dev_v2`.
- `prod_rob_webhook` can insert `sends`.
- `prod_rob_webhook` can update `dommes` webhook status fields.
- `prod_rob_webhook` can insert achievement unlock/event rows for webhook-triggered achievements.
- `prod_rob_webhook` cannot create/alter/drop/truncate schema.
- `prod_rob_webhook` cannot delete from `sends`, `bot_users`, `user_achievements`, or `achievement_events`.

## Run order for `rob_prod`

Execute as `doadmin` in pgAdmin4 or `psql`:

1. `scripts/db/build/001_core_schema.sql`
2. `scripts/db/build/002_indexes.sql`
3. `scripts/db/build/003_achievements.sql`
4. `scripts/db/build/003_runtime_grants_template.sql` (optional reference template)

Then apply production runtime grants:

- Prod bot: `scripts/db/grants/prod_rob_bot.sql`
- Prod webhook: `scripts/db/grants/prod_rob_webhook.sql`

Required `db_build_version` rows are:

- `001_core_schema`
- `002_indexes`
- `003_achievements`

Runtime grants are environment-specific and are validated by `scripts/check_db.py` from runtime credentials.

## Target tables

- `db_build_version`
- `bot_settings`
- `bot_users`
- `dommes`
- `subs`
- `sends`
- `vib_settings`
- `vib_leaderboard`
- `the_count`
- `inactive_users`
- `user_achievements`
- `achievement_events`

## Runtime safety

Runtime users (`dev_rob_bot`, `prod_rob_bot`, `prod_rob_webhook`) must not receive:

- `CREATE`
- `ALTER`
- `DROP`
- `TRUNCATE`

The webhook runtime user (`prod_rob_webhook`) must also not receive `DELETE` on `sends`, `bot_users`, `user_achievements`, or `achievement_events`.

Use `scripts/check_db.py` from runtime credentials to validate permissions and table/column shape.
