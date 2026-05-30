# Operations Runbook

This page is a practical checklist for day-to-day Rob operations in production/dev.

## Repo promotion: `rob-dev` -> `rob`

Treat the promotion as code promotion plus data rehearsal, not as a merge from the old `notpatdev/robthebot` repo.

Recommended order:

1. Push the current `rob-dev` codebase to a non-`main` bootstrap branch in `PlainStack2/rob`.
2. Copy GitHub Actions secrets, environments, and protection rules into `PlainStack2/rob`.
3. Verify the workflow wiring in the new repo before touching `main`.
4. Keep `PlainStack2/rob-dev` intact as rollback/reference during rehearsal.
5. Rehearse data import and webhook reissue on `rob_dev_v2`.
6. Only then move `PlainStack2/rob:main` to the promoted codebase.

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

While maintenance is enabled:

- leaderboard status changes to `🟠 Paused | Under Maintenance`;
- send posts are queued instead of published;
- leaderboard refresh waits until maintenance ends;
- `/register domme` and `/register sub` stay inactive;
- counting remains active.

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

## Rehearsal Migration and Webhook Reissue

```bash
rob migration audit --guild <guild_id>
rob webhook preview --guild <guild_id>
rob webhook send --guild <guild_id> --all --limit 10
rob webhook send --guild <guild_id> --discord-user-id <discord_user_id>
rob clear rob_dev_v2
```

Suggested rehearsal sequence:

1. Run the manual DB build SQL and grants for `rob_dev_v2`.
2. Run the legacy AWS discovery/report helpers.
3. Dry-run the SQLite import.
4. Apply the import into `rob_dev_v2`.
5. Run `rob migration audit --guild <guild_id>`.
6. Run `rob webhook preview --guild <guild_id>`.
7. Reissue webhook URLs in small batches with `rob webhook send`.

`rob clear rob_dev_v2` is deliberately read-only. It prints SQL for manual review and execution in pgAdmin/psql, and preserves schema plus `db_build_version`.

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
