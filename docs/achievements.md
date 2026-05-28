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

1. `scripts/db/build/003_achievements.sql`
2. Re-run the relevant grants file:
   - dev: `scripts/db/grants/dev_rob_bot.sql`
   - prod bot: `scripts/db/grants/prod_rob_bot.sql`
   - prod webhook: `scripts/db/grants/prod_rob_webhook.sql`
3. Validate with runtime credentials:
   - `PYTHONPATH=. python3 -m scripts.check_db`

If `scripts.check_db.py` reports achievement tables missing, apply the SQL manually and rerun the check.

## Slash commands

- `/achievements`
- `/achievements user:@user`
- `/test achievements` (staff/dev only; visual preview only, no DB writes)

`/test achievements` sends preview cards for every configured achievement so copy/layout can be reviewed in Discord.

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
