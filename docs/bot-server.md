# Bot Server

The bot server is the Discord-only side of Rob.

## Responsibilities

- Connects to Discord.
- Connects to PostgreSQL.
- Accepts send notifications from the webhook through the private bot ops bridge.
- Processes the specific recorded send immediately instead of constantly polling pending sends.
- Releases `queued_maintenance` sends after maintenance is disabled.
- Posts send notifications to the configured tracking channel.
- Refreshes leaderboard messages from posted sends.
- Ignores imported legacy sends that were already marked `posted`.
- Handles `/register`, `/leaderboard`, `/add`, and `/count set`.
- Runs the counting listener.

## Runtime

- Entry point: `python -m apps.bot.main`
- Background worker: `rob.services.send_queue_service.SendQueueService`
- PostgreSQL is the source of truth for queue state and maintenance state.
- The queue worker processes send IDs pushed by the webhook and only uses slow fallback checks for maintenance/ops requests.

## Required environment

- `APP_ENV`
- `LOG_LEVEL`
- `DATABASE_URL`
- `DISCORD_TOKEN`
- `BOT_NAME`
- `ROB_OPS_HOST`
- `ROB_OPS_PORT`
- `ROB_OPS_SECRET`

The bot does not host the Throne webhook HTTP server.

## Runtime verification

Run this on the bot host after editing `.env` or after a deploy:

```bash
sudo bash deploy/scripts/check-bot-runtime.sh
```

It validates the parsed bot settings, DB grants/schema, systemd state, the
local bot-ops health endpoint, and the bot's webhook-notify bridge settings.

## Webhook-to-bot send notifications

The bot ops bridge listens on `ROB_OPS_HOST:ROB_OPS_PORT`, usually `127.0.0.1:8811`.
Because that address is local to the bot server, the webhook server cannot reach it unless the bot server exposes a small, protected reverse proxy route.

Recommended Nginx route on `bot-01.robthebot.com`:

```nginx
location = /ops/sends/process {
    proxy_pass http://127.0.0.1:8811/ops/sends/process;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Keep the bot ops bridge itself bound to `127.0.0.1`. Do not open port `8811` publicly.
The webhook must send the matching `ROB_OPS_SECRET` header through `ROB_BOT_NOTIFY_URL`.
