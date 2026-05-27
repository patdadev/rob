# Maintenance Mode

Maintenance mode is stored in PostgreSQL `bot_settings` using:

- `maintenance_mode`
- `maintenance_reason`

It is controlled from backend shell commands, not from broad Discord admin commands.

## During Maintenance

- Incoming sends are still saved to PostgreSQL.
- Webhook sends are inserted as `queued_maintenance`.
- The bot does not post queued sends to Discord.
- Leaderboard messages continue to reflect posted sends only.
- Legacy imported sends that were seeded as `posted` stay out of the queue.

## After Maintenance

When maintenance mode is disabled, the bot queue worker:

1. Releases `queued_maintenance` sends back to `pending`.
2. Processes them oldest-first.
3. Marks successful posts as `posted`.
4. Marks failures as `failed`.
5. Refreshes leaderboard messages.

## Commands

```bash
scripts/rob maintenance status
scripts/rob maintenance on "reason"
scripts/rob maintenance off
scripts/rob queue status
scripts/rob queue flush
```
