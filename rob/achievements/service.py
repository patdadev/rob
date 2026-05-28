from __future__ import annotations

import logging

from rob.achievements.definitions import ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY, AchievementDefinition
from rob.database.repositories.achievements import AchievementsRepository
from rob.database.repositories.models import AchievementSummary

log = logging.getLogger(__name__)


COUNT_NUMBER_TO_ACHIEVEMENT_KEYS: dict[int, tuple[str, ...]] = {
    1: ("count_start",),
    10: ("count_10",),
    67: ("count_67",),
    69: ("count_69",),
    100: ("count_100",),
    420: ("count_420",),
    666: ("count_666",),
    1000: ("count_1000",),
    1234: ("count_1234",),
    4321: ("count_4321",),
    5000: ("count_5000",),
    10000: ("count_10000",),
}


class AchievementsService:
    def __init__(self, repository: AchievementsRepository) -> None:
        self.repository = repository

    def all_definitions(self) -> tuple[AchievementDefinition, ...]:
        return ACHIEVEMENTS

    def get_definition(self, key: str) -> AchievementDefinition | None:
        return ACHIEVEMENTS_BY_KEY.get(key)

    async def unlock_achievement(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        achievement_key: str,
        source: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
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
                source=source,
                metadata=metadata,
            )
            if unlocked:
                await self.repository.record_event(
                    guild_id=guild_id,
                    discord_user_id=discord_user_id,
                    achievement_key=achievement_key,
                    event_type="unlocked",
                    source=source,
                    metadata=metadata,
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

    async def unlock_many(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        achievement_keys: list[str] | tuple[str, ...],
        source: str | None = None,
        metadata: dict | None = None,
    ) -> list[str]:
        unlocked: list[str] = []
        for key in achievement_keys:
            if await self.unlock_achievement(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                achievement_key=key,
                source=source,
                metadata=metadata,
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
        return [achievement for achievement in ACHIEVEMENTS if achievement.key in unlocked_keys]

    async def get_achievement_summary(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AchievementSummary:
        unlocked_count = await self.repository.count_for_user(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        return AchievementSummary(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            unlocked_count=unlocked_count,
            total_count=len(ACHIEVEMENTS),
        )
