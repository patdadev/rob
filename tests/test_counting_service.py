from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from rob.services.counting_service import CountingService


@dataclass
class _State:
    guild_id: int
    channel_id: int | None
    current_number: int
    last_user_id: int | None
    is_enabled: bool
    pending_restore: bool


class _FakeCountingRepo:
    def __init__(self):
        self.state = _State(
            guild_id=1,
            channel_id=100,
            current_number=0,
            last_user_id=None,
            is_enabled=True,
            pending_restore=False,
        )

    async def get(self, guild_id: int):
        if guild_id != self.state.guild_id:
            return None
        return self.state

    async def upsert(self, **kwargs):
        self.state = _State(
            guild_id=kwargs["guild_id"],
            channel_id=kwargs["channel_id"],
            current_number=kwargs["current_number"],
            last_user_id=kwargs["last_user_id"],
            is_enabled=kwargs["is_enabled"],
            pending_restore=kwargs["pending_restore"],
        )
        return self.state


class _FakeGuildSettingsRepo:
    async def get(self, _guild_id: int):
        return SimpleNamespace(counting_channel_id=100, sub_role_id=22)


class _FakeDommesRepo:
    async def get_by_user_id(self, _guild_id: int, _domme_user_id: int):
        return SimpleNamespace(id=1)


class _FakeMessage:
    def __init__(self):
        self.edits: list[dict] = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class _FakeChannel:
    def __init__(self):
        self.id = 100
        self.sent: list[dict] = []
        self.messages: list[_FakeMessage] = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        message = _FakeMessage()
        self.messages.append(message)
        return message


class _FakeMember:
    def __init__(self, user_id: int, role_ids: list[int]):
        self.id = user_id
        self.bot = False
        self.roles = [SimpleNamespace(id=role_id) for role_id in role_ids]


class _FakeMessageEvent:
    def __init__(self, *, author, content: str, channel: _FakeChannel):
        self.guild = SimpleNamespace(id=1)
        self.author = author
        self.content = content
        self.channel = channel
        self.attachments = []
        self.stickers = []


class _FakeAchievements:
    def __init__(self):
        self.unlock_calls: list[str] = []
        self.unlock_many_calls: list[list[str]] = []

    async def unlock_achievement(self, *, achievement_key: str, **_kwargs):
        self.unlock_calls.append(achievement_key)
        return True

    async def unlock_many(self, *, achievement_keys, **_kwargs):
        self.unlock_many_calls.append(list(achievement_keys))
        return list(achievement_keys)


def _service(
    *,
    counting_repo: _FakeCountingRepo,
    tick_seconds: int = 15,
    rescue_seconds: int = 300,
    achievements: _FakeAchievements | None = None,
):
    return CountingService(
        bot=SimpleNamespace(),
        counting=counting_repo,
        guild_settings=_FakeGuildSettingsRepo(),
        dommes=_FakeDommesRepo(),
        achievements=achievements,
        rescue_tick_seconds=tick_seconds,
        rescue_window_seconds=rescue_seconds,
        parse_test_sends_as_real_sends=False,
        test_gifter_usernames=("marie_123",),
    )


def test_same_user_double_count_does_not_reset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.services.counting_service.discord.Member", _FakeMember)
    repo = _FakeCountingRepo()
    repo.state.current_number = 7
    repo.state.last_user_id = 10
    channel = _FakeChannel()
    service = _service(counting_repo=repo)
    message = _FakeMessageEvent(author=_FakeMember(10, [22]), content="8", channel=channel)

    result = asyncio.run(service.process_message(message))

    assert result is not None
    assert result.reason == "same_user"
    assert repo.state.current_number == 7
    assert repo.state.pending_restore is False


