from __future__ import annotations

from asyncpg import Record

from rob.database.connection import Database
from rob.database.repositories.models import GuildSettings


def _build_guild_settings(row: Record) -> GuildSettings:
    return GuildSettings(
        guild_id=int(row["guild_id"]),
        registration_channel_id=row["registration_channel_id"],
        leaderboard_channel_id=row["leaderboard_channel_id"],
        send_track_channel_id=row["send_track_channel_id"],
        counting_channel_id=row["counting_channel_id"],
        report_channel_id=row["report_channel_id"] if "report_channel_id" in row else None,
        domme_role_id=row["domme_role_id"],
        sub_role_id=row["sub_role_id"],
        mod_role_id=row["mod_role_id"],
        inactive_role_id=row["inactive_role_id"] if "inactive_role_id" in row else None,
        warn_log_channel_id=row["warn_log_channel_id"],
        carlbot_user_id=row["carlbot_user_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class GuildSettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def ensure_guild(self, guild_id: int) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO guild_settings (guild_id)
                VALUES ($1)
                ON CONFLICT (guild_id) DO NOTHING
                """,
                guild_id,
            )

    async def get(self, guild_id: int) -> GuildSettings | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM guild_settings WHERE guild_id = $1",
                guild_id,
            )
        if row is None:
            return None
        return _build_guild_settings(row)

    async def list_guild_ids(self) -> list[int]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                "SELECT guild_id FROM guild_settings ORDER BY guild_id ASC"
            )
        return [int(row["guild_id"]) for row in rows]
