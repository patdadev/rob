from __future__ import annotations

from rob.database.repositories.bot_state import BotStateRepository
from rob.database.repositories.models import MaintenanceState
from rob.services.leaderboard_status import LeaderboardStatus
from rob.utils.time import utc_now


MAINTENANCE_MODE_KEY = "maintenance_mode"
MAINTENANCE_REASON_KEY = "maintenance_reason"
LEADERBOARD_REFRESH_REQUESTED_AT_KEY = "leaderboard_refresh_requested_at"
LEADERBOARD_REFRESH_COMPLETED_AT_KEY = "leaderboard_refresh_completed_at"


class MaintenanceService:
    def __init__(self, bot_state: BotStateRepository) -> None:
        self.bot_state = bot_state

    async def get_state(self) -> MaintenanceState:
        values = await self.bot_state.get_values(
            [MAINTENANCE_MODE_KEY, MAINTENANCE_REASON_KEY]
        )
        raw_enabled = values.get(MAINTENANCE_MODE_KEY, "false")
        enabled = raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
        reason = values.get(MAINTENANCE_REASON_KEY) or None
        _raw_value, updated_at = await self.bot_state.get_value(MAINTENANCE_MODE_KEY)
        return MaintenanceState(enabled=enabled, reason=reason, updated_at=updated_at)

    async def is_enabled(self) -> bool:
        return await self.bot_state.get_bool(MAINTENANCE_MODE_KEY, default=False)

    async def get_leaderboard_status(self) -> LeaderboardStatus:
        if await self.is_enabled():
            return LeaderboardStatus.MAINTENANCE
        return LeaderboardStatus.LIVE

    async def registrations_blocked(self) -> bool:
        return await self.is_enabled()

    async def notifications_suppressed(self) -> bool:
        return await self.is_enabled()

    async def enable(self, *, reason: str | None) -> None:
        await self.bot_state.set_values(
            {
                MAINTENANCE_MODE_KEY: "true",
                MAINTENANCE_REASON_KEY: reason or "",
            }
        )
        await self.request_leaderboard_refresh()

    async def disable(self) -> None:
        await self.bot_state.set_values(
            {
                MAINTENANCE_MODE_KEY: "false",
                MAINTENANCE_REASON_KEY: "",
            }
        )
        await self.request_leaderboard_refresh()

    async def request_leaderboard_refresh(self) -> None:
        marker = utc_now().isoformat()
        await self.bot_state.set_value(LEADERBOARD_REFRESH_REQUESTED_AT_KEY, marker)

    async def consume_leaderboard_refresh_request(self) -> bool:
        requested, _ = await self.bot_state.get_value(LEADERBOARD_REFRESH_REQUESTED_AT_KEY)
        completed, _ = await self.bot_state.get_value(LEADERBOARD_REFRESH_COMPLETED_AT_KEY)
        if not requested or requested == completed:
            return False
        await self.bot_state.set_value(LEADERBOARD_REFRESH_COMPLETED_AT_KEY, requested)
        return True
