from __future__ import annotations

from rob.database.connection import Database


class InactiveUsersRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def upsert_watching(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        bot_user_id: int | None = None,
    ) -> None:
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO inactive_users (
                    guild_id,
                    bot_user_id,
                    discord_user_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES ($1, $2, $3, 'watching', now(), now())
                ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                    bot_user_id = COALESCE(EXCLUDED.bot_user_id, inactive_users.bot_user_id),
                    updated_at = now()
                """,
                guild_id,
                bot_user_id,
                discord_user_id,
            )
