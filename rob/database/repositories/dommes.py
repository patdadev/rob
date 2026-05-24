from __future__ import annotations

from datetime import datetime, timezone

from asyncpg import Record

from rob.database.connection import Database
from rob.database.repositories.models import Domme


def _build_domme(row: Record) -> Domme:
    return Domme(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]),
        discord_user_id=int(row["discord_user_id"]),
        throne_url=str(row["throne_url"]),
        registered_at=row["registered_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class DommesRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def upsert(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        throne_url: str,
    ) -> Domme:
        registered_at = datetime.now(timezone.utc)
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO dommes (
                    guild_id,
                    discord_user_id,
                    throne_url,
                    registered_at
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                    throne_url = EXCLUDED.throne_url,
                    updated_at = now()
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                throne_url,
                registered_at,
            )
        assert row is not None
        return _build_domme(row)

    async def get_by_user_id(self, guild_id: int, discord_user_id: int) -> Domme | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM dommes
                WHERE guild_id = $1
                AND discord_user_id = $2
                """,
                guild_id,
                discord_user_id,
            )
        if row is None:
            return None
        return _build_domme(row)

    async def list_for_guild(self, guild_id: int) -> list[Domme]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM dommes
                WHERE guild_id = $1
                ORDER BY registered_at ASC, discord_user_id ASC
                """,
                guild_id,
            )
        return [_build_domme(row) for row in rows]

    async def remove_by_user_id(self, guild_id: int, discord_user_id: int) -> Domme | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                DELETE FROM dommes
                WHERE guild_id = $1
                AND discord_user_id = $2
                RETURNING *
                """,
                guild_id,
                discord_user_id,
            )
        if row is None:
            return None
        return _build_domme(row)

    async def count(self, guild_id: int) -> int:
        async with self.database.acquire() as connection:
            value = await connection.fetchval(
                "SELECT COUNT(*) FROM dommes WHERE guild_id = $1",
                guild_id,
            )
        return int(value or 0)
