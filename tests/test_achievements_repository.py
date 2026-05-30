from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from rob.database.repositories.achievements import AchievementsRepository


class _FakeConnection:
    def __init__(self):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.fetch_calls: list[tuple[str, tuple]] = []
        self.fetchval_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []
        self.return_row = {"id": 1}

    async def fetchrow(self, query: str, *params):
        self.fetchrow_calls.append((query, params))
        return self.return_row

    async def fetch(self, query: str, *params):
        self.fetch_calls.append((query, params))
        return [{"achievement_key": "count_10"}]

    async def fetchval(self, _query: str, *_params):
        self.fetchval_calls.append((_query, _params))
        return 1

    async def execute(self, query: str, *params):
        self.execute_calls.append((query, params))
        return "INSERT 0 1"


class _FakeDatabase:
    def __init__(self, connection: _FakeConnection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_unlock_query_uses_on_conflict_do_nothing():
    connection = _FakeConnection()
    repo = AchievementsRepository(_FakeDatabase(connection))  # type: ignore[arg-type]

    unlocked = asyncio.run(
        repo.unlock(
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
            source="test",
            metadata={"x": 1},
        )
    )

    assert unlocked is True
    query, params = connection.fetchrow_calls[0]
    assert "ON CONFLICT (guild_id, discord_user_id, achievement_key)" in query
    assert "DO NOTHING" in query
    assert params[:3] == (1, 2, "count_10")
    assert isinstance(params[4], str)
    assert json.loads(params[4]) == {"x": 1}


def test_list_keys_and_event_recording():
    connection = _FakeConnection()
    repo = AchievementsRepository(_FakeDatabase(connection))  # type: ignore[arg-type]

    keys = asyncio.run(repo.list_keys_for_user(guild_id=1, discord_user_id=2))
    asyncio.run(
        repo.record_event(
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
            event_type="unlocked",
            source="test",
        )
    )

    assert "count_10" in keys
    assert connection.execute_calls
    _, params = connection.execute_calls[0]
    assert isinstance(params[5], str)
    assert json.loads(params[5]) == {}


def test_reset_for_guild_deletes_unlocks_and_events():
    connection = _FakeConnection()
    repo = AchievementsRepository(_FakeDatabase(connection))  # type: ignore[arg-type]

    result = asyncio.run(repo.reset_for_guild(guild_id=99))

    assert result == {"guild_id": 99, "unlocks_deleted": 1, "events_deleted": 1}
    assert len(connection.fetchval_calls) == 2
    assert "DELETE FROM user_achievements" in connection.fetchval_calls[0][0]
    assert connection.fetchval_calls[0][1] == (99,)
    assert "DELETE FROM achievement_events" in connection.fetchval_calls[1][0]
