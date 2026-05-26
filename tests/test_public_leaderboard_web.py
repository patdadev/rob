from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from rob.throne import webhooks


class _FakePublicRepo:
    def __init__(self, row):
        self.row = row

    async def get_by_token(self, token: str):
        return self.row


class _FakeLeaderboards:
    async def get_top_dommes_public(self, *args, **kwargs):
        return [
            SimpleNamespace(label="High Priestess Rae", total_cents=1042481, send_count=18),
            SimpleNamespace(label="Registered Dom/me", total_cents=0, send_count=0),
            SimpleNamespace(label="Registered Dom/me", total_cents=0, send_count=0),
        ]

    async def get_public_data_freshness(self, *args, **kwargs):
        return datetime(2026, 5, 20, 12, 30, tzinfo=timezone.utc)


class _Req:
    def __init__(self):
        self.match_info = {"public_token": "token"}
        self.app = {
            "database": object(),
            "settings": SimpleNamespace(
                leaderboard_limit=10,
                throne_parse_test_sends_as_real_sends=False,
                throne_test_gifter_usernames=("marie_123",),
                throne_test_send_leaderboard_owner_user_id=None,
                public_leaderboard_cache_seconds=60,
            ),
        }


def test_public_route_404_for_missing_or_disabled(monkeypatch):
    monkeypatch.setattr(webhooks, "PublicLeaderboardsRepository", lambda _db: _FakePublicRepo(None))
    response = asyncio.run(webhooks.handle_public_leaderboard(_Req()))
    assert response.status == 404


def test_public_route_renders_polished_html_and_freshness(monkeypatch):
    row = SimpleNamespace(guild_id=1, title="Send Leaderboard", enabled=True)
    monkeypatch.setattr(webhooks, "PublicLeaderboardsRepository", lambda _db: _FakePublicRepo(row))
    monkeypatch.setattr(webhooks, "LeaderboardsRepository", lambda _db: _FakeLeaderboards())
    response = asyncio.run(webhooks.handle_public_leaderboard(_Req()))
    text = response.text
    assert response.status == 200
    assert response.headers["Cache-Control"] == "public, max-age=60"
    assert "leaderboard-page" in text
    assert "leaderboard-panel" in text
    assert "background:#000" in text
    assert "Times New Roman" in text
    assert "<img" not in text
    assert "🥇" not in text
    assert "<@" not in text
    assert "123456789012345678" not in text
    assert "Leaderboard data updated:" in text
    assert "Page refreshed:" in text
    assert "2026-05-20 12:30 UTC" in text
    assert "Tracked send total" in text
    assert "$10,424.81" in text
    assert "18 sends" in text
    assert "Registered Dom/me 2" in text


def test_public_route_no_send_state(monkeypatch):
    row = SimpleNamespace(guild_id=1, title="Send Leaderboard", enabled=True)

    class _EmptyLeaderboards:
        async def get_top_dommes_public(self, *args, **kwargs):
            return []

        async def get_public_data_freshness(self, *args, **kwargs):
            return None

    monkeypatch.setattr(webhooks, "PublicLeaderboardsRepository", lambda _db: _FakePublicRepo(row))
    monkeypatch.setattr(webhooks, "LeaderboardsRepository", lambda _db: _EmptyLeaderboards())
    response = asyncio.run(webhooks.handle_public_leaderboard(_Req()))
    text = response.text
    assert "No tracked sends are available yet." in text
    assert "Leaderboard data updated: No tracked sends yet" in text
