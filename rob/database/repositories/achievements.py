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
