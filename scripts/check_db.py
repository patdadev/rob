from __future__ import annotations

import asyncio
from pathlib import Path

from rob.config.settings import configure_logging, load_base_settings
from rob.database.connection import Database

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "rob" / "database" / "migrations"


async def _assert_table_columns(connection, table: str, required_columns: set[str]) -> None:
    rows = await connection.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = $1
        """,
        table,
    )
    if not rows:
        raise RuntimeError(f"Missing required table: {table}")
    present = {str(row["column_name"]) for row in rows}
    missing = sorted(required_columns - present)
    if missing:
        raise RuntimeError(f"Table {table} is missing required columns: {', '.join(missing)}")


async def main() -> None:
    settings = load_base_settings()
    configure_logging(settings.log_level)

    database = Database(settings.database_url)

    await database.connect()

    try:
        healthy = await database.health_check()
        if not healthy:
            raise RuntimeError("Database check failed.")
        async with database.acquire() as connection:
            rows = await connection.fetch("SELECT version FROM schema_migrations")
            applied = {str(row["version"]) for row in rows}

            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            expected = {migration_file.stem for migration_file in migration_files}
            missing_migrations = sorted(expected - applied)
            if missing_migrations:
                raise RuntimeError(
                    "Database is missing applied migrations: " + ", ".join(missing_migrations)
                )

            await _assert_table_columns(
                connection,
                "guild_settings",
                {
                    "guild_id",
                    "domme_role_id",
                    "sub_role_id",
                    "warn_log_channel_id",
                    "carlbot_user_id",
                    "report_channel_id",
                    "inactive_role_id",
                },
            )
            await _assert_table_columns(
                connection,
                "sends",
                {
                    "id",
                    "domme_user_id",
                    "sub_user_id",
                    "sub_name",
                    "amount_cents",
                    "currency",
                    "discord_post_status",
                    "is_test_send",
                    "public_send_id",
                },
            )
            await _assert_table_columns(
                connection,
                "send_requests",
                {
                    "id",
                    "guild_id",
                    "sub_user_id",
                    "domme_user_id",
                    "method",
                    "status",
                    "denial_reason",
                    "resolved_by_user_id",
                },
            )
            await _assert_table_columns(
                connection,
                "leaderboard_message",
                {
                    "guild_id",
                    "message_key",
                    "leaderboard_type",
                    "channel_id",
                    "message_id",
                },
            )

        print("Database check passed.")
    finally:
        await database.close()

if __name__ == "__main__":
    asyncio.run(main())
