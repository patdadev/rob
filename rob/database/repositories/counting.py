from __future__ import annotations

from asyncpg import Record

from rob.database.connection import Database
from rob.database.repositories.models import CountingState


def _build_counting_state(row: Record) -> CountingState:
    return CountingState(
        guild_id=int(row["guild_id"]),
        channel_id=row["channel_id"],
        current_number=int(row["current_number"]),
        last_user_id=row["last_user_id"],
        is_enabled=bool(row["is_enabled"]),
        pending_restore=bool(row["pending_restore"]),
        updated_at=row["updated_at"],
    )


class CountingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def get(self, guild_id: int) -> CountingState | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM the_count WHERE guild_id = $1",
                guild_id,
            )
        if row is None:
            return None
        return _build_counting_state(row)

    async def upsert(
        self,
        *,
        guild_id: int,
        channel_id: int | None,
        current_number: int,
        last_user_id: int | None,
        is_enabled: bool,
        pending_restore: bool,
    ) -> CountingState:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO the_count (
                    guild_id,
                    channel_id,
                    current_number,
                    last_user_id,
                    is_enabled,
                    pending_restore
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (guild_id) DO UPDATE SET
                    channel_id = EXCLUDED.channel_id,
                    current_number = EXCLUDED.current_number,
                    last_user_id = EXCLUDED.last_user_id,
                    is_enabled = EXCLUDED.is_enabled,
                    pending_restore = EXCLUDED.pending_restore,
                    updated_at = now()
                RETURNING *
                """,
                guild_id,
                channel_id,
                current_number,
                last_user_id,
                is_enabled,
                pending_restore,
            )
        assert row is not None
        return _build_counting_state(row)


# Backward-compat alias while services transition to v2 naming.
TheCountRepository = CountingRepository
