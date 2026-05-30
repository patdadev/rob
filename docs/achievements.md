# Rob Achievements

Rob achievements are definition-driven in code, with per-user unlock state stored in PostgreSQL.

## Where things live

- Definitions: `rob/achievements/definitions.py`
- Unlock/query service: `rob/achievements/service.py`
- Achievement card renderers: `rob/achievements/embeds.py`
- Runtime command handlers: `rob/discord/cogs/achievements.py`
- DB tables:
  - `user_achievements`
  - `achievement_events`

## Categories

- `count`
- `sends_domme`
- `sends_sub`
- `leaderboard`
- `throne_tracking`
- `inactivity`
- `maintenance`
- `misc`
- `secret`

## Manual DB setup

Run manually as `doadmin`:

1. Ensure base DB build scripts are already applied:
   - `scripts/db/build/001_core_schema.sql`
   - `scripts/db/build/002_indexes.sql`
2. Apply achievements and current rehearsal extensions:
   - `scripts/db/build/003_achievements.sql`
   - `scripts/db/build/004_sub_send_names.sql`
   - `scripts/db/build/005_count_recovery.sql`
   - `scripts/db/build/006_send_change_requests.sql`
3. Re-run the relevant grants file:
   - dev rehearsal: `scripts/db/grants/dev_rehearsal_prod_roles.sql`
   - prod bot: `scripts/db/grants/prod_rob_bot.sql`
   - prod webhook: `scripts/db/grants/prod_rob_webhook.sql`
4. Validate with runtime credentials:
   - `PYTHONPATH=. python3 -m scripts.check_db`

If `scripts.check_db.py` reports achievement tables missing, apply the SQL manually and rerun the check.

## Slash commands

- `/achievements`
- `/achievements user:@user`
- `/test achievements` (staff/dev only; visual preview only, no DB writes)

`/test achievements` sends preview cards for every configured achievement so copy/layout can be reviewed in Discord.

## Unlock announcement behavior

- Achievement unlocks are announced in the same context that caused the unlock when that flow supports announcements.
- Unlock announcements now mention the unlocked user directly so Discord actually pings them.
- The footer text is:

  `Achievements Unlock by {display_name}`

- `/achievements` itself remains a view command and should not start pinging people just because someone opens the catalogue.

## Adding a new achievement

1. Add definition in `rob/achievements/definitions.py`.
2. Hook unlock trigger in the relevant service/cog flow.
3. Add/update tests for:
   - key presence/uniqueness
   - unlock behavior
   - command rendering if user-facing

## Current trigger notes

- Count/send/leaderboard/throne setup + test webhook + DM + achievements-view triggers are wired.
- Some definitions remain TODO-gated until deeper event history exists (for example some regain/recovery edge cases).
