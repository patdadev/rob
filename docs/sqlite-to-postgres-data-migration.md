# SQLite -> PostgreSQL Data Migration

This process imports legacy SQLite data into the v2 PostgreSQL schema.

This is a data migration only. It is not a schema build step, and it is not part of deploy.

## Source and target

- Source SQLite (read-only): `/opt/rob-the-bot/data/rob_the_bot.sqlite3`
- Dev rehearsal target: `rob_dev_v2`

Before importing data, manually apply DB build SQL (as `doadmin`) in this order:

1. `scripts/db/build/001_core_schema.sql`
2. `scripts/db/build/002_indexes.sql`
3. `scripts/db/build/003_achievements.sql`
4. `scripts/db/build/004_sub_send_names.sql`
5. `scripts/db/build/005_count_recovery.sql`
6. `scripts/db/build/006_send_change_requests.sql`

## Safety rules

1. Do not write to live SQLite.
2. Default run is dry-run.
3. `--truncate-target` requires `--confirm-truncate`.
4. Truncate is blocked on prod-like DB names unless `--allow-prod-truncate` is explicitly passed.
5. Database URL secrets are never printed.

## Legacy AWS rehearsal helpers

Run these on the soon-to-be-legacy AWS host when you want Rob to find the likely SQLite database and rehearse the import safely.

### Find likely SQLite candidates

```bash
python3 -m scripts.data_migration.legacy_server.find_sqlite_candidates
```

This scans common legacy roots such as `/opt`, `/srv`, `/var`, `/home/ec2-user`, and `/home/ubuntu`, then ranks candidates by Rob-shaped table fingerprints.

### Build a concise legacy report

```bash
python3 -m scripts.data_migration.legacy_server.legacy_sqlite_report
```

Optional explicit source:

```bash
python3 -m scripts.data_migration.legacy_server.legacy_sqlite_report \
  --sqlite /opt/rob-the-bot/data/rob_the_bot.sqlite3 \
  --report-json /tmp/legacy-sqlite-report.json
```

### Full rehearsal dry-run from the legacy host

```bash
scripts/data_migration/legacy_server/legacy_to_pg_dry_run.sh \
  --database-url 'postgresql://prod_rob_bot:***@host:25060/rob_dev_v2?sslmode=require' \
  --default-guild-id 1506597978251591813
```

This will:

1. locate or validate the SQLite source;
2. run the inspection report;
3. run the PostgreSQL importer in `--dry-run` mode;
4. write timestamped report artifacts under `/tmp`.

### Real rehearsal import from the legacy host

```bash
scripts/data_migration/legacy_server/legacy_to_pg_apply.sh \
  --database-url 'postgresql://prod_rob_bot:***@host:25060/rob_dev_v2?sslmode=require' \
  --default-guild-id 1506597978251591813 \
  --confirm-apply yes
```

This does not create schema, roles, or grants. Run the DB build SQL and grants manually first.

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
  --database-url 'postgresql://prod_rob_bot:***@host:25060/rob_dev_v2?sslmode=require' \
  --default-guild-id 1506597978251591813 \
  --dry-run \
  --report-json /tmp/rob-import-dry-run.json
```

## Real import (writes data)

```bash
python3 -m scripts.data_migration.import_sqlite_to_postgres \
  --sqlite /opt/rob-the-bot/data/rob_the_bot.sqlite3 \
  --database-url 'postgresql://prod_rob_bot:***@host:25060/rob_dev_v2?sslmode=require' \
  --default-guild-id 1506597978251591813 \
  --no-dry-run \
  --report-json /tmp/rob-import-apply.json
```

Optional target reset (dangerous):

```bash
python3 -m scripts.data_migration.import_sqlite_to_postgres \
  --sqlite /opt/rob-the-bot/data/rob_the_bot.sqlite3 \
  --database-url 'postgresql://prod_rob_bot:***@host:25060/rob_dev_v2?sslmode=require' \
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

## Recommended rehearsal order

1. Take a safe SQLite backup or snapshot.
2. Run `legacy_sqlite_report.py` or `find_sqlite_candidates.py` on the legacy host.
3. Run `legacy_to_pg_dry_run.sh` against `rob_dev_v2`.
4. Review Dom/me counts, Sub counts, send totals, and count-state parity.
5. Run `legacy_to_pg_apply.sh` only after the dry-run looks correct.
6. Validate the imported result with:
   - `rob migration audit --guild <guild_id>`
   - `PYTHONPATH=. python3 -m scripts.check_db`
   - live bot/webhook rehearsal against `rob_dev_v2`
