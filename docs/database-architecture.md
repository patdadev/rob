# Database Architecture (Rob v2 Rebuild)

## Databases

- Dev rehearsal: `rob_dev_v2`
- Production target: `rob_prod`

Rob runtime services should not use `defaultdb` or `_dodb` for app data.

## Runtime users

- Dev bot runtime: `dev_rob_bot`
- Prod bot runtime: `prod_rob_bot`
- Prod webhook runtime: `prod_rob_webhook`

Schema creation/alteration is handled manually by `doadmin` (or provider-equivalent admin).

## Ownership and privileges model

- DB build scripts are executed manually in `psql`/pgAdmin4 by `doadmin`.
- Runtime users are **not** schema owners.
- Runtime users must **not** have `CREATE`, `ALTER`, `DROP`, or `TRUNCATE`.
- Runtime users only receive operational permissions required by app code.

## Core v2 tables

- `db_build_version`
- `bot_settings`
- `bot_users`
- `dommes`
- `subs`
- `sends`
- `vib_settings`
- `vib_leaderboard`
- `the_count`
- `inactive_users`

## `bot_settings` JSON shape

`bot_settings.value` is JSON and should use stable keys for operational state.  
For maintenance-related state, prefer:

```json
{
  "enabled": true,
  "message": "Maintenance reason text",
  "updated_by": 123456789012345678
}
```

## Removed legacy tables/features

The v2 rebuild intentionally removes legacy dependencies from runtime code:

- `send_requests` table and `/sendrequest`
- `blacklist`/`rob_blacklist` tables (replaced by `bot_users.status='blocked'`)
- `throne_creators` table (folded into `dommes`)
- `guild_settings` table (replaced by `vib_settings`)
- `leaderboard_message` and `public_leaderboards` (merged into `vib_leaderboard`)
- `counting_state` (replaced by `the_count`)
- `bot_state` (replaced by `bot_settings`)
- `schema_migrations` (replaced by `db_build_version`)
- portal/Django tables

## Webhook compatibility route

Both routes are supported:

- `POST /throne/webhook/{creator_id}/{secret}` (compatibility)
- `POST /webhook/{creator_id}/{secret}` (preferred)

Preferred production URL base:

- `https://throne.robthebot.com/webhook/{creator_id}/{secret}`

## Runtime DB check behavior

`scripts/check_db.py` validates:

1. required v2 tables/columns
2. required `db_build_version` entries (`001_core_schema`, `002_indexes`)
3. runtime permission profile for `_bot` and `_webhook` users
4. no schema `CREATE` privilege for runtime users

`check_db` never creates or alters schema.
