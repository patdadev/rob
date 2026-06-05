from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from rob.discord.client import RobBot


class _FakeTree:
    def __init__(self):
        self.clear_calls: list[object] = []
        self.sync_calls: list[object | None] = []

    def clear_commands(self, *, guild=None):
        self.clear_calls.append(guild)

    async def sync(self, *, guild=None):
        self.sync_calls.append(guild)
        return [SimpleNamespace(name="achievements")]


def test_single_guild_sync_clears_stale_guild_commands_before_global_sync():
    tree = _FakeTree()
    fake_bot = SimpleNamespace(tree=tree)

    asyncio.run(RobBot._sync_application_commands(fake_bot, [123456789]))

    assert len(tree.clear_calls) == 1
    assert len(tree.sync_calls) == 2
    assert tree.sync_calls[0] is tree.clear_calls[0]
    assert tree.sync_calls[1] is None


def test_multi_guild_sync_keeps_global_only():
    tree = _FakeTree()
    fake_bot = SimpleNamespace(tree=tree)

    asyncio.run(RobBot._sync_application_commands(fake_bot, [1, 2]))

    assert tree.clear_calls == []
    assert tree.sync_calls == [None]


def _fake_interaction(*, guild_id=123, command_name="leaderboard"):
    response = SimpleNamespace(send_message=AsyncMock())
    return SimpleNamespace(
        user=SimpleNamespace(id=7),
        guild=SimpleNamespace(id=guild_id) if guild_id is not None else None,
        guild_id=guild_id,
        command=SimpleNamespace(qualified_name=command_name),
        response=response,
    )


def test_global_interaction_check_allows_terms_command_without_gate():
    terms_cog = SimpleNamespace(
        is_terms_interaction=lambda interaction: interaction.command.qualified_name == "terms",
        ensure_terms_acceptance=AsyncMock(return_value=False),
    )
    fake_bot = SimpleNamespace(
        blacklist_repo=SimpleNamespace(contains=AsyncMock(return_value=False)),
        maintenance_service=SimpleNamespace(is_rob_offline_for_guild=AsyncMock(return_value=False)),
        get_cog=lambda name: terms_cog if name == "TermsCog" else None,
    )
    interaction = _fake_interaction(command_name="terms")

    allowed = asyncio.run(RobBot._global_interaction_check(fake_bot, interaction))

    assert allowed is True
    terms_cog.ensure_terms_acceptance.assert_not_awaited()


def test_global_interaction_check_delegates_non_terms_test_guild_commands():
    terms_cog = SimpleNamespace(
        is_terms_interaction=lambda _interaction: False,
        ensure_terms_acceptance=AsyncMock(return_value=False),
    )
    fake_bot = SimpleNamespace(
        blacklist_repo=SimpleNamespace(contains=AsyncMock(return_value=False)),
        maintenance_service=SimpleNamespace(is_rob_offline_for_guild=AsyncMock(return_value=False)),
        get_cog=lambda name: terms_cog if name == "TermsCog" else None,
    )
    interaction = _fake_interaction(command_name="leaderboard")

    allowed = asyncio.run(RobBot._global_interaction_check(fake_bot, interaction))

    assert allowed is False
    terms_cog.ensure_terms_acceptance.assert_awaited_once_with(interaction)


def test_global_interaction_check_ignores_dm_terms_gate():
    terms_cog = SimpleNamespace(
        is_terms_interaction=lambda _interaction: False,
        ensure_terms_acceptance=AsyncMock(return_value=False),
    )
    fake_bot = SimpleNamespace(
        blacklist_repo=SimpleNamespace(contains=AsyncMock(return_value=False)),
        maintenance_service=SimpleNamespace(is_rob_offline_for_guild=AsyncMock(return_value=False)),
        get_cog=lambda name: terms_cog if name == "TermsCog" else None,
    )
    interaction = _fake_interaction(guild_id=None, command_name="leaderboard")

    allowed = asyncio.run(RobBot._global_interaction_check(fake_bot, interaction))

    assert allowed is True
    terms_cog.ensure_terms_acceptance.assert_not_awaited()
