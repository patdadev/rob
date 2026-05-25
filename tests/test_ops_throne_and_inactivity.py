from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from scripts.ops import build_parser, handle_inactivity, handle_throne


class _FakeBotState:
    def __init__(self):
        self.values: dict[str, str] = {}

    async def get_bool(self, key: str, *, default: bool = False):
        raw = self.values.get(key)
        if raw is None:
            return default
        return raw == "true"

    async def set_value(self, key: str, value: str):
        self.values[key] = value


class _FakeThroneCreators:
    async def get_by_handle(self, _guild_id: int, handle: str):
        if handle.lower() != "pat":
            return None
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            throne_handle="pat",
            throne_creator_id="creator-1",
            discord_user_id=10,
            tracking_mode="webhook",
            webhook_connected_at=now,
            last_successful_event_at=now,
            setup_verified_at=now,
        )

    async def list_for_guild(self, _guild_id: int):
        return [
            SimpleNamespace(
                throne_handle="pat",
                throne_creator_id="creator-1",
                discord_user_id=10,
                tracking_mode="webhook",
                last_successful_event_at=None,
                setup_verified_at=None,
            )
        ]


class _FakeSubs:
    async def list_for_guild(self, _guild_id: int):
        now = datetime.now(timezone.utc)
        return [SimpleNamespace(discord_user_id=20, send_name="subby", registered_at=now)]


def test_inactivity_parser_and_toggle(capsys):
    parser = build_parser()
    args = parser.parse_args(["inactivity", "on", "--guild-id", "1"])

    ctx = SimpleNamespace(
        bot_state=_FakeBotState(),
        settings=SimpleNamespace(inactivity_enabled_default=False),
        guild_settings=SimpleNamespace(list_guild_ids=lambda: [1]),
    )
    asyncio.run(handle_inactivity(ctx, args))

    out = capsys.readouterr().out
    assert "Inactivity" in out
    assert "Enabled: true" in out


def test_throne_status_and_dommes_render(capsys):
    ctx = SimpleNamespace(
        throne_creators=_FakeThroneCreators(),
        subs=_FakeSubs(),
        settings=SimpleNamespace(),
        guild_settings=SimpleNamespace(list_guild_ids=lambda: [1]),
    )

    status_args = SimpleNamespace(throne_command="status", guild_id=1, handle="pat")
    asyncio.run(handle_throne(ctx, status_args))
    status_out = capsys.readouterr().out
    assert "Throne Status" in status_out
    assert "Found: true" in status_out
    assert "Creator ID: creator-1" in status_out

    dommes_args = SimpleNamespace(throne_command="dommes", guild_id=1)
    asyncio.run(handle_throne(ctx, dommes_args))
    dommes_out = capsys.readouterr().out
    assert "Throne Dom/mes" in dommes_out
    assert "@pat" in dommes_out
    assert "Creator ID: creator-1" in dommes_out
