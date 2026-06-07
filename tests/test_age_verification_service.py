from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from rob.config.guilds import MAIN_GUILD_ID, TEST_GUILD_ID
from rob.database.repositories.age_verification import (
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_MANUAL_REVIEW_REQUIRED,
    STATUS_PENDING,
    STATUS_VERIFIED_18_PLUS,
)
from rob.services.age_verification_service import AgeVerificationService
from rob.services.yoti_age_provider import (
    AgeVerificationProviderResult,
    AgeVerificationStartResult,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record(
    *,
    guild_id: int = TEST_GUILD_ID,
    discord_user_id: int = 42,
    status: str = STATUS_PENDING,
    yoti_session_id: str | None = "sess-1",
    expires_at: datetime | None = None,
    manual_review_reason: str | None = None,
):
    current = _now()
    return SimpleNamespace(
        id=1,
        guild_id=guild_id,
        discord_user_id=discord_user_id,
        status=status,
        provider="yoti",
        age_threshold=18,
        yoti_session_id=yoti_session_id,
        yoti_reference_id="rob:test",
        yoti_method=None,
        yoti_result_summary=None,
        manual_review_reason=manual_review_reason,
        reviewed_by_user_id=None,
        verified_at=None,
        expires_at=expires_at,
        revoked_at=None,
        created_at=current,
        updated_at=current,
    )


class _FakeAgeRepo:
    def __init__(self, state=None):
        self.state = state
        self.start_calls: list[dict] = []
        self.verified_calls: list[dict] = []
        self.failed_calls: list[dict] = []
        self.manual_review_calls: list[dict] = []
        self.expired_calls: list[dict] = []
        self.approve_calls: list[dict] = []
        self.reject_calls: list[dict] = []
        self.revoke_calls: list[dict] = []

    async def get(self, *, guild_id, discord_user_id):
        if self.state is None:
            return None
        if self.state.guild_id != guild_id or self.state.discord_user_id != discord_user_id:
            return None
        return self.state

    async def get_by_yoti_session_id(self, *, session_id):
        if self.state is None or self.state.yoti_session_id != session_id:
            return None
        return self.state

    async def start_pending(self, **kwargs):
        self.start_calls.append(kwargs)
        self.state = _record(
            guild_id=kwargs["guild_id"],
            discord_user_id=kwargs["discord_user_id"],
            status=STATUS_PENDING,
            yoti_session_id=kwargs["yoti_session_id"],
            expires_at=kwargs.get("expires_at"),
        )
        return self.state

    async def mark_verified(self, **kwargs):
        self.verified_calls.append(kwargs)
        self.state = _record(
            guild_id=kwargs["guild_id"],
            discord_user_id=kwargs["discord_user_id"],
            status=STATUS_VERIFIED_18_PLUS,
            yoti_session_id=self.state.yoti_session_id if self.state else None,
            expires_at=kwargs.get("expires_at"),
        )
        self.state.yoti_method = kwargs.get("method")
        self.state.yoti_result_summary = kwargs.get("result_summary")
        self.state.verified_at = _now()
        return self.state

    async def mark_failed(self, **kwargs):
        self.failed_calls.append(kwargs)
        self.state = _record(
            guild_id=kwargs["guild_id"],
            discord_user_id=kwargs["discord_user_id"],
            status=STATUS_FAILED,
            yoti_session_id=self.state.yoti_session_id if self.state else None,
        )
        self.state.yoti_result_summary = kwargs.get("reason")
        return self.state

    async def mark_manual_review_required(self, **kwargs):
        self.manual_review_calls.append(kwargs)
        self.state = _record(
            guild_id=kwargs["guild_id"],
            discord_user_id=kwargs["discord_user_id"],
            status=STATUS_MANUAL_REVIEW_REQUIRED,
            yoti_session_id=self.state.yoti_session_id if self.state else None,
            manual_review_reason=kwargs.get("reason"),
        )
        self.state.yoti_result_summary = kwargs.get("result_summary")
        self.state.yoti_method = kwargs.get("method")
        return self.state

    async def mark_expired(self, **kwargs):
        self.expired_calls.append(kwargs)
        self.state = _record(
            guild_id=kwargs["guild_id"],
            discord_user_id=kwargs["discord_user_id"],
            status=STATUS_EXPIRED,
            yoti_session_id=self.state.yoti_session_id if self.state else None,
        )
        return self.state

    async def manual_approve(self, **kwargs):
        self.approve_calls.append(kwargs)
        self.state = _record(
            guild_id=kwargs["guild_id"],
            discord_user_id=kwargs["discord_user_id"],
            status=STATUS_VERIFIED_18_PLUS,
        )
        self.state.manual_review_reason = kwargs.get("reason")
        return self.state

    async def manual_reject(self, **kwargs):
        self.reject_calls.append(kwargs)
        self.state = _record(
            guild_id=kwargs["guild_id"],
            discord_user_id=kwargs["discord_user_id"],
            status=STATUS_FAILED,
        )
        self.state.manual_review_reason = kwargs.get("reason")
        return self.state

    async def mark_revoked(self, **kwargs):
        self.revoke_calls.append(kwargs)
        self.state = _record(
            guild_id=kwargs["guild_id"],
            discord_user_id=kwargs["discord_user_id"],
            status="revoked",
        )
        self.state.manual_review_reason = kwargs.get("reason")
        return self.state


class _FakeProvider:
    def __init__(self):
        self.create_calls: list[dict] = []
        self.verification_urls: list[str] = []

    def build_verification_url(self, session_id: str) -> str:
        url = f"https://age.yoti.com?sessionId={session_id}&sdkId=sdk"
        self.verification_urls.append(url)
        return url

    async def create_session(self, **kwargs):
        self.create_calls.append(kwargs)
        return AgeVerificationStartResult(
            session_id="sess-new",
            verification_url=self.build_verification_url("sess-new"),
            expires_at=_now() + timedelta(minutes=15),
            reference_id="rob:test:42",
        )


def _service(*, repo=None, provider=None, enabled=True, test_only=True):
    return AgeVerificationService(
        age_verifications=repo or _FakeAgeRepo(),
        enabled=enabled,
        test_only=test_only,
        age_threshold=18,
        provider=provider,
    )


def test_age_verification_service_is_test_guild_only_when_requested():
    service = _service(enabled=True, test_only=True)
    assert service.is_enabled_for(TEST_GUILD_ID) is True
    assert service.is_enabled_for(MAIN_GUILD_ID) is False


def test_start_verification_creates_pending_session():
    repo = _FakeAgeRepo()
    provider = _FakeProvider()
    service = _service(repo=repo, provider=provider)

    result = asyncio.run(
        service.start_verification(
            guild_id=TEST_GUILD_ID,
            discord_user_id=42,
        )
    )

    assert result.status == STATUS_PENDING
    assert result.session_id == "sess-new"
    assert result.verification_url.endswith("sess-new&sdkId=sdk")
    assert provider.create_calls == [{"guild_id": TEST_GUILD_ID, "discord_user_id": 42}]
    assert repo.start_calls[0]["yoti_session_id"] == "sess-new"


def test_start_verification_reuses_active_pending_session():
    record = _record(expires_at=_now() + timedelta(minutes=10))
    repo = _FakeAgeRepo(state=record)
    provider = _FakeProvider()
    service = _service(repo=repo, provider=provider)

    result = asyncio.run(
        service.start_verification(
            guild_id=TEST_GUILD_ID,
            discord_user_id=42,
        )
    )

    assert result.status == STATUS_PENDING
    assert result.session_id == "sess-1"
    assert provider.create_calls == []
    assert repo.start_calls == []


def test_get_status_record_marks_expired_pending_sessions():
    record = _record(expires_at=_now() - timedelta(minutes=1))
    repo = _FakeAgeRepo(state=record)
    service = _service(repo=repo)

    updated = asyncio.run(
        service.get_status_record(
            guild_id=TEST_GUILD_ID,
            discord_user_id=42,
        )
    )

    assert updated.status == STATUS_EXPIRED
    assert repo.expired_calls == [{"guild_id": TEST_GUILD_ID, "discord_user_id": 42}]


def test_apply_provider_result_marks_verified():
    repo = _FakeAgeRepo(state=_record())
    service = _service(repo=repo)

    updated = asyncio.run(
        service.apply_provider_result(
            AgeVerificationProviderResult(
                session_id="sess-1",
                status=STATUS_VERIFIED_18_PLUS,
                method="DOC_SCAN",
                summary="Yoti COMPLETE via DOC_SCAN",
                expires_at=_now() + timedelta(minutes=5),
            )
        )
    )

    assert updated.status == STATUS_VERIFIED_18_PLUS
    assert repo.verified_calls[0]["method"] == "DOC_SCAN"
    assert service.should_have_verified_role(updated) is True


def test_apply_provider_result_marks_manual_review_when_unclear():
    repo = _FakeAgeRepo(state=_record())
    service = _service(repo=repo)

    updated = asyncio.run(
        service.apply_provider_result(
            AgeVerificationProviderResult(
                session_id="sess-1",
                status=STATUS_MANUAL_REVIEW_REQUIRED,
                method="AGE_ESTIMATION",
                summary="Yoti ERROR via AGE_ESTIMATION",
                expires_at=None,
            )
        )
    )

    assert updated.status == STATUS_MANUAL_REVIEW_REQUIRED
    assert repo.manual_review_calls[0]["method"] == "AGE_ESTIMATION"


def test_manual_approve_and_revoke_delegate_to_repository():
    repo = _FakeAgeRepo()
    service = _service(repo=repo)

    approved = asyncio.run(
        service.manual_approve(
            guild_id=TEST_GUILD_ID,
            discord_user_id=42,
            staff_user_id=7,
            reason="Checked manually",
        )
    )
    revoked = asyncio.run(
        service.revoke(
            guild_id=TEST_GUILD_ID,
            discord_user_id=42,
            staff_user_id=7,
            reason="Testing revoke",
        )
    )

    assert approved.status == STATUS_VERIFIED_18_PLUS
    assert repo.approve_calls[0]["staff_user_id"] == 7
    assert revoked.status == "revoked"
    assert repo.revoke_calls[0]["reason"] == "Testing revoke"
