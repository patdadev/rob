# Rob Web Portal (Django Superadmin)

## Overview

Rob now includes a separate Django-based superadmin portal under `portal/`.

- Framework: Django + Django Admin
- Auth: Discord OAuth (`identify`, `guilds`)
- Data store: PostgreSQL (existing Rob tables mapped as unmanaged models)
- Access: superadmin allowlist only (`ROB_PORTAL_SUPERADMIN_USER_IDS`)

This portal is intentionally separate from the Discord bot and webhook services.

## What PR #32 Adds

The portal rollout in PR #32 introduces:

- Django portal app under `portal/`
- Discord OAuth superadmin login
- Django Admin mappings for Rob DB tables
- custom pages for dashboard/services/logs/database/leaderboards/sends/settings
- private bot-ops bridge integration
- safe allowlisted log reader with redaction
- migration `010_portal_audit_log` for portal action auditing
- deploy script and systemd service template for the portal service

## Why Django Admin

Django Admin provides a secure, mature baseline for:

- authenticated admin sessions
- model browsing and filtering
- safe CRUD controls
- admin actions for constrained workflows

This avoids rebuilding every internal page by hand while still allowing custom Rob pages for operations.

## URL Layout

All portal routes are prefixed with `/portal/`:

- `/portal/`
- `/portal/login/`
- `/portal/logout/`
- `/portal/auth/discord/`
- `/portal/auth/discord/callback/`
- `/portal/admin/`
- `/portal/dashboard/`
- `/portal/services/`
- `/portal/logs/`
- `/portal/database/`
- `/portal/leaderboards/`
- `/portal/sends/`
- `/portal/settings/`

## Environment Variables

Add these to `.env` for portal runtime:

```dotenv
ROB_PORTAL_ENABLED=false
ROB_PORTAL_ENV=dev
ROB_PORTAL_BASE_URL=https://rob-dev.barecoding.com
ROB_PORTAL_SECRET_KEY=
ROB_PORTAL_ALLOWED_HOSTS=rob-dev.barecoding.com,127.0.0.1,localhost
ROB_PORTAL_CSRF_TRUSTED_ORIGINS=https://rob-dev.barecoding.com
ROB_PORTAL_SUPERADMIN_USER_IDS=1299308718009356289

DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DISCORD_REDIRECT_URI=https://rob-dev.barecoding.com/portal/auth/discord/callback

PORTAL_DATABASE_URL=postgresql://rob_dev_portal:<password>@<host>:<port>/rob_dev?sslmode=require
PORTAL_MIGRATION_DATABASE_URL=postgresql://rob_dev_migrator:<password>@<host>:<port>/rob_dev?sslmode=require

ROB_OPS_HOST=127.0.0.1
ROB_OPS_PORT=8811
ROB_OPS_SECRET=
ROB_PORTAL_ALLOWED_SERVICES=rob-bot-dev.service,rob-webhook-dev.service,rob-portal-dev.service
ROB_PORTAL_ENABLE_SERVICE_ACTIONS=false
```

When `ROB_PORTAL_ENABLED=true`, the portal now enforces:

- `PORTAL_DATABASE_URL` or `DATABASE_URL` must be set
- `ROB_PORTAL_SECRET_KEY` must be non-empty and not the default placeholder
- SQLite fallback is only for disabled/local development use

## Authentication Model

1. User visits `/portal/login/`.
2. Portal redirects to Discord OAuth.
3. Callback validates OAuth state and exchanges `code` for identity.
4. Portal checks Discord ID against `ROB_PORTAL_SUPERADMIN_USER_IDS`.
5. Allowed users get a Django staff account (`is_staff=True`).
6. First configured superadmin ID is elevated to `is_superuser=True`.
7. User is signed in and redirected to `/portal/admin/`.

Non-allowlisted users are denied.

## Database Mapping

Portal models map to existing Rob tables with `managed = False`:

- `guild_settings`
- `dommes`
- `subs`
- `sends`
- `send_requests`
- `throne_creators`
- `public_leaderboards`
- `leaderboard_message`
- `bot_state`
- `counting_state`
- `blacklist`
- `schema_migrations`
- `portal_audit_log`

### Where Django’s Own Tables Live

Django creates auth/session/admin tables (`auth_user`, `django_content_type`, `django_admin_log`, etc.) in whatever database the portal connects to.

Option A (recommended for current dev): use `rob_dev` via `PORTAL_DATABASE_URL`.

- Simple operationally
- Django tables and Rob tables share the same database

