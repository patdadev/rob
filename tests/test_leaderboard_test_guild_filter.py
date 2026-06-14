"""Leaderboard opt-out filtering (applies to every guild)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from rob.services.leaderboard_service import LeaderboardService

GUILD_ID = 1506597978251591813


class _FakeDommes:
    def __init__(self, dommes):
        self._dommes = dommes
        self.calls = 0

    async def list_for_guild(self, guild_id):
        self.calls += 1
        return [d for d in self._dommes if d.guild_id == guild_id]


def _entry(user_id, total=100, count=1):
    return SimpleNamespace(user_id=user_id, total_cents=total, send_count=count)


def _make_service(dommes_repo):
    return LeaderboardService(
        bot=SimpleNamespace(),
        guild_settings=SimpleNamespace(),
        leaderboards=SimpleNamespace(),
        bot_state=SimpleNamespace(),
        maintenance=SimpleNamespace(),
        dommes=dommes_repo,
    )


def test_filter_drops_opted_out_dommes():
    dommes = _FakeDommes([
        SimpleNamespace(guild_id=GUILD_ID, discord_user_id=1, leaderboard_visible=True),
        SimpleNamespace(guild_id=GUILD_ID, discord_user_id=2, leaderboard_visible=False),
    ])
    service = _make_service(dommes)
    entries = [_entry(1), _entry(2), _entry(3)]

    result = asyncio.run(service._filter_entries_for_guild(GUILD_ID, entries))

    # Only the opted-in, registered Dom/me survives.
    assert [e.user_id for e in result] == [1]
    assert dommes.calls == 1


def test_filter_noop_when_dommes_repo_missing():
    service = _make_service(None)
    entries = [_entry(1)]
    result = asyncio.run(service._filter_entries_for_guild(GUILD_ID, entries))
    assert result is entries


def test_filter_noop_when_no_entries():
    dommes = _FakeDommes([])
    service = _make_service(dommes)
    result = asyncio.run(service._filter_entries_for_guild(GUILD_ID, []))
    assert result == []
    assert dommes.calls == 0
