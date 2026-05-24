# Operations Runbook

This page is a practical checklist for day-to-day Rob operations in production/dev.

## Install Global `robctl`

```bash
scripts/install-robctl-global.sh
```

After this, `robctl` is available globally from shell sessions.

## Health + Service Checks

```bash
robctl status
robctl logs bot
robctl logs webhook
```

## Maintenance Window

```bash
robctl maintenance on "Deploying update"
robctl queue status
robctl maintenance off
robctl queue flush
```

## Leaderboard Recovery

```bash
robctl leaderboard refresh
robctl leaderboard status --guild-id <guild_id>
robctl leaderboard diagnose --guild-id <guild_id>
robctl leaderboard repair-send-dommes --guild-id <guild_id> --dry-run
robctl leaderboard repair-send-dommes --guild-id <guild_id>
```

If message refs are missing but Discord messages still exist:

```bash
robctl leaderboard adopt --guild-id <guild_id> --leaderboard-channel-id <channel_id> --leaderboard-message-id <message_id> --stats-message-id <message_id>
```

## Send Pipeline Operations

```bash
robctl sends list --status all --guild-id <guild_id> --limit 25
robctl sends mark-posted <send_id>
robctl sends backfill-public-ids
robctl throne invalidate-test-sends
```

## Throne Registration Audit

```bash
robctl throne status --guild-id <guild_id>
robctl throne dommes --guild-id <guild_id>
robctl throne subs --guild-id <guild_id>
robctl throne status --guild-id <guild_id> --handle <throne_handle>
```

## Inactivity System

```bash
robctl inactivity status --guild-id <guild_id>
robctl inactivity on --guild-id <guild_id>
robctl inactivity off --guild-id <guild_id>
```

In Discord:

- `/inactivelist` shows current tracked inactive members and scheduled removal timestamps.
- `/inactivitytest` sends template inactivity notices to your DM.

## Blacklist Operations

```bash
robctl blacklist list --limit 100
robctl blacklist add <discord_user_id> --reason "manual"
robctl blacklist remove <discord_user_id>
```

In Discord (moderator permissions required):

- `!rob-blacklist <discord_user_id_or_mention> [reason]`
- `!rob-unblacklist <discord_user_id_or_mention>`
- `!throne-blacklist <discord_user_id_or_mention>`
