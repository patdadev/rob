from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import discord
from rob.services.bot_ops_server import BotOpsServer


class _FakeRequest:
    def __init__(
        self,
        *,
        payload: dict | None = None,
        form_payload: dict | None = None,
        headers: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
    ):
        self._payload = payload or {}
        self._form_payload = form_payload or {}
        self.headers = headers or {}
        self.query = query or {}
        self.match_info: dict[str, str] = {}

    async def json(self):
        if self._payload == "__error__":
            raise ValueError("json parse failed")
        return self._payload

    async def post(self):
        return _FakeForm(self._form_payload)


class _FakeForm(dict):
    def getall(self, key):
        value = self[key]
        if isinstance(value, list):
            return value
        return [value]


class _FakeSendQueue:
    def __init__(self):
        self.notified: list[int] = []

    async def notify_send(self, send_id: int) -> None:
        self.notified.append(send_id)


class _FakeRegistrationService:
    def __init__(self):
        self.calls: list[dict] = []

    async def register_sub(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(sub=SimpleNamespace(id=7, discord_user_id=kwargs["discord_user_id"]), send_names=tuple(kwargs["send_names"]))


class _FakeSendChangeRequestService:
    def __init__(self):
        self.calls: list[dict] = []

    async def create_send_add_request(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id=11,
            action="send_add",
            status="pending",
            domme_user_id=555,
        )


class _FakeVibSettingsRepo:
    def __init__(self):
        self.channel_calls: list[tuple[int, str, int | None]] = []
        self.role_calls: list[tuple[int, str, int | None]] = []
        self.settings = SimpleNamespace(
            guild_id=99,
            registration_channel_id=None,
            leaderboard_channel_id=22,
            send_track_channel_id=None,
            counting_channel_id=None,
            report_channel_id=None,
            warn_log_channel_id=None,
            domme_role_id=None,
            sub_role_id=None,
            mod_role_id=77,
            inactive_role_id=None,
        )

    async def get(self, guild_id: int):
        assert guild_id == 99
        return self.settings

    async def set_channel_id(self, guild_id: int, field_name: str, channel_id: int | None):
        self.channel_calls.append((guild_id, field_name, channel_id))
        setattr(self.settings, field_name, channel_id)
        return self.settings

    async def set_role_id(self, guild_id: int, field_name: str, role_id: int | None):
        self.role_calls.append((guild_id, field_name, role_id))
        setattr(self.settings, field_name, role_id)
        return self.settings


class _FakeAchievementsRepo:
    def __init__(self):
        self.guild_ids: list[int] = []

    async def reset_for_guild(self, *, guild_id: int):
        self.guild_ids.append(guild_id)
        return {"guild_id": guild_id, "unlocks_deleted": 4, "events_deleted": 9}


def _make_fake_guild():
    leaderboard = MagicMock(spec=discord.TextChannel)
    leaderboard.id = 22
    leaderboard.name = "leaderboard"

    send_tracker = MagicMock(spec=discord.TextChannel)
    send_tracker.id = 33
    send_tracker.name = "send-tracker"

    counting = MagicMock(spec=discord.TextChannel)
    counting.id = 44
    counting.name = "counting"

    return SimpleNamespace(
        id=99,
        name="Rob Test Server",
        channels=[leaderboard, send_tracker, counting],
        roles=[
            SimpleNamespace(id=77, name="Moderator"),
            SimpleNamespace(id=88, name="Dom/me"),
            SimpleNamespace(id=99, name="Sub"),
            SimpleNamespace(id=1, name="@everyone"),
        ],
    )


def test_bot_ops_process_send_endpoint_enqueues_specific_send():
    send_queue = _FakeSendQueue()
    bot = SimpleNamespace(send_queue_service=send_queue, user=SimpleNamespace(id=123))
    server = BotOpsServer(bot=bot, host="127.0.0.1", port=8811, secret="shared")
    request = _FakeRequest(
        payload={"send_id": 42, "guild_id": 99},
        headers={"X-Rob-Ops-Secret": "shared"},
    )

    response = asyncio.run(server._handle_process_send(request))

    assert response.status == 200
    assert send_queue.notified == [42]
    body = json.loads(response.text)
    assert body == {"ok": True, "queued": True, "send_id": 42, "guild_id": 99}


def test_bot_ops_process_send_endpoint_requires_secret():
    send_queue = _FakeSendQueue()
    bot = SimpleNamespace(send_queue_service=send_queue, user=SimpleNamespace(id=123))
    server = BotOpsServer(bot=bot, host="127.0.0.1", port=8811, secret="shared")
    request = _FakeRequest(payload={"send_id": 42}, headers={})

    response = asyncio.run(server._handle_process_send(request))

    assert response.status == 403
    assert send_queue.notified == []


def test_bot_ops_add_sub_accepts_form_payload_send_names_string():
    registration_service = _FakeRegistrationService()
    bot = SimpleNamespace(
        registration_service=registration_service,
        user=SimpleNamespace(id=123),
    )
    server = BotOpsServer(bot=bot, host="127.0.0.1", port=8811, secret="shared")
    request = _FakeRequest(
        payload="__error__",
        form_payload={
            "discord_user_id": "42",
            "send_names": "alpha, beta, gamma",
        },
        headers={"X-Rob-Ops-Secret": "shared"},
    )
    request.match_info["guild_id"] = "99"

    response = asyncio.run(server._handle_add_sub(request))

    assert response.status == 200
    assert registration_service.calls == [
        {
            "guild_id": 99,
            "discord_user_id": 42,
            "send_names": ["alpha", "beta", "gamma"],
        }
    ]


def test_bot_ops_send_add_request_endpoint_uses_approval_service():
    approval_service = _FakeSendChangeRequestService()
    bot = SimpleNamespace(
        send_change_request_service=approval_service,
        user=SimpleNamespace(id=123),
    )
    server = BotOpsServer(bot=bot, host="127.0.0.1", port=8811, secret="shared")
    request = _FakeRequest(
        payload={
            "domme_lookup": "missadore",
            "amount": "25.50",
            "sub_name": "pat",
            "requested_by": "rob@test",
        },
        headers={"X-Rob-Ops-Secret": "shared"},
    )
    request.match_info["guild_id"] = "99"

    response = asyncio.run(server._handle_request_send_add(request))

    assert response.status == 200
    assert approval_service.calls == [
        {
            "guild_id": 99,
            "domme_lookup": "missadore",
            "amount_cents": 2550,
            "sub_name": "pat",
            "requested_by": "rob@test",
            "currency": "USD",
            "method": "manual",
            "note": None,
        }
    ]


def test_bot_ops_guild_scan_returns_suggestions():
    vib_settings_repo = _FakeVibSettingsRepo()
    guild = _make_fake_guild()
    bot = SimpleNamespace(
        get_guild=lambda guild_id: guild if guild_id == 99 else None,
        vib_settings_repo=vib_settings_repo,
        user=SimpleNamespace(id=123),
    )
    server = BotOpsServer(bot=bot, host="127.0.0.1", port=8811, secret="shared")
    request = _FakeRequest(headers={"X-Rob-Ops-Secret": "shared"})
    request.match_info["guild_id"] = "99"

    response = asyncio.run(server._handle_guild_scan(request))

    assert response.status == 200
    body = json.loads(response.text)
    send_tracker_entry = next(
        entry for entry in body["channel_matches"] if entry["field"] == "send_track_channel_id"
    )
    domme_role_entry = next(
        entry for entry in body["role_matches"] if entry["field"] == "domme_role_id"
    )
    assert send_tracker_entry["suggested"]["id"] == 33
    assert send_tracker_entry["current"]["id"] is None
    assert domme_role_entry["suggested"]["id"] == 88


def test_bot_ops_guild_auto_apply_updates_selected_suggestions():
    vib_settings_repo = _FakeVibSettingsRepo()
    guild = _make_fake_guild()
    bot = SimpleNamespace(
        get_guild=lambda guild_id: guild if guild_id == 99 else None,
        vib_settings_repo=vib_settings_repo,
        user=SimpleNamespace(id=123),
    )
    server = BotOpsServer(bot=bot, host="127.0.0.1", port=8811, secret="shared")
    request = _FakeRequest(
        payload={"options": "send_track_channel_id,domme_role_id"},
        headers={"X-Rob-Ops-Secret": "shared"},
    )
    request.match_info["guild_id"] = "99"

    response = asyncio.run(server._handle_apply_guild_scan(request))

    assert response.status == 200
    assert vib_settings_repo.channel_calls == [(99, "send_track_channel_id", 33)]
    assert vib_settings_repo.role_calls == [(99, "domme_role_id", 88)]
    body = json.loads(response.text)
    assert [entry["field"] for entry in body["applied"]] == [
        "send_track_channel_id",
        "domme_role_id",
    ]


def test_bot_ops_guild_achievement_reset_endpoint_returns_deleted_counts():
    achievements_repo = _FakeAchievementsRepo()
    bot = SimpleNamespace(
        achievements_repo=achievements_repo,
        user=SimpleNamespace(id=123),
    )
    server = BotOpsServer(bot=bot, host="127.0.0.1", port=8811, secret="shared")
    request = _FakeRequest(headers={"X-Rob-Ops-Secret": "shared"})
    request.match_info["guild_id"] = "99"

    response = asyncio.run(server._handle_reset_guild_achievements(request))

    assert response.status == 200
    assert achievements_repo.guild_ids == [99]
    body = json.loads(response.text)
    assert body["unlocks_deleted"] == 4
    assert body["events_deleted"] == 9
