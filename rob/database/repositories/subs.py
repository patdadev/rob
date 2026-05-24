from __future__ import annotations

from datetime import datetime, timezone

from asyncpg import Record

from rob.database.connection import Database
from rob.database.repositories.models import Sub


def _build_sub(row: Record) -> Sub:
    return Sub(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]),
        discord_user_id=int(row["discord_user_id"]),
        send_name=str(row["send_name"]),
        registered_at=row["registered_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SubsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def upsert(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        send_name: str,
    ) -> Sub:
        registered_at = datetime.now(timezone.utc)
        async with self.database.transaction() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO subs (
                    guild_id,
                    discord_user_id,
                    send_name,
                    registered_at
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                    send_name = EXCLUDED.send_name,
                    updated_at = now()
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                send_name,
                registered_at,
            )
            assert row is not None
            sub = _build_sub(row)
            await connection.execute(
                """
                UPDATE sends
                SET
                    sub_id = $1,
                    sub_user_id = $2
                WHERE guild_id = $3
                AND sub_user_id IS NULL
                AND sub_name IS NOT NULL
                AND lower(sub_name) = lower($4)
                """,
                sub.id,
                sub.discord_user_id,
                guild_id,
                send_name,
            )
        return sub

    async def get_by_user_id(self, guild_id: int, discord_user_id: int) -> Sub | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM subs
                WHERE guild_id = $1
                AND discord_user_id = $2
                """,
                guild_id,
                discord_user_id,
            )
        if row is None:
            return None
        return _build_sub(row)

    async def get_by_name(self, guild_id: int, send_name: str) -> Sub | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM subs
                WHERE guild_id = $1
                AND lower(send_name) = lower($2)
                """,
                guild_id,
                send_name,
            )
        if row is None:
            return None
        return _build_sub(row)

    async def list_for_guild(self, guild_id: int) -> list[Sub]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM subs
                WHERE guild_id = $1
                ORDER BY registered_at ASC, lower(send_name) ASC
                """,
                guild_id,
            )
        return [_build_sub(row) for row in rows]

    async def count(self, guild_id: int) -> int:
        async with self.database.acquire() as connection:
            value = await connection.fetchval(
                "SELECT COUNT(*) FROM subs WHERE guild_id = $1",
                guild_id,
            )
        return int(value or 0)
