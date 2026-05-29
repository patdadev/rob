# Deployment

The old split deploy workflows have been replaced by a single workflow: **Deploy Rob Codebase** in `.github/workflows/deploy-codebase.yml`.

## Deployment flow

1. GitHub runs codebase checks first (compile, ruff, pytest, deploy file sanity checks).
2. Bot server pre-check runs over SSH before any bot deploy.
3. Webhook server pre-check runs over SSH before any webhook deploy.
4. Bot deploy runs only if bot pre-check passes.
5. Webhook deploy runs only if webhook pre-check passes.

## Triggering

- Push to `main` deploys **dev** automatically.
- Manual `workflow_dispatch` can deploy `dev` or `prod`.
- `prod` should be protected using GitHub Environment approval rules.
- Bot and webhook can be deployed independently with workflow inputs.

## Safety and scope

Deployment does **not**:

- build DB schema automatically;
- run SQLite data migration automatically;
- use doadmin runtime credentials;
- overwrite `.env`;
- print secrets.

Deployment pre-check and deploy scripts validate DB readiness via `scripts/check_db.py`, but do not mutate schema.

## Manual DB build remains separate

If schema build/grants are required, run manually (admin action):

- `scripts/db/build/001_core_schema.sql`
- `scripts/db/build/002_indexes.sql`
- `scripts/db/build/003_achievements.sql`
- `scripts/db/build/004_sub_send_names.sql`
- `scripts/db/build/005_count_recovery.sql`
- `scripts/db/grants/*.sql`

SQLite data migration remains separate and is not part of deployment.

## Prod-role rehearsal target

For current rehearsals, both services run against `rob_dev_v2` with production-shaped runtime users:

- Bot server (`/opt/rob-bot/app/.env`): `DATABASE_URL=postgresql://prod_rob_bot:.../rob_dev_v2?...`
- Webhook server (`/opt/rob-webhook/app/.env`): `DATABASE_URL=postgresql://prod_rob_webhook:.../rob_dev_v2?...`
- Webhook base URL: `THRONE_WEBHOOK_BASE_URL=https://throne.robthebot.com`

If either service still points at an older database, `scripts/check_db.py` will fail because Rob v2 expects `db_build_version` and the new v2 schema tables.

## Infrastructure hostnames

- `bot-01.robthebot.com`
- `webhook-01.robthebot.com`
- `db-01.robthebot.com`

`db-01.robthebot.com` is a private/internal/admin-only reference by default. Do not expose PostgreSQL publicly unless protected by strict network controls.

The webhook service should stay on `127.0.0.1:8080` behind Cloudflared; do not expose port `8080` publicly.
