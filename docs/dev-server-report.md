# Dev Server Report

## 1. What Was Built

### Webhook server

- Added a standalone webhook runtime in `apps/webhook/main.py`.
- Added `GET /health` and `POST /throne/webhook/{creator_id}/{secret}` in `rob/throne/webhooks.py`.
- Added payload normalisation in `rob/throne/payloads.py`.
- Added webhook secret hashing/matching and optional signature verification helpers in `rob/throne/security.py`.
- Added maintenance-aware send recording through `rob/services/send_service.py`.
- Kept the webhook runtime independent from Discord settings so it can run without `DISCORD_TOKEN`.

### Bot server foundation

- Added a dedicated Discord runtime in `apps/bot/main.py` and `rob/discord/client.py`.
- Added cogs for `/register domme`, `/register sub`, `/sendrequest`, `/leaderboard`, `/add`, and `/count set`.
- Added a background send queue worker in `rob/services/send_queue_service.py`.
- Added leaderboard refresh and counting services.

### PostgreSQL usage

- Replaced runtime SQLite assumptions with PostgreSQL repository classes under `rob/database/repositories/`.
- Kept SQLite limited to the legacy import path in `rob/database/migrations/legacy/sqlite_to_postgres.py`.
- Public leaderboard queries now derive from posted sends only.
- Legacy imported sends are inserted as `posted`, and the bot queue only fetches `pending`, so those imported rows are not reposted.

### Deployment files

- Added split systemd units for webhook and bot dev services.
- Added first-time bootstrap scripts `deploy/scripts/install-webhook-dev.sh` and `deploy/scripts/install-bot-dev.sh`.
- Added `deploy/scripts/deploy-webhook-dev.sh`.
- Added `deploy/scripts/deploy-bot-dev.sh`.
- Added `scripts/robctl` and `scripts/ops.py` for backend operations.

### Workflows

- Added a checks workflow for push and pull request validation.
- Added manual deploy workflows for webhook dev and bot dev.

### Docs

- Added webhook server, bot server, deployment, maintenance, command, and backend control docs.
- Added this report as `docs/dev-server-report.md`.

### UI/card improvements

- Added reusable embed builders under `rob/ui/cards/`.
- Added dedicated cards for sends, leaderboards, registration, counting, maintenance, errors, and status.

### Cleanup and removal

- Moved the old single-process/event bot into `legacy/single-process-bot/`.
- Moved old event config and single-process install scripts into `legacy/`.
- Removed active runtime reliance on old `bot/` and event-era paths.

## 2. Branch Details

- Base branch used: `rebuild/rob-v2-foundation`
- Base branch tip incorporated during final recheck: `3bfba90`
- New branch name: `rebuild/dev-online-services`
- Commit summary:
  - split webhook and Discord runtimes
  - PostgreSQL repository/service layer
  - send queue worker and maintenance flow
  - bot commands and counting scaffold
  - deploy scripts, systemd units, GitHub workflows
  - docs, tests, and legacy archive cleanup

## 3. Server Setup Plan

### Webhook server

1. Create runtime user `rob`.
2. Either run `sudo DEPLOY_USER=deployuser bash deploy/scripts/install-webhook-dev.sh` or clone the repo branch into `/opt/rob-webhook/app` manually.
3. Create `/opt/rob-webhook/app/.env`.
   Webhook env does not need `DISCORD_TOKEN`.
4. Create `.venv`.
5. Install dependencies from `requirements.txt`.
6. Decide whether `THRONE_WEBHOOK_REQUIRE_SIGNATURE` should be `false` for early dev or `true` once Throne signature settings are verified.
7. Verify `PYTHONPATH=. python -m apps.webhook.main` starts with valid env and DB access.
8. Verify `curl http://127.0.0.1:8080/health` returns `OK`.
9. Install `deploy/systemd/rob-webhook-dev.service`.
10. Copy or symlink `deploy/scripts/deploy-webhook-dev.sh` to `/opt/rob-webhook/deploy-webhook-dev.sh`.
11. Add a sudoers entry for the deploy SSH user so it can restart `rob-webhook-dev.service` without a password prompt.
12. Configure the Cloudflare Tunnel from `https://rob-dev.barecoding.com` to `http://127.0.0.1:8080`.
13. Add GitHub deploy secrets.
14. Run the manual `Deploy Webhook Dev` workflow.

