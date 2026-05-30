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


class _FakeMaintenance:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    async def notifications_suppressed(self) -> bool:
        return self.enabled


class _FakeMember:
    def __init__(self, user_id: int, *, joined_at: datetime | None = None):
        self.id = user_id
        self.bot = False
        self.nick = None
        self.display_name = f"User{user_id}"
        self.name = f"User{user_id}"
        self.mention = f"<@{user_id}>"
        self.dm_messages: list[dict[str, object]] = []
        self.kicked = False
        self.joined_at = joined_at

    async def send(self, content=None, view=None, **kwargs):
        self.dm_messages.append({"content": content, "view": view, **kwargs})

    async def kick(self, *, reason: str):
        del reason
        self.kicked = True


class _FakeRole:
    def __init__(self, role_id: int, members: list[_FakeMember]):
        self.id = role_id
        self.members = members


class _FakeGuild:
    def __init__(self, guild_id: int, role: _FakeRole, *, name: str = "VIB"):
        self.id = guild_id
        self._role = role
        self.name = name

    def get_role(self, role_id: int):
        if self._role.id == role_id:
            return self._role
        return None


def _service(*, bot_state: _FakeBotState, inactive_role_id: int | None, maintenance: _FakeMaintenance | None = None):
    return InactivityService(
        bot_state=bot_state,
        guild_settings=_FakeGuildSettingsRepo(inactive_role_id),
        enabled_default=False,
        new_member_grace_days=7,
        assignment_grace_days=14,
        bootstrap_grace_days=21,
        final_notice_days=7,
        notice_channel_id=None,
        maintenance=maintenance,
    )


def _view_text(payload: dict[str, object]) -> str:
    view = payload.get("view")
    if view is None:
        return str(payload.get("content", ""))
    chunks: list[str] = []
    for top_level in getattr(view, "children", []):
        for child in getattr(top_level, "children", []):
            content = getattr(child, "content", None)
            if content:
                chunks.append(str(content))
    return "\n".join(chunks)


def test_new_member_grace_no_immediate_warning():
    joined_at = datetime.now(timezone.utc)
    member = _FakeMember(10, joined_at=joined_at)
    guild = _FakeGuild(1, _FakeRole(99, [member]))
    bot_state = _FakeBotState()
    service = _service(bot_state=bot_state, inactive_role_id=99)
    asyncio.run(service.set_enabled(1, True))

    snapshots = asyncio.run(service.process_guild(guild, send_notifications=True, perform_kicks=False))

    assert len(snapshots) == 1
    assert member.dm_messages == []


def test_new_member_warning_after_seven_days_contains_timestamps():
    joined_at = datetime.now(timezone.utc) - timedelta(days=8)
    member = _FakeMember(10, joined_at=joined_at)
    guild = _FakeGuild(1, _FakeRole(99, [member]))
    bot_state = _FakeBotState()
    service = _service(bot_state=bot_state, inactive_role_id=99)
    asyncio.run(service.set_enabled(1, True))

    asyncio.run(service.process_guild(guild, send_notifications=True, perform_kicks=False))

    assert len(member.dm_messages) == 1
    rendered = _view_text(member.dm_messages[0])
    assert "Hello? Anyone there" in rendered
    assert "marked as inactive" in rendered
    assert "We'll send another reminder" in rendered
    assert "<t:" in rendered


def test_final_inactivity_warning_uses_week_two_copy():
    member = _FakeMember(10)
    guild = _FakeGuild(1, _FakeRole(99, [member]))
    bot_state = _FakeBotState()
    service = _service(bot_state=bot_state, inactive_role_id=99)
    asyncio.run(service.set_enabled(1, True))

    now = datetime.now(timezone.utc)
    key_prefix = "inactivity:1:user:10"
    bot_state.values[f"{key_prefix}:assigned_at"] = (now - timedelta(days=14)).isoformat()
    bot_state.values[f"{key_prefix}:remove_at"] = (now + timedelta(days=6)).isoformat()
    bot_state.values[f"{key_prefix}:initial_notice_sent"] = "true"
    bot_state.values[f"{key_prefix}:final_notice_sent"] = "false"
    bot_state.values["inactivity:1:bootstrapped_at"] = (now - timedelta(days=14)).isoformat()

    asyncio.run(service.process_guild(guild, send_notifications=True, perform_kicks=False))

    assert len(member.dm_messages) == 1
    rendered = _view_text(member.dm_messages[0])
    assert "I don't miss you, I swear" in rendered
    assert "You're on week 2 right now" in rendered
    assert "clears automatically" in rendered


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


def test_inactivity_maintenance_suppresses_dms_and_kicks():
    member = _FakeMember(10)
    guild = _FakeGuild(1, _FakeRole(99, [member]))
    bot_state = _FakeBotState()
    service = _service(
        bot_state=bot_state,
        inactive_role_id=99,
        maintenance=_FakeMaintenance(enabled=True),
    )
    asyncio.run(service.set_enabled(1, True))

    now = datetime.now(timezone.utc)
    key_prefix = "inactivity:1:user:10"
    bot_state.values[f"{key_prefix}:assigned_at"] = (now - timedelta(days=14)).isoformat()
    bot_state.values[f"{key_prefix}:remove_at"] = (now - timedelta(minutes=5)).isoformat()
    bot_state.values[f"{key_prefix}:initial_notice_sent"] = "false"
    bot_state.values[f"{key_prefix}:final_notice_sent"] = "false"
    bot_state.values["inactivity:1:bootstrapped_at"] = (now - timedelta(days=14)).isoformat()

    snapshots = asyncio.run(service.process_guild(guild, send_notifications=True, perform_kicks=True))

    assert len(snapshots) == 1
    assert member.dm_messages == []
    assert member.kicked is False
