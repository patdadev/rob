from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from collections.abc import Awaitable, Callable

from rob.achievements.definitions import (
    ACHIEVEMENTS,
    ACHIEVEMENTS_BY_KEY,
    ENABLED_ACHIEVEMENTS,
    AchievementDefinition,
    achievements_for_trigger,
)
from rob.database.repositories.achievements import AchievementsRepository
from rob.database.repositories.models import AchievementSummary, UserAchievement

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AchievementUnlockState:
    definition: AchievementDefinition
    unlocked_at: datetime | None = None
    source: str | None = None
    metadata: dict | None = None

    @property
    def unlocked(self) -> bool:
        return self.unlocked_at is not None


@dataclass(frozen=True)
class AchievementServerUserStanding:
    discord_user_id: int
    unlocked_count: int


@dataclass(frozen=True)
class AchievementServerRecentUnlock:
    discord_user_id: int
    definition: AchievementDefinition
    unlocked_at: datetime


@dataclass(frozen=True)
class AchievementServerStats:
    members_with_unlocks: int
    unlock_counts: dict[str, int]
    recent_unlocks: list[AchievementServerRecentUnlock]
    top_users: list[AchievementServerUserStanding]


class AchievementsService:
    def __init__(self, repository: AchievementsRepository, *, enabled: bool = True) -> None:
        self.repository = repository
        self.enabled = enabled

    def all_definitions(self) -> tuple[AchievementDefinition, ...]:
        return ACHIEVEMENTS

    def enabled_definitions(self) -> tuple[AchievementDefinition, ...]:
        return ENABLED_ACHIEVEMENTS

    def get_definition(self, key: str) -> AchievementDefinition | None:
        return ACHIEVEMENTS_BY_KEY.get(key)

    def definitions_for_trigger(self, trigger_type: str) -> tuple[AchievementDefinition, ...]:
        return achievements_for_trigger(trigger_type)

    async def unlock_achievement(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        achievement_key: str,
        source: str | None = None,
        metadata: dict | None = None,
        on_unlocked: Callable[[AchievementDefinition], Awaitable[None]] | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        definition = self.get_definition(achievement_key)
        if definition is None:
            log.warning("Attempted to unlock unknown achievement key=%s", achievement_key)
            return False
        if not definition.enabled:
            return False

        try:
            unlocked = await self.repository.unlock(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                achievement_key=achievement_key,
                source=source or definition.source,
                metadata=metadata,
            )
            if unlocked:
                await self.repository.record_event(
                    guild_id=guild_id,
                    discord_user_id=discord_user_id,
                    achievement_key=achievement_key,
                    event_type="unlocked",
                    source=source or definition.source,
                    metadata=metadata,
                )
                if on_unlocked is not None:
                    try:
                        await on_unlocked(definition)
                    except Exception:
                        log.exception(
                            "Achievement announcement failed guild_id=%s user_id=%s key=%s",
                            guild_id,
                            discord_user_id,
                            achievement_key,
                        )
            return unlocked
        except Exception:
            log.exception(
                "Achievement unlock failed guild_id=%s user_id=%s key=%s",
                guild_id,
                discord_user_id,
                achievement_key,
            )
            return False

    async def unlock_triggered_achievements(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        trigger_type: str,
        value: str | int,
        matches: Callable[[str | int | None, str | int], bool],
        source: str | None = None,
        metadata: dict | None = None,
        on_unlocked: Callable[[AchievementDefinition], Awaitable[None]] | None = None,
    ) -> list[str]:
        unlocked: list[str] = []
        for definition in self.definitions_for_trigger(trigger_type):
            if not matches(definition.trigger_value, value):
                continue
            if await self.unlock_achievement(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                achievement_key=definition.key,
                source=source or definition.source,
                metadata=metadata,
                on_unlocked=on_unlocked,
            ):
                unlocked.append(definition.key)
        return unlocked

    async def unlock_many(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        achievement_keys: list[str] | tuple[str, ...],
        source: str | None = None,
        metadata: dict | None = None,
        on_unlocked: Callable[[AchievementDefinition], Awaitable[None]] | None = None,
    ) -> list[str]:
        """Attempt to unlock multiple achievements. Returns keys that were newly unlocked."""
        unlocked: list[str] = []
        for key in achievement_keys:
            if await self.unlock_achievement(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                achievement_key=key,
                source=source,
                metadata=metadata,
                on_unlocked=on_unlocked,
            ):
                unlocked.append(key)
        return unlocked

    async def get_user_achievement_keys(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> set[str]:
        return await self.repository.list_keys_for_user(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )

    async def get_user_achievement_records(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> list[UserAchievement]:
        return await self.repository.list_for_user(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )

    async def get_user_achievement_states(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> list[AchievementUnlockState]:
        records = await self.get_user_achievement_records(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        record_by_key = {record.achievement_key: record for record in records}
        return [
            AchievementUnlockState(
                definition=definition,
                unlocked_at=record_by_key[definition.key].unlocked_at if definition.key in record_by_key else None,
                source=record_by_key[definition.key].source if definition.key in record_by_key else None,
                metadata=record_by_key[definition.key].metadata if definition.key in record_by_key else None,
            )
            for definition in ENABLED_ACHIEVEMENTS
        ]

    async def get_user_achievements(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> list[AchievementDefinition]:
        unlocked_keys = await self.get_user_achievement_keys(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        return [achievement for achievement in ENABLED_ACHIEVEMENTS if achievement.key in unlocked_keys]

    async def get_achievement_summary(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AchievementSummary:
        unlocked_count = len(
            await self.get_user_achievements(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
            )
        )
        return AchievementSummary(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            unlocked_count=unlocked_count,
            total_count=len(ENABLED_ACHIEVEMENTS),
        )

    async def get_server_stats(
        self,
        *,
        guild_id: int,
        recent_limit: int = 5,
        leaderboard_limit: int = 5,
    ) -> AchievementServerStats:
        unlock_counts = await self.repository.list_unlock_counts_for_guild(guild_id=guild_id)
        recent_records = await self.repository.list_recent_unlocks_for_guild(
            guild_id=guild_id,
            limit=recent_limit,
        )
        top_user_rows = await self.repository.list_top_users_for_guild(
            guild_id=guild_id,
            limit=leaderboard_limit,
        )
        recent_unlocks = [
            AchievementServerRecentUnlock(
                discord_user_id=record.discord_user_id,
                definition=definition,
                unlocked_at=record.unlocked_at,
            )
            for record in recent_records
            if (definition := self.get_definition(record.achievement_key)) is not None
        ]
        top_users = [
            AchievementServerUserStanding(discord_user_id=discord_user_id, unlocked_count=unlocked_count)
            for discord_user_id, unlocked_count in top_user_rows
        ]
        return AchievementServerStats(
            members_with_unlocks=await self.repository.count_users_with_unlocks(guild_id=guild_id),
            unlock_counts=unlock_counts,
            recent_unlocks=recent_unlocks,
            top_users=top_users,
        )
