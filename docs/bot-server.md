# Bot Server

The bot server is the Discord-only side of Rob.

## Responsibilities

- Connects to Discord.
- Connects to PostgreSQL.
- Processes `sends.discord_post_status='pending'`.
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
- The queue worker fetches only `pending` sends, so legacy imported rows already marked `posted` are not reposted.

## Required environment

- `APP_ENV`
- `LOG_LEVEL`
- `DATABASE_URL`
- `DISCORD_TOKEN`
- `BOT_NAME`

The bot does not host the Throne webhook HTTP server.
