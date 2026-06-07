from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from rob.config.guilds import is_test_guild
from rob.database.repositories.age_verification import (
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_MANUAL_REVIEW_REQUIRED,
    STATUS_NOT_STARTED,
    STATUS_PENDING,
    STATUS_VERIFIED_18_PLUS,
    AgeVerificationRepository,
)
from rob.database.repositories.models import AgeVerificationRecord
from rob.services.yoti_age_provider import (
    AgeVerificationProviderResult,
    AgeVerificationStartResult,
    YotiAgeProvider,
    YotiConfigurationError,
    YotiProviderError,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgeVerificationStartResponse:
    status: str
    verification_url: str | None
    expires_at: datetime | None
    session_id: str | None = None


class AgeVerificationError(RuntimeError):
    """Base error raised for age verification flow failures."""


class AgeVerificationUnavailableError(AgeVerificationError):
    """Raised when the feature is disabled or not available in a guild."""


class AgeVerificationConfigError(AgeVerificationError):
    """Raised when Yoti or backend settings are incomplete."""


class AgeVerificationService:
    def __init__(
        self,
        *,
        age_verifications: AgeVerificationRepository,
        enabled: bool,
        test_only: bool,
        age_threshold: int = 18,
        provider: YotiAgeProvider | None = None,
    ) -> None:
        self.age_verifications = age_verifications
        self.enabled = enabled
        self.test_only = test_only
        self.age_threshold = age_threshold
        self.provider = provider

    def is_enabled_for(self, guild_id: int | None) -> bool:
        if not self.enabled:
            return False
        if self.test_only:
            return is_test_guild(guild_id)
        return guild_id is not None

    def ensure_enabled_for(self, guild_id: int | None) -> None:
        if self.is_enabled_for(guild_id):
            return
        raise AgeVerificationUnavailableError(
            "Age verification is only available in the test guild right now."
        )

    async def get_status_record(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AgeVerificationRecord | None:
        record = await self.age_verifications.get(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        if (
            record is not None
            and record.status == STATUS_PENDING
            and record.expires_at is not None
            and record.expires_at <= datetime.now(timezone.utc)
        ):
            expired = await self.age_verifications.mark_expired(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
            )
            return expired or record
        return record

    async def get_status(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> str:
        record = await self.get_status_record(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        if record is None:
            return STATUS_NOT_STARTED
        return record.status

    async def start_verification(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AgeVerificationStartResponse:
        self.ensure_enabled_for(guild_id)
        current = await self.get_status_record(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        if current is not None and current.status == STATUS_VERIFIED_18_PLUS:
            return AgeVerificationStartResponse(
                status=current.status,
                verification_url=None,
                expires_at=current.expires_at,
                session_id=current.yoti_session_id,
            )

        if (
            current is not None
            and current.status == STATUS_PENDING
            and current.yoti_session_id
            and self.provider is not None
        ):
            return AgeVerificationStartResponse(
                status=current.status,
                verification_url=self.provider.build_verification_url(
                    current.yoti_session_id
                ),
                expires_at=current.expires_at,
                session_id=current.yoti_session_id,
            )

        start_result = await self._create_provider_session(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        await self.age_verifications.start_pending(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            age_threshold=self.age_threshold,
            yoti_session_id=start_result.session_id,
            yoti_reference_id=start_result.reference_id,
            expires_at=start_result.expires_at,
        )
        return AgeVerificationStartResponse(
            status=STATUS_PENDING,
            verification_url=start_result.verification_url,
            expires_at=start_result.expires_at,
            session_id=start_result.session_id,
        )

    async def refresh_session(
        self,
        *,
        session_id: str,
    ) -> AgeVerificationRecord | None:
        provider = self._require_provider()
        try:
            result = await provider.get_result(session_id)
        except YotiConfigurationError as exc:
            raise AgeVerificationConfigError(str(exc)) from exc
        except YotiProviderError as exc:
            raise AgeVerificationError(str(exc)) from exc
        return await self.apply_provider_result(result)

    async def handle_notification(
        self,
        payload: dict,
    ) -> AgeVerificationRecord | None:
        provider = self._require_provider()
        try:
            result = await provider.handle_notification(payload)
        except YotiConfigurationError as exc:
            raise AgeVerificationConfigError(str(exc)) from exc
        except YotiProviderError as exc:
            raise AgeVerificationError(str(exc)) from exc
        return await self.apply_provider_result(result)

    async def apply_provider_result(
        self,
        result: AgeVerificationProviderResult,
    ) -> AgeVerificationRecord | None:
        record = await self.age_verifications.get_by_yoti_session_id(
            session_id=result.session_id
        )
        if record is None:
            log.info(
                "Ignoring Yoti result for unknown or superseded session_id=%s status=%s",
                result.session_id,
                result.status,
            )
            return None

        if result.status == STATUS_VERIFIED_18_PLUS:
            return await self.age_verifications.mark_verified(
                guild_id=record.guild_id,
                discord_user_id=record.discord_user_id,
                method=result.method,
                result_summary=result.summary,
                expires_at=result.expires_at,
            )
        if result.status == STATUS_FAILED:
            return await self.age_verifications.mark_failed(
                guild_id=record.guild_id,
                discord_user_id=record.discord_user_id,
                reason=result.summary,
            )
        if result.status == STATUS_MANUAL_REVIEW_REQUIRED:
            return await self.age_verifications.mark_manual_review_required(
                guild_id=record.guild_id,
                discord_user_id=record.discord_user_id,
                reason=result.summary,
                method=result.method,
                result_summary=result.summary,
            )
        if result.status == STATUS_EXPIRED:
            return await self.age_verifications.mark_expired(
                guild_id=record.guild_id,
                discord_user_id=record.discord_user_id,
            )
        return record

    async def manual_approve(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        staff_user_id: int | None = None,
        reason: str | None = None,
    ) -> AgeVerificationRecord:
        self.ensure_enabled_for(guild_id)
        return await self.age_verifications.manual_approve(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            age_threshold=self.age_threshold,
            staff_user_id=staff_user_id,
            reason=reason,
        )

    async def manual_reject(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        staff_user_id: int | None = None,
        reason: str | None = None,
    ) -> AgeVerificationRecord:
        self.ensure_enabled_for(guild_id)
        return await self.age_verifications.manual_reject(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            age_threshold=self.age_threshold,
            staff_user_id=staff_user_id,
            reason=reason,
        )

    async def revoke(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        staff_user_id: int | None = None,
        reason: str | None = None,
    ) -> AgeVerificationRecord:
        self.ensure_enabled_for(guild_id)
        return await self.age_verifications.mark_revoked(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            reason=reason,
            staff_user_id=staff_user_id,
        )

    @staticmethod
    def should_have_verified_role(record: AgeVerificationRecord | None) -> bool:
        if record is None:
            return False
        return record.status == STATUS_VERIFIED_18_PLUS

    async def _create_provider_session(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AgeVerificationStartResult:
        provider = self._require_provider()
        try:
            return await provider.create_session(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
            )
        except YotiConfigurationError as exc:
            raise AgeVerificationConfigError(str(exc)) from exc
        except YotiProviderError as exc:
            raise AgeVerificationError(str(exc)) from exc

    def _require_provider(self) -> YotiAgeProvider:
        if self.provider is None:
            raise AgeVerificationConfigError(
                "Age verification provider is not configured."
            )
        return self.provider
