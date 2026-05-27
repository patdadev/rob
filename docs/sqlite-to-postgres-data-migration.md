# SQLite -> PostgreSQL Data Migration

This process imports legacy SQLite data into the v2 PostgreSQL schema.

## Source and target

- Source SQLite (read-only): `/opt/rob-the-bot/data/rob_the_bot.sqlite3`
- Dev rehearsal target: `rob_dev_v2`

## Safety rules

1. Do not write to live SQLite.
2. Default run is dry-run.
3. `--truncate-target` requires `--confirm-truncate`.
4. Truncate is blocked on prod-like DB names unless `--allow-prod-truncate` is explicitly passed.
5. Database URL secrets are never printed.

## Inspect source only

```bash
python3 -m scripts.data_migration.inspect_sqlite \
  --sqlite /opt/rob-the-bot/data/rob_the_bot.sqlite3 \
  --report-json /tmp/rob-sqlite-inspect.json
```

## Build import payload + dry-run

```bash
python3 -m scripts.data_migration.import_sqlite_to_postgres \
  --sqlite /opt/rob-the-bot/data/rob_the_bot.sqlite3 \
  --database-url 'postgresql://dev_rob_bot:***@host:25060/rob_dev_v2?sslmode=require' \
  --default-guild-id 1506597978251591813 \
  --dry-run \
  --report-json /tmp/rob-import-dry-run.json
```

## Real import (writes data)

```bash
python3 -m scripts.data_migration.import_sqlite_to_postgres \
  --sqlite /opt/rob-the-bot/data/rob_the_bot.sqlite3 \
  --database-url 'postgresql://dev_rob_bot:***@host:25060/rob_dev_v2?sslmode=require' \
  --default-guild-id 1506597978251591813 \
  --no-dry-run \
  --report-json /tmp/rob-import-apply.json
```

Optional target reset (dangerous):

```bash
python3 -m scripts.data_migration.import_sqlite_to_postgres \
  --sqlite /opt/rob-the-bot/data/rob_the_bot.sqlite3 \
  --database-url 'postgresql://dev_rob_bot:***@host:25060/rob_dev_v2?sslmode=require' \
  --default-guild-id 1506597978251591813 \
  --no-dry-run \
  --truncate-target \
  --confirm-truncate
```

## Mapping summary

- `bot_config` -> `bot_settings`, `the_count`, `inactive_users`
- `event_dommes` -> `bot_users`, `dommes`
- `event_subs` -> `bot_users`, `subs`
- `event_sends` -> `bot_users`, `sends`
- `event_messages` -> `vib_leaderboard`
- `throne_creators` -> `bot_users`, `dommes` tracking columns
- `rob_blacklist` -> `bot_users.status='blocked'`
- `send_requests` -> folded into `sends` only when approved and not duplicated
- `throne_wishlist_items` -> ignored by default

## Report output notes

Importer output explicitly reports:

- `send_requests`: `found`, `accepted`, `inserted_into_sends`, `skipped_duplicate`, `skipped_missing_domme`
- `throne_creators_merge`: totals and conflict counts
- `event_sends_skipped_missing_domme`
- `throne_wishlist_items_ignored` row count (when wishlist cache is not included)

This avoids silent data-shape handling during rehearsal imports.
