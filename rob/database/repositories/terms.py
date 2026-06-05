from __future__ import annotations

from asyncpg import Record

from rob.database.connection import Database
from rob.database.repositories.models import UserTermsAcceptance

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_DECLINED = "declined"

ALLOWED_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
)


def _build(row: Record) -> UserTermsAcceptance:
    return UserTermsAcceptance(
        discord_user_id=int(row["discord_user_id"]),
        status=str(row["status"]),
        terms_version=str(row["terms_version"]),
        dm_channel_id=int(row["dm_channel_id"]) if row["dm_channel_id"] is not None else None,
        dm_message_id=int(row["dm_message_id"]) if row["dm_message_id"] is not None else None,
        first_prompted_at=row["first_prompted_at"],
        last_prompted_at=row["last_prompted_at"],
        accepted_at=row["accepted_at"],
        declined_at=row["declined_at"],
    )


class TermsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def get(self, *, discord_user_id: int) -> UserTermsAcceptance | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM user_terms_acceptance
                WHERE discord_user_id = $1
                """,
                discord_user_id,
            )
        return _build(row) if row is not None else None

    async def upsert_pending(
        self,
        *,
        discord_user_id: int,
        terms_version: str,
        dm_channel_id: int | None = None,
        dm_message_id: int | None = None,
    ) -> UserTermsAcceptance:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO user_terms_acceptance (
                    discord_user_id,
                    status,
                    terms_version,
                    dm_channel_id,
                    dm_message_id
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (discord_user_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    terms_version = EXCLUDED.terms_version,
                    dm_channel_id = COALESCE(EXCLUDED.dm_channel_id, user_terms_acceptance.dm_channel_id),
                    dm_message_id = COALESCE(EXCLUDED.dm_message_id, user_terms_acceptance.dm_message_id),
                    last_prompted_at = now(),
                    accepted_at = NULL,
                    declined_at = NULL
                RETURNING *
                """,
                discord_user_id,
                STATUS_PENDING,
                terms_version,
                dm_channel_id,
                dm_message_id,
            )
        assert row is not None
        return _build(row)

    async def set_dm_message(
        self,
        *,
        discord_user_id: int,
        dm_channel_id: int,
        dm_message_id: int,
    ) -> UserTermsAcceptance | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE user_terms_acceptance
                SET dm_channel_id = $2,
                    dm_message_id = $3
                WHERE discord_user_id = $1
                RETURNING *
                """,
                discord_user_id,
                dm_channel_id,
                dm_message_id,
            )
        return _build(row) if row is not None else None

    async def set_status(
        self,
        *,
        discord_user_id: int,
        status: str,
    ) -> UserTermsAcceptance | None:
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Unknown terms status: {status!r}")

        accepted_at = "now()" if status == STATUS_ACCEPTED else "NULL"
        declined_at = "now()" if status == STATUS_DECLINED else "NULL"
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE user_terms_acceptance
                SET status = $2,
                    accepted_at = {accepted_at},
                    declined_at = {declined_at}
                WHERE discord_user_id = $1
                RETURNING *
                """,
                discord_user_id,
                status,
            )
        return _build(row) if row is not None else None

    async def mark_accepted(
        self,
        *,
        discord_user_id: int,
    ) -> UserTermsAcceptance | None:
        return await self.set_status(
            discord_user_id=discord_user_id,
            status=STATUS_ACCEPTED,
        )

    async def mark_declined(
        self,
        *,
        discord_user_id: int,
    ) -> UserTermsAcceptance | None:
        return await self.set_status(
            discord_user_id=discord_user_id,
            status=STATUS_DECLINED,
        )
