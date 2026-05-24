from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from rob.services.inactivity_service import InactivityService


class _FakeBotState:
    def __init__(self):
        self.values: dict[str, str] = {}

    async def get_text(self, key: str) -> str | None:
        return self.values.get(key)

    async def set_value(self, key: str, value: str) -> None:
        self.values[key] = value

    async def get_values(self, keys: list[str]) -> dict[str, str]:
        return {key: self.values[key] for key in keys if key in self.values}

    async def set_values(self, values: dict[str, str | None]) -> None:
        for key, value in values.items():
            if value is None:
                self.values.pop(key, None)
            else:
                self.values[key] = value


class _FakeGuildSettingsRepo:
    def __init__(self, inactive_role_id: int | None):
        self.inactive_role_id = inactive_role_id

    async def get(self, _guild_id: int):
        return SimpleNamespace(inactive_role_id=self.inactive_role_id)


class _FakeMember:
    def __init__(self, user_id: int):
        self.id = user_id
        self.bot = False
        self.nick = None
        self.display_name = f"User{user_id}"
        self.name = f"User{user_id}"
        self.mention = f"<@{user_id}>"
        self.dm_messages: list[str] = []
        self.kicked = False

    async def send(self, message: str):
        self.dm_messages.append(message)

    async def kick(self, *, reason: str):
        del reason
        self.kicked = True


class _FakeRole:
    def __init__(self, role_id: int, members: list[_FakeMember]):
        self.id = role_id
        self.members = members


class _FakeGuild:
    def __init__(self, guild_id: int, role: _FakeRole):
        self.id = guild_id
        self._role = role

    def get_role(self, role_id: int):
        if self._role.id == role_id:
            return self._role
        return None


def _service(*, bot_state: _FakeBotState, inactive_role_id: int | None):
    return InactivityService(
        bot_state=bot_state,
        guild_settings=_FakeGuildSettingsRepo(inactive_role_id),
        enabled_default=False,
        assignment_grace_days=14,
        bootstrap_grace_days=21,
        final_notice_days=7,
        notice_channel_id=None,
    )


def test_inactivity_disabled_by_default_no_processing():
    member = _FakeMember(10)
    guild = _FakeGuild(1, _FakeRole(99, [member]))
    bot_state = _FakeBotState()
    service = _service(bot_state=bot_state, inactive_role_id=99)

    snapshots = asyncio.run(service.process_guild(guild, send_notifications=False, perform_kicks=False))

    assert snapshots == []


def test_inactivity_enabled_creates_member_schedule():
    member = _FakeMember(10)
    guild = _FakeGuild(1, _FakeRole(99, [member]))
    bot_state = _FakeBotState()
    service = _service(bot_state=bot_state, inactive_role_id=99)
    asyncio.run(service.set_enabled(1, True))

    snapshots = asyncio.run(service.process_guild(guild, send_notifications=False, perform_kicks=False))

    assert len(snapshots) == 1
    assert snapshots[0].member.id == 10
    key_prefix = "inactivity:1:user:10"
    assert f"{key_prefix}:assigned_at" in bot_state.values
    assert f"{key_prefix}:remove_at" in bot_state.values


def test_inactivity_kicks_when_expired():
    member = _FakeMember(10)
    guild = _FakeGuild(1, _FakeRole(99, [member]))
    bot_state = _FakeBotState()
    service = _service(bot_state=bot_state, inactive_role_id=99)
    asyncio.run(service.set_enabled(1, True))

    now = datetime.now(timezone.utc)
    key_prefix = "inactivity:1:user:10"
    bot_state.values[f"{key_prefix}:assigned_at"] = (now - timedelta(days=20)).isoformat()
    bot_state.values[f"{key_prefix}:remove_at"] = (now - timedelta(minutes=5)).isoformat()
    bot_state.values[f"{key_prefix}:initial_notice_sent"] = "true"
    bot_state.values[f"{key_prefix}:final_notice_sent"] = "true"
    bot_state.values["inactivity:1:bootstrapped_at"] = (now - timedelta(days=20)).isoformat()

    snapshots = asyncio.run(service.process_guild(guild, send_notifications=False, perform_kicks=True))

    assert snapshots == []
    assert member.kicked is True
    assert f"{key_prefix}:assigned_at" not in bot_state.values
