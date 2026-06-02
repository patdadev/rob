from __future__ import annotations

import asyncio
from datetime import datetime

from rob.achievements.service import AchievementsService
from rob.database.repositories.models import UserAchievement


class _FakeAchievementsRepo:
    def __init__(self) -> None:
        self.unlock_calls: list[dict] = []
        self.event_calls: list[dict] = []
        self.keys: set[str] = set()
        self.raise_on_unlock = False
        self.count = 0
        self.records: list[UserAchievement] = []

    async def unlock(self, **kwargs):
        if self.raise_on_unlock:
            raise RuntimeError("boom")
        self.unlock_calls.append(kwargs)
        key = str(kwargs["achievement_key"])
        if key in self.keys:
            return False
        self.keys.add(key)
        self.count += 1
        return True

    async def record_event(self, **kwargs):
        self.event_calls.append(kwargs)

    async def list_keys_for_user(self, **_kwargs):
        return set(self.keys)

    async def count_for_user(self, **_kwargs):
        return self.count

    async def list_for_user(self, **_kwargs):
        return list(self.records)

    async def list_unlock_counts_for_guild(self, **_kwargs):
        return {"count_10": 2}

    async def list_recent_unlocks_for_guild(self, **_kwargs):
        return list(self.records)

    async def list_top_users_for_guild(self, **_kwargs):
        return [(2, 2)]

    async def count_users_with_unlocks(self, **_kwargs):
        return 1


def test_unlock_achievement_uses_on_conflict_style_semantics():
    repo = _FakeAchievementsRepo()
    service = AchievementsService(repo)  # type: ignore[arg-type]

    first = asyncio.run(
        service.unlock_achievement(
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
            source="test",
        )
    )
    second = asyncio.run(
        service.unlock_achievement(
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
            source="test",
        )
    )

    assert first is True
    assert second is False
    assert len(repo.unlock_calls) == 2
    assert len(repo.event_calls) == 1


def test_unknown_achievement_key_is_rejected():
    repo = _FakeAchievementsRepo()
    service = AchievementsService(repo)  # type: ignore[arg-type]

    unlocked = asyncio.run(
        service.unlock_achievement(
            guild_id=1,
            discord_user_id=2,
            achievement_key="does_not_exist",
        )
    )

    assert unlocked is False
    assert repo.unlock_calls == []


def test_unlock_failures_are_non_fatal():
    repo = _FakeAchievementsRepo()
    repo.raise_on_unlock = True
    service = AchievementsService(repo)  # type: ignore[arg-type]

    unlocked = asyncio.run(
        service.unlock_achievement(
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
        )
    )

    assert unlocked is False


def test_summary_counts_unlocked_and_total():
    repo = _FakeAchievementsRepo()
    repo.keys = {"count_10", "count_67"}
    repo.count = 2
    service = AchievementsService(repo)  # type: ignore[arg-type]

    summary = asyncio.run(service.get_achievement_summary(guild_id=1, discord_user_id=2))

    assert summary.unlocked_count == 2
    assert summary.total_count >= 2


def test_unlock_callback_runs_only_for_new_unlocks():
    repo = _FakeAchievementsRepo()
    service = AchievementsService(repo)  # type: ignore[arg-type]
    announced: list[str] = []

    async def _callback(definition):
        announced.append(definition.key)

    first = asyncio.run(
        service.unlock_achievement(
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
            source="test",
            on_unlocked=_callback,
        )
    )
    second = asyncio.run(
        service.unlock_achievement(
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
            source="test",
            on_unlocked=_callback,
        )
    )

    assert first is True
    assert second is False
    assert announced == ["count_10"]


def test_unlock_achievement_is_globally_disabled_without_touching_repository():
    repo = _FakeAchievementsRepo()
    service = AchievementsService(repo, enabled=False)  # type: ignore[arg-type]

    unlocked = asyncio.run(
        service.unlock_achievement(
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
            source="test",
        )
    )

    assert unlocked is False
    assert repo.unlock_calls == []
    assert repo.event_calls == []


def test_unlock_many_with_callback():
    repo = _FakeAchievementsRepo()
    service = AchievementsService(repo)  # type: ignore[arg-type]
    announced: list[str] = []

    async def _callback(definition):
        announced.append(definition.key)

    result = asyncio.run(
        service.unlock_many(
            guild_id=1,
            discord_user_id=2,
            achievement_keys=["count_10", "count_67", "count_69"],
            source="test",
            on_unlocked=_callback,
        )
    )

    assert result == ["count_10", "count_67", "count_69"]
    assert announced == ["count_10", "count_67", "count_69"]


def test_unlock_many_skips_already_unlocked():
    repo = _FakeAchievementsRepo()
    repo.keys = {"count_10"}
    service = AchievementsService(repo)  # type: ignore[arg-type]

    result = asyncio.run(
        service.unlock_many(
            guild_id=1,
            discord_user_id=2,
            achievement_keys=["count_10", "count_67"],
            source="test",
        )
    )

    assert result == ["count_67"]


def test_enabled_definitions_returns_only_enabled():
    repo = _FakeAchievementsRepo()
    service = AchievementsService(repo)  # type: ignore[arg-type]

    enabled = service.enabled_definitions()
    all_defs = service.all_definitions()

    assert len(enabled) <= len(all_defs)
    assert all(d.enabled for d in enabled)


def test_unlock_triggered_achievements_uses_catalog_thresholds():
    repo = _FakeAchievementsRepo()
    service = AchievementsService(repo)  # type: ignore[arg-type]

    result = asyncio.run(
        service.unlock_triggered_achievements(
            guild_id=1,
            discord_user_id=2,
            trigger_type="sub_total_cents",
            value=100_000,
            matches=lambda trigger_value, current_value: isinstance(trigger_value, int) and current_value >= trigger_value,
        )
    )

    assert "sub_first_send" in result
    assert "sub_100_sent" in result
    assert "sub_1000_sent" in result


def test_get_user_achievement_states_includes_locked_entries():
    repo = _FakeAchievementsRepo()
    repo.records = [
        UserAchievement(
            id=1,
            guild_id=1,
            discord_user_id=2,
            achievement_key="count_10",
            unlocked_at=datetime(2026, 1, 2),
            source="counting:number",
            metadata={},
            created_at=datetime(2026, 1, 2),
            updated_at=datetime(2026, 1, 2),
        )
    ]
    service = AchievementsService(repo)  # type: ignore[arg-type]

    states = asyncio.run(service.get_user_achievement_states(guild_id=1, discord_user_id=2))

    unlocked = next(state for state in states if state.definition.key == "count_10")
    locked = next(state for state in states if state.definition.key == "secret_command")
    assert unlocked.unlocked is True
    assert locked.unlocked is False