def test_wrong_sub_number_starts_rescue_and_valid_send_restores(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.services.counting_service.discord.Member", _FakeMember)
    repo = _FakeCountingRepo()
    repo.state.current_number = 7
    repo.state.last_user_id = 9
    channel = _FakeChannel()
    service = _service(counting_repo=repo, tick_seconds=1, rescue_seconds=60)
    message = _FakeMessageEvent(author=_FakeMember(10, [22]), content="99", channel=channel)

    result = asyncio.run(service.process_message(message))
    assert result is not None
    assert result.reason == "wrong_number_sub_rescue"
    assert repo.state.pending_restore is True
    assert len(channel.sent) == 1

    send = SimpleNamespace(
        guild_id=1,
        domme_user_id=20,
        sub_user_id=10,
        sub_name="real",
        source="manual:paypal",
        is_private=False,
        is_test_send=False,
    )
    restored = asyncio.run(service.process_send_for_count_rescue(send))
    assert restored is True
    assert repo.state.pending_restore is False
    assert repo.state.current_number == 7


def test_send_request_send_can_rescue_when_sub_user_is_known(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.services.counting_service.discord.Member", _FakeMember)
    repo = _FakeCountingRepo()
    repo.state.current_number = 12
    repo.state.last_user_id = 9
    channel = _FakeChannel()
    service = _service(counting_repo=repo, tick_seconds=1, rescue_seconds=60)
    message = _FakeMessageEvent(author=_FakeMember(10, [22]), content="99", channel=channel)

    start = asyncio.run(service.process_message(message))
    assert start is not None
    assert start.reason == "wrong_number_sub_rescue"
    assert repo.state.pending_restore is True

    send = SimpleNamespace(
        guild_id=1,
        domme_user_id=20,
        sub_user_id=10,
        sub_name=None,
        source="send_request",
        is_private=False,
        is_test_send=False,
    )
    restored = asyncio.run(service.process_send_for_count_rescue(send))
    assert restored is True
    assert repo.state.pending_restore is False
    assert repo.state.current_number == 12


def test_test_send_does_not_rescue(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.services.counting_service.discord.Member", _FakeMember)
    repo = _FakeCountingRepo()
    repo.state.current_number = 7
    repo.state.last_user_id = 9
    channel = _FakeChannel()
    service = _service(counting_repo=repo, tick_seconds=1, rescue_seconds=60)
    message = _FakeMessageEvent(author=_FakeMember(10, [22]), content="99", channel=channel)
    asyncio.run(service.process_message(message))

    send = SimpleNamespace(
        guild_id=1,
        domme_user_id=20,
        sub_user_id=10,
        sub_name="marie_123",
        is_private=False,
        is_test_send=True,
    )
    restored = asyncio.run(service.process_send_for_count_rescue(send))
    assert restored is False
    assert repo.state.pending_restore is True
    asyncio.run(service._clear_rescue_window(1))


def test_rescue_window_expiry_resets_count(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.services.counting_service.discord.Member", _FakeMember)
    repo = _FakeCountingRepo()
    repo.state.current_number = 7
    repo.state.last_user_id = 9
    channel = _FakeChannel()
    service = _service(counting_repo=repo, tick_seconds=1, rescue_seconds=1)
    message = _FakeMessageEvent(author=_FakeMember(10, [22]), content="99", channel=channel)
    asyncio.run(service.process_message(message))

    async def _wait():
        await asyncio.sleep(1.3)

    asyncio.run(_wait())
    assert repo.state.current_number == 0
    assert repo.state.pending_restore is False


def test_count_milestone_unlocks_achievement(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.services.counting_service.discord.Member", _FakeMember)
    repo = _FakeCountingRepo()
    repo.state.current_number = 9
    channel = _FakeChannel()
    achievements = _FakeAchievements()
    service = _service(counting_repo=repo, achievements=achievements)
    message = _FakeMessageEvent(author=_FakeMember(10, [22]), content="10", channel=channel)

    result = asyncio.run(service.process_message(message))

    assert result is not None and result.success is True
    assert "count_10" in achievements.unlock_calls


def test_wrong_number_unlocks_first_mistake(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.services.counting_service.discord.Member", _FakeMember)
    repo = _FakeCountingRepo()
    repo.state.current_number = 4
    repo.state.last_user_id = 9
    channel = _FakeChannel()
    achievements = _FakeAchievements()
    service = _service(counting_repo=repo, achievements=achievements)
    message = _FakeMessageEvent(author=_FakeMember(10, [22]), content="6", channel=channel)

    result = asyncio.run(service.process_message(message))

    assert result is not None and result.success is False
    assert "count_first_mistake" in achievements.unlock_calls


def test_rescue_unlocks_sub_save_count_achievement(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.services.counting_service.discord.Member", _FakeMember)
    repo = _FakeCountingRepo()
    repo.state.current_number = 7
    repo.state.last_user_id = 9
    channel = _FakeChannel()
    achievements = _FakeAchievements()
    service = _service(counting_repo=repo, tick_seconds=1, rescue_seconds=60, achievements=achievements)
    message = _FakeMessageEvent(author=_FakeMember(10, [22]), content="99", channel=channel)
    asyncio.run(service.process_message(message))

    send = SimpleNamespace(
        guild_id=1,
        domme_user_id=20,
        sub_user_id=10,
        sub_name="real",
        source="manual:paypal",
        is_private=False,
        is_test_send=False,
    )
    restored = asyncio.run(service.process_send_for_count_rescue(send))
    assert restored is True
    assert "sub_save_count" in achievements.unlock_calls
