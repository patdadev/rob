# Backend Commands

Use [`scripts/rob`](../scripts/rob) from the server checkout, or install the global shell wrapper.

To install `rob` as a global bash/zsh command:

```bash
scripts/install-rob-global.sh
```

The installer prefers a real system-wide binary link in `/usr/local/bin` when it has permission, and otherwise falls back to `~/.local/bin`.

## Supported commands

```bash
scripts/rob status
scripts/rob logs bot
scripts/rob logs webhook
scripts/rob restart bot
scripts/rob restart webhook
scripts/rob restart all

scripts/rob maintenance status
scripts/rob maintenance on "Deploying schema changes"
scripts/rob maintenance off

scripts/rob queue status
scripts/rob queue flush

scripts/rob leaderboard refresh
scripts/rob leaderboard adopt --guild-id 123 --leaderboard-channel-id 456 --leaderboard-message-id 789 --stats-message-id 790
scripts/rob leaderboard status --guild-id 123
scripts/rob leaderboard preview --guild-id 123
scripts/rob leaderboard diagnose --guild-id 123
scripts/rob leaderboard repair-send-dommes --guild-id 123 --dry-run
scripts/rob leaderboard repair-send-dommes --guild-id 123

scripts/rob throne status --guild-id 123
scripts/rob throne status --guild-id 123 --handle pat
scripts/rob throne refresh
scripts/rob throne dommes --guild-id 123
scripts/rob throne list --guild-id 123
scripts/rob throne search --guild-id 123 <@123456789012345678>
scripts/rob throne subs --guild-id 123
scripts/rob throne webhook refresh --guild-id 123 <@123456789012345678>
scripts/rob throne addsend --guild-id 123 <@123456789012345678> 100 --sub-name marie_123 --method cashapp --note "manual adjustment"
scripts/rob throne addsub --guild-id 123 <@123456789012345678> marie_123
scripts/rob throne adddomme --guild-id 123 <@123456789012345678> https://throne.com/pat
scripts/rob throne invalidate-test-sends
scripts/rob inactivity status --guild-id 123
scripts/rob inactivity on --guild-id 123
scripts/rob inactivity off --guild-id 123
scripts/rob blacklist add 123456789012345678 --reason "manual"
scripts/rob blacklist remove 123456789012345678
scripts/rob blacklist list --limit 50
scripts/rob sends backfill-public-ids
scripts/rob sends list --status all --guild-id 123 --limit 25
scripts/rob sends mark-posted 151
scripts/rob guild scan --guild-id 123
scripts/rob guild set-channel --guild-id 123 --field leaderboard_channel_id --channel-id 456
scripts/rob guild set-channel --guild-id 123 --field report_channel_id --clear
scripts/rob guild set-role --guild-id 123 --field domme_role_id --role-id 654
scripts/rob guild set-role --guild-id 123 --field inactive_role_id --clear

scripts/rob count status
scripts/rob count set 123
```

## Notes

- Example bash aliases/functions for daily ops:

```bash
alias rob='scripts/rob'
alias rob-lb-refresh='scripts/rob leaderboard refresh'
alias rob-lb-status='scripts/rob leaderboard status'
alias rob-maint-on='scripts/rob maintenance on'
alias rob-maint-off='scripts/rob maintenance off'
alias rob-queue='scripts/rob queue status'
alias rob-queue-flush='scripts/rob queue flush'
alias rob-sends='scripts/rob sends list --status all --guild-id 123 --limit 25'
alias rob-sends-backfill='scripts/rob sends backfill-public-ids'
```

- `maintenance on/off`, `queue status`, `queue flush`, `leaderboard refresh`, and `count` commands talk directly to PostgreSQL through `scripts.ops`.
- `rob` is a bash-native global wrapper; it delegates data operations to Python (`python -m scripts.ops`) so ops logic remains versioned and testable in the app codebase.
- `robctl` remains available as a compatibility shim that forwards to `rob`.
- `rob` supports short aliases to simplify typing:
  - `rob lb ...` for `rob leaderboard ...`
  - `rob q ...` for `rob queue ...`
  - `rob m ...` for `rob maintenance ...`
  - `rob g ...` for `rob guild ...`
  - `rob s ...` for `rob sends ...`
  - `rob t ...` for `rob throne ...`
  - `rob c ...` for `rob count ...`
  - `rob i ...` for `rob inactivity ...`
  - `rob bl ...` for `rob blacklist ...`
