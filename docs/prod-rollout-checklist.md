# Production Rollout Checklist (Rob v2 Rebuild)

## 0) Prod-role rehearsal on `rob_dev_v2`

Before creating or using `rob_prod`, validate production-style runtime credentials against the rehearsal database:

1. Build the `rob_dev_v2` schema manually:
   - `scripts/db/build/001_core_schema.sql`
   - `scripts/db/build/002_indexes.sql`
   - `scripts/db/build/003_achievements.sql`
2. Apply `scripts/db/grants/dev_rehearsal_prod_roles.sql` as `doadmin`.
3. Configure bot/webhook servers to use:
   - `prod_rob_bot` against `rob_dev_v2` for bot rehearsal.
   - `prod_rob_webhook` against `rob_dev_v2` for webhook rehearsal.
4. Run `PYTHONPATH=. python3 -m scripts.check_db` once with each runtime credential.

`rob_dev_v2` is the rehearsal database. `prod_rob_bot` is the bot runtime user. `prod_rob_webhook` is the webhook runtime user. Production runtime should later point to `rob_prod`, not `rob_dev_v2`.

### Webhook reinstall readiness

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

## 1) Build production schema manually as `doadmin`

Run in order, against `rob_prod`:

1. `scripts/db/build/001_core_schema.sql`
2. `scripts/db/build/002_indexes.sql`
3. `scripts/db/build/003_achievements.sql`
4. `scripts/db/build/003_runtime_grants_template.sql` (optional reference template)
5. `scripts/db/grants/prod_rob_bot.sql`
6. `scripts/db/grants/prod_rob_webhook.sql`

These are DB build scripts, not app migrations.

## 2) Confirm runtime users

- `prod_rob_bot` connects and has runtime table/sequence access.
- `prod_rob_webhook` connects with narrower runtime grants.
- Neither runtime user has schema `CREATE`.
- `prod_rob_webhook` cannot delete from `sends`, `bot_users`, `user_achievements`, or `achievement_events`.

## 3) Seed minimum configuration

Insert only required production rows:

- `vib_settings` for production guild(s)
- optional `bot_settings` defaults (maintenance/features/inactivity)

Do not copy dev send history by default.

## 4) Configure runtime environment

Bot:
- `DATABASE_URL=postgresql://prod_rob_bot:.../rob_prod?...`

Webhook:
- `DATABASE_URL=postgresql://prod_rob_webhook:.../rob_prod?...`

No admin DB credential is required in runtime `.env`.

## 5) Validate DB with runtime credentials

Run:

```bash
PYTHONPATH=. python3 -m scripts.check_db
```

If this fails, apply missing DB build SQL manually and rerun.

## 6) Deploy webhook and bot services

Deploy scripts intentionally run:

1. dependency install
2. compile checks
3. `scripts.check_db`
4. service restart

Deploy scripts do **not** create/alter schema.

## 7) Functional validation

1. registration works (`/register domme`, `/register sub`)
2. webhook ingest works on preferred route
3. send queue posts and marks sends
4. leaderboard refresh works
5. `/leaderboard` and counting features behave normally
6. inactivity loop behaves as expected

## 8) Post-cutover audit

- runtime logs show no DB permission errors
- webhook user is still missing schema `CREATE`
- webhook user cannot delete from `sends`, `bot_users`, `user_achievements`, or `achievement_events`
- `db_build_version` includes:
  - `001_core_schema`
  - `002_indexes`
  - `003_achievements`
