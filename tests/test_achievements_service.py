from __future__ import annotations

import asyncio

from rob.achievements.service import AchievementsService


class _FakeAchievementsRepo:
    def __init__(self) -> None:
        self.unlock_calls: list[dict] = []
        self.event_calls: list[dict] = []
        self.keys: set[str] = set()
        self.raise_on_unlock = False
        self.count = 0

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