- Deploy scripts now run `scripts/run_migrations.py` before `scripts/check_db.py`, and `check_db` validates required schema columns so deploys fail fast on schema drift.
- `leaderboard adopt` lets you attach existing Discord message IDs to `leaderboard_message` refs (`leaderboard` + `leaderboard_stats`) so refresh/edit paths can resume without reposting.
- `guild scan` reads current `guild_settings` channel and role fields, prefers the already-running bot session for live Discord guild data, and falls back to direct Discord REST only if the local bot-ops endpoint is unavailable.
- The running bot exposes a local-only ops bridge on `ROB_OPS_HOST` / `ROB_OPS_PORT` (`127.0.0.1:8811` by default). Set `ROB_OPS_SECRET` in `.env` if you want the bridge to require an auth header from `rob`.
- `guild set-channel` updates one whitelisted `guild_settings` channel field in PostgreSQL and refreshes `updated_at`.
- `guild set-role` updates one whitelisted `guild_settings` role field in PostgreSQL and refreshes `updated_at`.
- `maintenance on` now requests a leaderboard refresh automatically so the main leaderboard status switches to `🟠 Paused (Maintenance)` on the next bot refresh cycle.
- `maintenance off` now clears maintenance mode, releases queued maintenance sends back to `pending`, and requests a leaderboard refresh so the main leaderboard can return to `🟢 Live`.
- `throne invalidate-test-sends` marks previously recorded sends from usernames in `THRONE_TEST_GIFTER_USERNAMES` as `is_test_send=true` so they stop affecting leaderboard totals when test parsing is disabled again.
- `sends backfill-public-ids` generates and stores missing `public_send_id` values for older rows so support/admin workflows can use stable indexed public IDs.
- `logs` and `restart` use `journalctl` and `systemctl`, so they are meant for the server where the service is installed.
- `restart` uses `sudo systemctl restart ...`, so the deploy or operator user should have passwordless sudo for the specific Rob services.
- A minimal sudoers entry is usually enough, for example:

```sudoers
Cmnd_Alias ROB_BOT_CTL = /bin/systemctl restart rob-bot-dev.service, /usr/bin/systemctl restart rob-bot-dev.service
Cmnd_Alias ROB_WEBHOOK_CTL = /bin/systemctl restart rob-webhook-dev.service, /usr/bin/systemctl restart rob-webhook-dev.service
deployuser ALL=(root) NOPASSWD: ROB_BOT_CTL, ROB_WEBHOOK_CTL
```

- `queue flush` refuses to run while maintenance mode is still enabled.
- `rob` with no arguments now prints friendly usage/help and exits `0`.

- 2026-05-23: Public send card now uses compact Components V2 layout with real `discord.ui.Separator()`, item thumbnails, friendly currency names, and purple accent constants from `rob/ui/theme.py`; rank lines/footer/timestamps removed.
- 2026-05-23: Added `scripts/rob throne invalidate-test-sends` so historical known test sends can be backfilled as `is_test_send=true`.
- 2026-05-23: Added `scripts/rob sends backfill-public-ids` and a stored `sends.public_send_id` column for indexed support/admin lookups.
- 2026-05-23: NEW LEADER ALERT posting is now live in the leaderboard/send-tracker channel flow with bot-state dedupe.
- 2026-05-23: Leaderboard refreshes now show dynamic status text: `🟢 Live` normally and `🟠 Paused (Maintenance)` when maintenance mode is enabled. `🔴 Offline` is supported at the card layer for an explicit future offline source.
- 2026-05-22: Leaderboard and stats cards now use explicit separator components; stats include Unclaimed Sends section.


## Inactivity timing
- New inactive members now use a 7-day no-warning grace period (`INACTIVITY_NEW_MEMBER_GRACE_DAYS`, default `7`).
- First warning sends at ~day 7 and includes Discord relative/full removal timestamps (`<t:...:R> / <t:...:f>`).
- Final warning sends at ~day 14 (`INACTIVITY_FINAL_NOTICE_DAYS` before removal) and clarifies removal is not a ban.
- Removal runs at ~day 21 of inactivity by default.