### Bot server

1. Create runtime user `rob`.
2. Either run `sudo DEPLOY_USER=deployuser bash deploy/scripts/install-bot-dev.sh` or clone the repo branch into `/opt/rob-bot/app` manually.
3. Create `/opt/rob-bot/app/.env`.
4. Create `.venv`.
5. Install dependencies from `requirements.txt`.
6. Verify `PYTHONPATH=. python -m apps.bot.main` starts with valid env and DB access.
7. Install `deploy/systemd/rob-bot-dev.service`.
8. Copy or symlink `deploy/scripts/deploy-bot-dev.sh` to `/opt/rob-bot/deploy-bot-dev.sh`.
9. Add a sudoers entry for the deploy SSH user so it can restart and inspect `rob-bot-dev.service` without a password prompt.
10. Add GitHub deploy secrets.
11. Run the manual `Deploy Bot Dev` workflow.

## 4. Required Environment Variables

### Webhook `.env`

- `APP_ENV`
- `LOG_LEVEL`
- `DATABASE_URL`
- `THRONE_WEBHOOK_HOST`
- `THRONE_WEBHOOK_PORT`
- `THRONE_WEBHOOK_BASE_URL`
- `THRONE_WEBHOOK_REQUIRE_SIGNATURE`
- `THRONE_PUBLIC_KEY_PEM`
- `THRONE_WEBHOOK_DEBUG_LOG_PAYLOAD`
- `THRONE_WEBHOOK_TIMESTAMP_HEADER`
- `THRONE_WEBHOOK_SIGNATURE_HEADER`
- `THRONE_WEBHOOK_SIGNED_MESSAGE_FORMAT`
- `THRONE_WEBHOOK_MAX_TIMESTAMP_SKEW_SECONDS`

Webhook env must not include `DISCORD_TOKEN`.
Use `THRONE_WEBHOOK_REQUIRE_SIGNATURE=false` for early dev if you do not yet have verified Throne signing details. Switch it to `true` once the public key and signature format are confirmed for the development webhook endpoint.

### Bot `.env`

- `APP_ENV`
- `LOG_LEVEL`
- `DATABASE_URL`
- `DISCORD_TOKEN`
- `BOT_NAME`

Bot env must include `DISCORD_TOKEN`.

## 5. Required GitHub Secrets

### `deploy-webhook-dev.yml`

- `WEBHOOK_DEV_HOST`
- `WEBHOOK_DEV_USER`
- `WEBHOOK_DEV_SSH_KEY`
- `WEBHOOK_DEV_PORT`

### `deploy-bot-dev.yml`

- `BOT_DEV_HOST`
- `BOT_DEV_USER`
- `BOT_DEV_SSH_KEY`
- `BOT_DEV_PORT`

## 6. Database Assumptions

- The database is `rob_dev`.
- PostgreSQL tables already exist through the migration foundation branch.
- Legacy data has already been imported or is importable with the legacy migration tooling.
- Bot/webhook app servers use runtime users such as `rob_dev_bot` and `rob_dev_webhook`.
- Migrations and schema ownership use `rob_dev_migrator`.

## 7. What Still Needs To Be Done Manually

- Provision the two DigitalOcean servers.
- Install Python and system packages.
- Create the `.env` files on both servers.
- Install the systemd unit files.
- Copy or symlink the deploy scripts into `/opt/rob-webhook/` and `/opt/rob-bot/`.
- Add sudoers entries for the SSH deploy users.
- Configure the Cloudflare Tunnel on the webhook server.
- Add the GitHub Actions deploy secrets.
- Run and verify the first manual deploy on both servers.

## 8. TODOs / Known Limitations

- Throne signature verification is implemented as an optional path, but live validation still depends on the correct production public key and exact signed-message format.
- The Discord command surface is intentionally minimal in this pass and does not include a broad admin suite.
- Leaderboard refresh is fully wired for posted sends and manual refresh requests, but richer multi-card/channel layouts can still be expanded.
- `robctl queue flush` releases queued maintenance sends back to `pending`; actual Discord posting still depends on the running bot worker.
- Send request approval/denial buttons from the old bot were not rebuilt yet.
- Production deployment and production-specific env separation are still to be done after the dev servers are proven out.
