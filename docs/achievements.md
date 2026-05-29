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

Run manually as `doadmin` for rehearsal on `rob_dev_v2`:

1. Build the base `rob_dev_v2` schema with `001_core_schema.sql` and `002_indexes.sql`.
2. Run `scripts/db/build/003_achievements.sql`.
3. Run `scripts/db/grants/dev_rehearsal_prod_roles.sql`.
4. Configure the bot and webhook servers to use production-style runtime users against `rob_dev_v2` for rehearsal:
   - `prod_rob_bot`
   - `prod_rob_webhook`
5. Validate with each runtime credential:
   - `PYTHONPATH=. python3 -m scripts.check_db`

`rob_dev_v2` is the rehearsal database. `prod_rob_bot` is the bot runtime user. `prod_rob_webhook` is the webhook runtime user. Production runtime should later point to `rob_prod`, not `rob_dev_v2`.

For production on `rob_prod`, run `scripts/db/build/003_achievements.sql`, then re-run the relevant production grants file:

- prod bot: `scripts/db/grants/prod_rob_bot.sql`
- prod webhook: `scripts/db/grants/prod_rob_webhook.sql`

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
