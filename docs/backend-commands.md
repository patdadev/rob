# Backend Commands

Use [`scripts/robctl`](../scripts/robctl) from the server checkout, or install a shell alias that points to it.

To install `robctl` as a global bash/zsh command:

```bash
scripts/install-robctl-global.sh
```

## Supported commands

```bash
scripts/robctl status
scripts/robctl logs bot
scripts/robctl logs webhook
scripts/robctl restart bot
scripts/robctl restart webhook
scripts/robctl restart all

scripts/robctl maintenance status
scripts/robctl maintenance on "Deploying schema changes"
scripts/robctl maintenance off

scripts/robctl queue status
scripts/robctl queue flush

scripts/robctl leaderboard refresh
scripts/robctl leaderboard adopt --guild-id 123 --leaderboard-channel-id 456 --leaderboard-message-id 789 --stats-message-id 790
scripts/robctl leaderboard status --guild-id 123
scripts/robctl leaderboard preview --guild-id 123
scripts/robctl leaderboard diagnose --guild-id 123
scripts/robctl leaderboard repair-send-dommes --guild-id 123 --dry-run
scripts/robctl leaderboard repair-send-dommes --guild-id 123

scripts/robctl throne status --guild-id 123
scripts/robctl throne status --guild-id 123 --handle pat
scripts/robctl throne refresh
scripts/robctl throne dommes --guild-id 123
scripts/robctl throne list --guild-id 123
scripts/robctl throne search --guild-id 123 <@123456789012345678>
scripts/robctl throne subs --guild-id 123
scripts/robctl throne webhook refresh --guild-id 123 <@123456789012345678>
scripts/robctl throne addsend --guild-id 123 <@123456789012345678> 100 --sub-name marie_123 --method cashapp --note "manual adjustment"
scripts/robctl throne addsub --guild-id 123 <@123456789012345678> marie_123
scripts/robctl throne adddomme --guild-id 123 <@123456789012345678> https://throne.com/pat
scripts/robctl throne invalidate-test-sends
scripts/robctl inactivity status --guild-id 123
scripts/robctl inactivity on --guild-id 123
scripts/robctl inactivity off --guild-id 123
scripts/robctl blacklist add 123456789012345678 --reason "manual"
scripts/robctl blacklist remove 123456789012345678
scripts/robctl blacklist list --limit 50
scripts/robctl sends backfill-public-ids
scripts/robctl sends list --status all --guild-id 123 --limit 25
scripts/robctl sends mark-posted 151

scripts/robctl count status
scripts/robctl count set 123
```

## Notes

- Example bash aliases/functions for daily ops:

```bash
alias robctl='scripts/robctl'
alias rob-lb-refresh='scripts/robctl leaderboard refresh'
alias rob-lb-status='scripts/robctl leaderboard status'
alias rob-maint-on='scripts/robctl maintenance on'
alias rob-maint-off='scripts/robctl maintenance off'
alias rob-queue='scripts/robctl queue status'
alias rob-queue-flush='scripts/robctl queue flush'
alias rob-sends='scripts/robctl sends list --status all --guild-id 123 --limit 25'
alias rob-sends-backfill='scripts/robctl sends backfill-public-ids'
```

- `maintenance on/off`, `queue status`, `queue flush`, `leaderboard refresh`, and `count` commands talk directly to PostgreSQL through `scripts.ops`.
- `robctl` is a bash-native global wrapper; it delegates data operations to Python (`python -m scripts.ops`) so ops logic remains versioned and testable in the app codebase.
- Deploy scripts now run `scripts/run_migrations.py` before `scripts/check_db.py`, and `check_db` validates required schema columns so deploys fail fast on schema drift.
- `leaderboard adopt` lets you attach existing Discord message IDs to `leaderboard_message` refs (`leaderboard` + `leaderboard_stats`) so refresh/edit paths can resume without reposting.
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
- `robctl` with no arguments now prints friendly usage/help and exits `0`.

- 2026-05-23: Public send card now uses compact Components V2 layout with real `discord.ui.Separator()`, item thumbnails, friendly currency names, and purple accent constants from `rob/ui/theme.py`; rank lines/footer/timestamps removed.
- 2026-05-23: Added `scripts/robctl throne invalidate-test-sends` so historical known test sends can be backfilled as `is_test_send=true`.
- 2026-05-23: Added `scripts/robctl sends backfill-public-ids` and a stored `sends.public_send_id` column for indexed support/admin lookups.
- 2026-05-23: NEW LEADER ALERT posting is now live in the leaderboard/send-tracker channel flow with bot-state dedupe.
- 2026-05-23: Leaderboard refreshes now show dynamic status text: `🟢 Live` normally and `🟠 Paused (Maintenance)` when maintenance mode is enabled. `🔴 Offline` is supported at the card layer for an explicit future offline source.
- 2026-05-22: Leaderboard and stats cards now use explicit separator components; stats include Unclaimed Sends section.
