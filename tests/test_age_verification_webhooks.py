from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from rob.database.repositories.age_verification import STATUS_PENDING, STATUS_VERIFIED_18_PLUS
from rob.throne import webhooks as webhooks_mod

pytestmark = pytest.mark.asyncio


def _record(*, status: str = STATUS_PENDING):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        status=status,
        guild_id=1506597978251591813,
        discord_user_id=42,
        provider="yoti",
        age_threshold=18,
        yoti_session_id="sess-1",
        yoti_reference_id="rob:test:42",
        yoti_method="DOC_SCAN" if status == STATUS_VERIFIED_18_PLUS else None,
        yoti_result_summary="Yoti COMPLETE via DOC_SCAN" if status == STATUS_VERIFIED_18_PLUS else None,
        manual_review_reason=None,
        verified_at=now if status == STATUS_VERIFIED_18_PLUS else None,
        expires_at=now + timedelta(minutes=15),
        revoked_at=None,
        created_at=now,
        updated_at=now,
    )


class _FakeRepo:
    def __init__(self, record):
        self.record = record

    async def get(self, *, guild_id, discord_user_id):
        assert guild_id == self.record.guild_id
        assert discord_user_id == self.record.discord_user_id
        return self.record


class _FakeService:
    def __init__(self, record):
        self.record = record
        self.provider = SimpleNamespace(
            build_verification_url=lambda session_id: f"https://age.yoti.com?sessionId={session_id}&sdkId=sdk"
        )
        self.start_verification = AsyncMock(
            return_value=SimpleNamespace(
                status=record.status,
                verification_url="https://age.yoti.com?sessionId=sess-1&sdkId=sdk",
                expires_at=record.expires_at,
                session_id=record.yoti_session_id,
            )
        )
        self.ensure_enabled_for = lambda _guild_id: None
        self.get_status_record = AsyncMock(return_value=record)
        self.handle_notification = AsyncMock(return_value=record)
        self.refresh_session = AsyncMock(return_value=record)
        self.age_threshold = 18


def _app(*, service, repo, secret: str = "shared"):
    app = web.Application()
    app["settings"] = SimpleNamespace(
        rob_backend_secret=secret,
        rob_bot_notify_url="http://bot.local/sends/process",
        rob_ops_secret="ops-secret",
        yoti_success_url=None,
    )
    app["age_verification_service"] = service
    app["age_verification_repository"] = repo
    app.router.add_post("/age-verification/start", webhooks_mod.handle_age_verification_start)
    app.router.add_get("/age-verification/status", webhooks_mod.handle_age_verification_status)
    app.router.add_post("/yoti/notification", webhooks_mod.handle_yoti_notification)
    app.router.add_get("/yoti/callback", webhooks_mod.handle_yoti_callback)
    return app


async def test_age_verification_start_requires_backend_auth():
    record = _record()
    app = _app(service=_FakeService(record), repo=_FakeRepo(record))

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/age-verification/start",
            json={"guild_id": record.guild_id, "discord_user_id": record.discord_user_id},
        )
        body = await response.json()

    assert response.status == 403
    assert body["error"] == "forbidden"


async def test_age_verification_start_returns_pending_payload():
    record = _record()
    service = _FakeService(record)
    app = _app(service=service, repo=_FakeRepo(record))

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/age-verification/start",
            json={"guild_id": record.guild_id, "discord_user_id": record.discord_user_id},
            headers={"Authorization": "Bearer shared"},
        )
        body = await response.json()

    assert response.status == 200
    assert body["status"] == STATUS_PENDING
    assert body["verification_url"].endswith("sess-1&sdkId=sdk")
    service.start_verification.assert_awaited_once_with(
        guild_id=record.guild_id,
        discord_user_id=record.discord_user_id,
    )


async def test_age_verification_status_returns_saved_record():
    record = _record(status=STATUS_VERIFIED_18_PLUS)
    service = _FakeService(record)
    app = _app(service=service, repo=_FakeRepo(record))

    async with TestClient(TestServer(app)) as client:
        response = await client.get(
            f"/age-verification/status?guild_id={record.guild_id}&discord_user_id={record.discord_user_id}",
            headers={"Authorization": "Bearer shared"},
        )
        body = await response.json()

    assert response.status == 200
    assert body["status"] == STATUS_VERIFIED_18_PLUS
    assert body["yoti_method"] == "DOC_SCAN"


async def test_yoti_notification_notifies_bot_when_record_updates(monkeypatch):
    record = _record(status=STATUS_VERIFIED_18_PLUS)
    service = _FakeService(record)
    notify_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(webhooks_mod, "notify_bot_age_verification_sync", notify_mock)
    app = _app(service=service, repo=_FakeRepo(record))

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/yoti/notification",
            json={"session_key": "sess-1", "signature": "ignored-for-fake-service"},
        )
        body = await response.json()

    assert response.status == 200
    assert body["status"] == STATUS_VERIFIED_18_PLUS
    notify_mock.assert_awaited_once_with(
        notify_base_url="http://bot.local/sends/process",
        secret="ops-secret",
        guild_id=record.guild_id,
        discord_user_id=record.discord_user_id,
    )
