from __future__ import annotations

from asyncpg import Record

from rob.database.connection import Database
from rob.database.repositories.models import AgeVerificationRecord

STATUS_NOT_STARTED = "not_started"
STATUS_PENDING = "pending"
STATUS_VERIFIED_18_PLUS = "verified_18_plus"
STATUS_FAILED = "failed"
STATUS_MANUAL_REVIEW_REQUIRED = "manual_review_required"
STATUS_EXPIRED = "expired"
STATUS_REVOKED = "revoked"

ALLOWED_STATUSES: tuple[str, ...] = (
    STATUS_NOT_STARTED,
    STATUS_PENDING,
    STATUS_VERIFIED_18_PLUS,
    STATUS_FAILED,
    STATUS_MANUAL_REVIEW_REQUIRED,
    STATUS_EXPIRED,
    STATUS_REVOKED,
)


def _build(row: Record) -> AgeVerificationRecord:
    return AgeVerificationRecord(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]),
        discord_user_id=int(row["discord_user_id"]),
        status=str(row["status"]),
        provider=str(row["provider"]),
        age_threshold=int(row["age_threshold"]),
        yoti_session_id=str(row["yoti_session_id"]) if row["yoti_session_id"] is not None else None,
        yoti_reference_id=str(row["yoti_reference_id"]) if row["yoti_reference_id"] is not None else None,
        yoti_method=str(row["yoti_method"]) if row["yoti_method"] is not None else None,
        yoti_result_summary=(
            str(row["yoti_result_summary"])
            if row["yoti_result_summary"] is not None
            else None
        ),
        manual_review_reason=(
            str(row["manual_review_reason"])
            if row["manual_review_reason"] is not None
            else None
        ),
        reviewed_by_user_id=(
            int(row["reviewed_by_user_id"])
            if row["reviewed_by_user_id"] is not None
            else None
        ),
        verified_at=row["verified_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class AgeVerificationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def get(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AgeVerificationRecord | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM age_verifications
                WHERE guild_id = $1
                  AND discord_user_id = $2
                """,
                guild_id,
                discord_user_id,
            )
        return _build(row) if row is not None else None

    async def get_by_yoti_session_id(
        self,
        *,
        session_id: str,
    ) -> AgeVerificationRecord | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM age_verifications
                WHERE yoti_session_id = $1
                """,
                session_id,
            )
        return _build(row) if row is not None else None

    async def start_pending(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        age_threshold: int,
        yoti_session_id: str,
        yoti_reference_id: str | None = None,
        expires_at=None,
    ) -> AgeVerificationRecord:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO age_verifications (
                    guild_id,
                    discord_user_id,
                    status,
                    provider,
                    age_threshold,
                    yoti_session_id,
                    yoti_reference_id,
                    expires_at,
                    yoti_method,
                    yoti_result_summary,
                    manual_review_reason,
                    reviewed_by_user_id,
                    verified_at,
                    revoked_at
                )
                VALUES ($1, $2, $3, 'yoti', $4, $5, $6, $7, NULL, NULL, NULL, NULL, NULL, NULL)
                ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    provider = EXCLUDED.provider,
                    age_threshold = EXCLUDED.age_threshold,
                    yoti_session_id = EXCLUDED.yoti_session_id,
                    yoti_reference_id = EXCLUDED.yoti_reference_id,
                    expires_at = EXCLUDED.expires_at,
                    yoti_method = NULL,
                    yoti_result_summary = NULL,
                    manual_review_reason = NULL,
                    reviewed_by_user_id = NULL,
                    verified_at = NULL,
                    revoked_at = NULL,
                    updated_at = now()
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                STATUS_PENDING,
                age_threshold,
                yoti_session_id,
                yoti_reference_id,
                expires_at,
            )
        assert row is not None
        return _build(row)

    async def mark_verified(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        method: str | None = None,
        result_summary: str | None = None,
        expires_at=None,
    ) -> AgeVerificationRecord | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE age_verifications
                SET status = $3,
                    yoti_method = COALESCE($4, yoti_method),
                    yoti_result_summary = $5,
                    manual_review_reason = NULL,
                    reviewed_by_user_id = NULL,
                    verified_at = now(),
                    expires_at = COALESCE($6, expires_at),
                    revoked_at = NULL,
                    updated_at = now()
                WHERE guild_id = $1
                  AND discord_user_id = $2
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                STATUS_VERIFIED_18_PLUS,
                method,
                result_summary,
                expires_at,
            )
        return _build(row) if row is not None else None

    async def mark_failed(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        reason: str | None = None,
    ) -> AgeVerificationRecord | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE age_verifications
                SET status = $3,
                    yoti_result_summary = $4,
                    manual_review_reason = NULL,
                    reviewed_by_user_id = NULL,
                    verified_at = NULL,
                    revoked_at = NULL,
                    updated_at = now()
                WHERE guild_id = $1
                  AND discord_user_id = $2
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                STATUS_FAILED,
                reason,
            )
        return _build(row) if row is not None else None

    async def mark_manual_review_required(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        reason: str | None = None,
        method: str | None = None,
        result_summary: str | None = None,
    ) -> AgeVerificationRecord | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE age_verifications
                SET status = $3,
                    yoti_method = COALESCE($4, yoti_method),
                    yoti_result_summary = COALESCE($5, yoti_result_summary),
                    manual_review_reason = $6,
                    reviewed_by_user_id = NULL,
                    verified_at = NULL,
                    revoked_at = NULL,
                    updated_at = now()
                WHERE guild_id = $1
                  AND discord_user_id = $2
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                STATUS_MANUAL_REVIEW_REQUIRED,
                method,
                result_summary,
                reason,
            )
        return _build(row) if row is not None else None

    async def mark_expired(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AgeVerificationRecord | None:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE age_verifications
                SET status = $3,
                    yoti_result_summary = 'Yoti session expired.',
                    manual_review_reason = NULL,
                    reviewed_by_user_id = NULL,
                    verified_at = NULL,
                    revoked_at = NULL,
                    updated_at = now()
                WHERE guild_id = $1
                  AND discord_user_id = $2
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                STATUS_EXPIRED,
            )
        return _build(row) if row is not None else None

    async def mark_revoked(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        reason: str | None = None,
        staff_user_id: int | None = None,
    ) -> AgeVerificationRecord:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO age_verifications (
                    guild_id,
                    discord_user_id,
                    status,
                    provider,
                    age_threshold,
                    manual_review_reason,
                    reviewed_by_user_id,
                    revoked_at
                )
                VALUES ($1, $2, $3, 'yoti', 18, $4, $5, now())
                ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    provider = EXCLUDED.provider,
                    manual_review_reason = EXCLUDED.manual_review_reason,
                    reviewed_by_user_id = EXCLUDED.reviewed_by_user_id,
                    verified_at = NULL,
                    revoked_at = now(),
                    updated_at = now()
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                STATUS_REVOKED,
                reason,
                staff_user_id,
            )
        assert row is not None
        return _build(row)

    async def manual_approve(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        age_threshold: int,
        staff_user_id: int | None = None,
        reason: str | None = None,
    ) -> AgeVerificationRecord:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO age_verifications (
                    guild_id,
                    discord_user_id,
                    status,
                    provider,
                    age_threshold,
                    yoti_result_summary,
                    manual_review_reason,
                    reviewed_by_user_id,
                    verified_at
                )
                VALUES ($1, $2, $3, 'yoti', $4, 'Manually approved by staff.', $5, $6, now())
                ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    provider = EXCLUDED.provider,
                    age_threshold = EXCLUDED.age_threshold,
                    yoti_result_summary = EXCLUDED.yoti_result_summary,
                    manual_review_reason = EXCLUDED.manual_review_reason,
                    reviewed_by_user_id = EXCLUDED.reviewed_by_user_id,
                    verified_at = now(),
                    revoked_at = NULL,
                    updated_at = now()
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                STATUS_VERIFIED_18_PLUS,
                age_threshold,
                reason,
                staff_user_id,
            )
        assert row is not None
        return _build(row)

    async def manual_reject(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        age_threshold: int,
        staff_user_id: int | None = None,
        reason: str | None = None,
    ) -> AgeVerificationRecord:
        async with self.database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO age_verifications (
                    guild_id,
                    discord_user_id,
                    status,
                    provider,
                    age_threshold,
                    yoti_result_summary,
                    manual_review_reason,
                    reviewed_by_user_id,
                    verified_at,
                    revoked_at
                )
                VALUES ($1, $2, $3, 'yoti', $4, 'Manually rejected by staff.', $5, $6, NULL, NULL)
                ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    provider = EXCLUDED.provider,
                    age_threshold = EXCLUDED.age_threshold,
                    yoti_result_summary = EXCLUDED.yoti_result_summary,
                    manual_review_reason = EXCLUDED.manual_review_reason,
                    reviewed_by_user_id = EXCLUDED.reviewed_by_user_id,
                    verified_at = NULL,
                    revoked_at = NULL,
                    updated_at = now()
                RETURNING *
                """,
                guild_id,
                discord_user_id,
                STATUS_FAILED,
                age_threshold,
                reason,
                staff_user_id,
            )
        assert row is not None
        return _build(row)