Option B (cleaner future separation): use a dedicated portal database (for example `rob_portal_dev`).

- Better logical isolation
- Requires separate provisioning/migration workflow

For enabled deployments, PostgreSQL is required. SQLite is not an enabled-runtime target.

Legacy tables are surfaced as warnings in `/portal/database/`:

- `leaderboard_messages`
- `throne_wishlist_items`

## Safe Actions (Phase 1)

Available in `/portal/leaderboards/` (POST + CSRF + superadmin required):

- refresh cached Discord names (via bot-ops bridge)
- request leaderboard refresh
- toggle maintenance mode
- create public leaderboard URL
- enable/disable/rotate public leaderboard token

All actions are audit logged into `portal_audit_log`.

## Log Viewing Safety

`/portal/logs/` is restricted to allowlisted services only.

- no arbitrary service input
- no shell command execution
- uses `subprocess.run(..., shell=False, timeout=...)`
- sensitive values are redacted before rendering

## Bot Ops Bridge Connectivity

Portal action endpoints call the private bot ops bridge:

- `GET /health`
- `POST /guilds/{guild_id}/leaderboard/public/refresh-names`
- `POST /guilds/{guild_id}/leaderboard/refresh`
- `POST /maintenance`

If `ROB_OPS_SECRET` is set, requests include `X-Rob-Ops-Secret`.

### Split-server vs same-server setup

Same-server dev (portal + bot on one machine):

```dotenv
ROB_OPS_HOST=127.0.0.1
ROB_OPS_PORT=8811
ROB_OPS_SECRET=
```

Split-server dev (portal and bot on different hosts):

```dotenv
ROB_OPS_HOST=<bot-server-private-ip-or-dns>
ROB_OPS_PORT=8811
ROB_OPS_SECRET=<same-secret-as-bot>
```

Security warning: do **not** expose the bot ops bridge publicly. Use private network routing, firewall allowlists, VPN, private tunnel routing, or an internal-only agent.

Bot-side bind warning: if the portal runs on a different server, the bot ops bridge must bind to a reachable address on the bot host (for example a private NIC IP). `127.0.0.1` on the bot host is not reachable from a remote portal server. If you must use `0.0.0.0`, lock it down with strict firewall rules and allow only the portal host IP.

Recommended: bind to the bot server private IP and allow only the portal server source IP.

## Local Run

```bash
cd /opt/rob-portal/app
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r portal/requirements.txt
PYTHONPATH=. .venv/bin/python -m scripts.run_migrations
PYTHONPATH=. .venv/bin/python -m scripts.check_db
cd portal
../.venv/bin/python manage.py migrate --noinput
../.venv/bin/python manage.py collectstatic --noinput
../.venv/bin/python manage.py check
../.venv/bin/python manage.py runserver 127.0.0.1:8090
```

## Systemd Example

Use `deploy/systemd/rob-portal-dev.service` as the baseline unit.

## Nginx Example

```nginx
location /portal/static/ {
    alias /opt/rob-portal/app/portal/staticfiles/;
    access_log off;
    expires 1h;
}

location /portal/ {
    proxy_pass http://127.0.0.1:8090/portal/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_redirect off;
}
```

Keep `/public/leaderboard/` and `/throne/webhook/` routed to the existing webhook service.

## Cloudflare Notes

For `https://rob-dev.barecoding.com/portal/`:

- use SSL mode `Full (strict)`
- keep `/portal/*` uncached (cache bypass rule)
- optionally place Cloudflare Access in front of `/portal/*` for an extra auth layer

## Not Included Yet

Deliberately not shipped in this phase:

- deploy/update buttons
- arbitrary service restart buttons
- public exposure of bot-ops bridge
- raw `.env` rendering

## Troubleshooting

- If portal always returns 404: set `ROB_PORTAL_ENABLED=true`.
- If Discord login fails: verify OAuth client ID/secret/redirect URI and trusted origins.
- If actions fail with 403 from bot-ops: verify `ROB_OPS_SECRET` matches bot service env.
- If admin pages fail with table errors: run Rob SQL migrations (including `010_portal_audit_log`).

## Installation & Deployment Guide

For full server install + deploy setup steps, use `docs/deployment-portal-dev.md`.

Portal deploy uses the same SSH secrets/host as webhook deploy in GitHub Actions (`WEBHOOK_DEV_HOST`, `WEBHOOK_DEV_USER`, `WEBHOOK_DEV_SSH_KEY`, `WEBHOOK_DEV_PORT`) so both services can deploy to the same server.
