# Operations Runbook

This page is a practical checklist for day-to-day Rob operations in production/dev.

## Install Global `rob`

```bash
scripts/install-rob-global.sh
```

After this, `rob` is available globally from shell sessions. `robctl` still works as a compatibility alias.

## Health + Service Checks

```bash
rob status
rob logs bot
rob logs webhook
```

## Maintenance Window

```bash
rob maintenance on "Deploying update"
rob queue status
rob maintenance off
rob queue flush
```

## Leaderboard Recovery

```bash
rob leaderboard refresh
rob leaderboard status --guild-id <guild_id>
rob leaderboard diagnose --guild-id <guild_id>
rob leaderboard repair-send-dommes --guild-id <guild_id> --dry-run
rob leaderboard repair-send-dommes --guild-id <guild_id>
```

If message refs are missing but Discord messages still exist:

```bash
rob leaderboard adopt --guild-id <guild_id> --leaderboard-channel-id <channel_id> --leaderboard-message-id <message_id> --stats-message-id <message_id>
```

## Send Pipeline Operations

```bash
rob sends list --status all --guild-id <guild_id> --limit 25
rob sends mark-posted <send_id>
rob sends backfill-public-ids
rob throne invalidate-test-sends
```

## Guild Channel Config Audit

```bash
rob guild scan --guild-id <guild_id>
rob guild set-channel --guild-id <guild_id> --field leaderboard_channel_id --channel-id <channel_id>
rob guild set-channel --guild-id <guild_id> --field report_channel_id --clear
rob guild set-role --guild-id <guild_id> --field domme_role_id --role-id <role_id>
rob guild set-role --guild-id <guild_id> --field inactive_role_id --clear
```

`rob guild scan` prints the current DB values, checks whether the configured channels and roles still exist in Discord, and suggests exact `rob guild set-channel ...` and `rob guild set-role ...` commands for missing fields.

The scan now prefers the already-running bot session for live Discord data, then falls back to direct Discord REST if the local bot-ops bridge is unavailable. By default that bridge listens on `127.0.0.1:8811`. If you want to lock it down further, set `ROB_OPS_SECRET` in `.env`.

## Throne Registration Audit

```bash
rob throne status --guild-id <guild_id>
rob throne dommes --guild-id <guild_id>
rob throne subs --guild-id <guild_id>
rob throne status --guild-id <guild_id> --handle <throne_handle>
```

## Inactivity System

```bash
rob inactivity status --guild-id <guild_id>
rob inactivity on --guild-id <guild_id>
rob inactivity off --guild-id <guild_id>
```

In Discord:

- `/inactivelist` shows current tracked inactive members and scheduled removal timestamps.
- `/inactivitytest` sends template inactivity notices to your DM.

## Blacklist Operations

```bash
rob blacklist list --limit 100
rob blacklist add <discord_user_id> --reason "manual"
rob blacklist remove <discord_user_id>
```

In Discord (moderator permissions required):

- `!rob-blacklist <discord_user_id_or_mention> [reason]`
- `!rob-unblacklist <discord_user_id_or_mention>`
- `!throne-blacklist <discord_user_id_or_mention>`
