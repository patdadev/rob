from __future__ import annotations

import json

from asyncpg import Record

from rob.database.connection import Database
from rob.database.repositories.models import UserAchievement


def _parse_metadata(value: object) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _build_user_achievement(row: Record) -> UserAchievement:
    return UserAchievement(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]),
        discord_user_id=int(row["discord_user_id"]),
        achievement_key=str(row["achievement_key"]),
        unlocked_at=row["unlocked_at"],
        source=row["source"],
        metadata=_parse_metadata(row["metadata"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class AchievementsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def unlock(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        achievement_key: str,
        source: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO user_achievements (
                    guild_id,
                    discord_user_id,
                    achievement_key,
                    source,
                    metadata
                )
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (guild_id, discord_user_id, achievement_key)
                DO NOTHING
                RETURNING id
                """,
                guild_id,
                discord_user_id,
                achievement_key,
                source,
                json.dumps(metadata or {}),
            )
        return row is not None

    async def list_for_user(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> list[UserAchievement]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM user_achievements
                WHERE guild_id = $1
                AND discord_user_id = $2
                ORDER BY unlocked_at ASC, id ASC
                """,
                guild_id,
                discord_user_id,
            )
        return [_build_user_achievement(row) for row in rows]

    async def list_keys_for_user(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> set[str]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT achievement_key
                FROM user_achievements
                WHERE guild_id = $1
                AND discord_user_id = $2
                """,
                guild_id,
                discord_user_id,
            )
        return {str(row["achievement_key"]) for row in rows}

    async def count_for_user(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> int:
        async with self.database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM user_achievements
                WHERE guild_id = $1
                AND discord_user_id = $2
                """,
                guild_id,
                discord_user_id,
            )
        return int(value or 0)

    async def count_users_with_unlocks(
        self,
        *,
        guild_id: int,
    ) -> int:
        async with self.database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COUNT(DISTINCT discord_user_id)
                FROM user_achievements
                WHERE guild_id = $1
                """,
                guild_id,
            )
        return int(value or 0)

    async def list_unlock_counts_for_guild(
        self,
        *,
        guild_id: int,
    ) -> dict[str, int]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT achievement_key, COUNT(*) AS unlock_count
                FROM user_achievements
                WHERE guild_id = $1
                GROUP BY achievement_key
                ORDER BY unlock_count DESC, achievement_key ASC
                """,
                guild_id,
            )
        return {str(row["achievement_key"]): int(row["unlock_count"]) for row in rows}

    async def list_recent_unlocks_for_guild(
        self,
        *,
        guild_id: int,
        limit: int = 5,
    ) -> list[UserAchievement]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM user_achievements
                WHERE guild_id = $1
                ORDER BY unlocked_at DESC, id DESC
                LIMIT $2
                """,
                guild_id,
                limit,
            )
        return [_build_user_achievement(row) for row in rows]

    async def list_top_users_for_guild(
        self,
        *,
        guild_id: int,
        limit: int = 5,
    ) -> list[tuple[int, int]]:
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT discord_user_id, COUNT(*) AS unlocked_count
                FROM user_achievements
                WHERE guild_id = $1
                GROUP BY discord_user_id
                ORDER BY unlocked_count DESC, MIN(unlocked_at) ASC, discord_user_id ASC
                LIMIT $2
                """,
                guild_id,
                limit,
            )
        return [(int(row["discord_user_id"]), int(row["unlocked_count"])) for row in rows]

    async def record_event(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        achievement_key: str,
        event_type: str,
        source: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO achievement_events (
                    guild_id,
                    discord_user_id,
                    achievement_key,
                    event_type,
                    source,
                    metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                guild_id,
                discord_user_id,
                achievement_key,
                event_type,
                source,
                json.dumps(metadata or {}),
            )

    async def reset_for_guild(self, *, guild_id: int) -> dict[str, int]:
        async with self.database.acquire() as connection:
            unlocks_deleted = int(
                await connection.fetchval(
                    """
                    WITH deleted AS (
                        DELETE FROM user_achievements
                        WHERE guild_id = $1
                        RETURNING 1
                    )
                    SELECT COUNT(*)
                    FROM deleted
                    """,
                    guild_id,
                )
                or 0
            )
            events_deleted = int(
                await connection.fetchval(
                    """
                    WITH deleted AS (
                        DELETE FROM achievement_events
                        WHERE guild_id = $1
                        RETURNING 1
                    )
                    SELECT COUNT(*)
                    FROM deleted
                    """,
                    guild_id,
                )
                or 0
            )
        return {
            "guild_id": guild_id,
            "unlocks_deleted": unlocks_deleted,
            "events_deleted": events_deleted,
        }
