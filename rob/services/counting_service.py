from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord

from rob.achievements.service import COUNT_NUMBER_TO_ACHIEVEMENT_KEYS, AchievementsService
from rob.database.repositories.counting import CountingRepository
from rob.database.repositories.dommes import DommesRepository
from rob.database.repositories.guild_settings import GuildSettingsRepository
from rob.services.send_display import is_known_test_sender
from rob.ui.cards.counting import count_failed_card, count_rescue_needed_card, count_saved_card


@dataclass(frozen=True)
class CountingProcessResult:
    success: bool
    expected_number: int
    current_number: int
    reason: str | None = None
    deadline: datetime | None = None


@dataclass
class _RescueWindow:
    guild_id: int
    channel_id: int
    message: discord.Message
    deadline: datetime
    restore_value: int
    failed_user_id: int
    failed_user_is_sub: bool
    task: asyncio.Task[None] | None = None


class CountingService:
    def __init__(
        self,
        *,
        bot: discord.Client,
        counting: CountingRepository,
        guild_settings: GuildSettingsRepository,
        dommes: DommesRepository,
        achievements: AchievementsService | None = None,
        rescue_window_seconds: int = 300,
        rescue_tick_seconds: int = 15,
        parse_test_sends_as_real_sends: bool = False,
        test_gifter_usernames: tuple[str, ...] = (),
    ) -> None:
        self.bot = bot
        self.counting = counting
        self.guild_settings = guild_settings
        self.dommes = dommes
        self.achievements = achievements
        self.rescue_window_seconds = rescue_window_seconds
        self.rescue_tick_seconds = rescue_tick_seconds
        self.parse_test_sends_as_real_sends = parse_test_sends_as_real_sends
        self.test_gifter_usernames = set(test_gifter_usernames)
        self._rescue_windows: dict[int, _RescueWindow] = {}

    async def get_or_create_state(self, guild_id: int):
        state = await self.counting.get(guild_id)
        if state is not None:
            return state
        settings = await self.guild_settings.get(guild_id)
        channel_id = settings.counting_channel_id if settings is not None else None
        return await self.counting.upsert(
            guild_id=guild_id,
            channel_id=channel_id,
            current_number=0,
            last_user_id=None,
            is_enabled=channel_id is not None,
            pending_restore=False,
        )

    async def set_current_number(self, guild_id: int, number: int):
        state = await self.get_or_create_state(guild_id)
        await self._clear_rescue_window(guild_id)
        return await self.counting.upsert(
            guild_id=guild_id,
            channel_id=state.channel_id,
            current_number=max(0, number),
            last_user_id=None,
            is_enabled=True,
            pending_restore=False,
        )

    async def process_message(self, message: discord.Message) -> CountingProcessResult | None:
        if message.guild is None or message.author.bot:
            return None

        state = await self.get_or_create_state(message.guild.id)
        if not state.is_enabled or state.channel_id is None:
            return None
        if message.channel.id != state.channel_id:
            return None

        content = message.content.strip()
        if not content.isdigit():
            return None

        if state.pending_restore:
            expected = state.current_number + 1
            return CountingProcessResult(
                success=False,
                expected_number=expected,
                current_number=state.current_number,
                reason="paused_for_rescue",
            )

        expected = state.current_number + 1
        number = int(content)
        if state.last_user_id == message.author.id:
            return CountingProcessResult(
                success=False,
                expected_number=expected,
                current_number=state.current_number,
                reason="same_user",
            )

        if number != expected:
            settings = await self.guild_settings.get(message.guild.id)
            sub_role_id = settings.sub_role_id if settings is not None else None
            is_sub = (
                isinstance(message.author, discord.Member)
                and sub_role_id is not None
                and any(role.id == sub_role_id for role in message.author.roles)
            )
            if self.achievements is not None:
                await self.achievements.unlock_achievement(
                    guild_id=message.guild.id,
                    discord_user_id=message.author.id,
                    achievement_key="count_first_mistake",
                    source="counting:wrong_number",
                    metadata={"attempted_number": number, "expected_number": expected},
                )
            if is_sub and hasattr(message.channel, "send"):
                deadline = datetime.now(timezone.utc) + timedelta(seconds=self.rescue_window_seconds)
                await self.counting.upsert(
                    guild_id=state.guild_id,
                    channel_id=state.channel_id,
                    current_number=state.current_number,
                    last_user_id=state.last_user_id,
                    is_enabled=state.is_enabled,
                    pending_restore=True,
                )
                await self._start_rescue_window(
                    guild_id=state.guild_id,
                    channel=message.channel,
                    failed_user_id=message.author.id,
                    failed_user_is_sub=True,
                    restore_value=state.current_number,
                    deadline=deadline,
                )
                return CountingProcessResult(
                    success=False,
                    expected_number=expected,
                    current_number=state.current_number,
                    reason="wrong_number_sub_rescue",
                    deadline=deadline,
                )

            await self._clear_rescue_window(state.guild_id)
            await self.counting.upsert(
                guild_id=state.guild_id,
                channel_id=state.channel_id,
                current_number=0,
                last_user_id=None,
                is_enabled=state.is_enabled,
                pending_restore=False,
            )
            return CountingProcessResult(
                success=False,
                expected_number=expected,
                current_number=0,
                reason="wrong_number_reset",
            )

        await self._clear_rescue_window(state.guild_id)
        await self.counting.upsert(
            guild_id=state.guild_id,
            channel_id=state.channel_id,
            current_number=number,
            last_user_id=message.author.id,
            is_enabled=state.is_enabled,
            pending_restore=False,
        )
        if self.achievements is not None:
            for achievement_key in COUNT_NUMBER_TO_ACHIEVEMENT_KEYS.get(number, ()):
                await self.achievements.unlock_achievement(
                    guild_id=message.guild.id,
                    discord_user_id=message.author.id,
                    achievement_key=achievement_key,
                    source="counting:number",
                    metadata={"number": number},
                )
            if expected == 1:
                await self.achievements.unlock_many(
                    guild_id=message.guild.id,
                    discord_user_id=message.author.id,
                    achievement_keys=["count_start", "count_after_reset"],
                    source="counting:restart",
                    metadata={"number": number},
                )
        return CountingProcessResult(
            success=True,
            expected_number=expected,
            current_number=number,
        )

    async def process_send_for_count_rescue(self, send) -> bool:
        rescue = self._rescue_windows.get(send.guild_id)
        if rescue is None:
            return False
        if datetime.now(timezone.utc) >= rescue.deadline:
            await self._expire_rescue_window(send.guild_id)
            return False
        if send.is_private:
            return False
        if send.is_test_send:
            return False
        if not self.parse_test_sends_as_real_sends and is_known_test_sender(
            send.sub_name,
            test_gifter_usernames=self.test_gifter_usernames,
        ):
            return False
        if send.sub_user_id is None:
            return False

        domme = await self.dommes.get_by_user_id(send.guild_id, send.domme_user_id)
        if domme is None:
            return False

        state = await self.get_or_create_state(send.guild_id)
        await self.counting.upsert(
            guild_id=state.guild_id,
            channel_id=state.channel_id,
            current_number=rescue.restore_value,
            last_user_id=None,
            is_enabled=state.is_enabled,
            pending_restore=False,
        )
        try:
            await rescue.message.edit(**count_saved_card(next_number=rescue.restore_value + 1).edit_kwargs())
        except discord.HTTPException:
            pass
        if self.achievements is not None and send.sub_user_id is not None:
            now = datetime.now(timezone.utc)
            remaining_seconds = int((rescue.deadline - now).total_seconds())
            await self.achievements.unlock_achievement(
                guild_id=send.guild_id,
                discord_user_id=send.sub_user_id,
                achievement_key="sub_save_count",
                source="counting:rescue",
                metadata={"remaining_seconds": max(0, remaining_seconds)},
            )
            if rescue.failed_user_is_sub and rescue.failed_user_id == send.sub_user_id:
                await self.achievements.unlock_achievement(
                    guild_id=send.guild_id,
                    discord_user_id=send.sub_user_id,
                    achievement_key="count_sub_recovered_own_mistake",
                    source="counting:rescue",
                )
            if remaining_seconds <= self.rescue_tick_seconds:
                await self.achievements.unlock_achievement(
                    guild_id=send.guild_id,
                    discord_user_id=send.sub_user_id,
                    achievement_key="count_last_second_save",
                    source="counting:rescue",
                    metadata={"remaining_seconds": max(0, remaining_seconds)},
                )
            # TODO: Dom/me-specific recovery achievements need a Dom/me recovery window
            # flow in counting, which is not currently implemented in v2.
        await self._clear_rescue_window(send.guild_id)
        return True

    async def _start_rescue_window(
        self,
        *,
        guild_id: int,
        channel: discord.abc.Messageable,
        failed_user_id: int,
        failed_user_is_sub: bool,
        restore_value: int,
        deadline: datetime,
    ) -> None:
        await self._clear_rescue_window(guild_id)
        remaining = max(0, int((deadline - datetime.now(timezone.utc)).total_seconds()))
        message = await channel.send(
            **count_rescue_needed_card(
                remaining_seconds=remaining,
                deadline_unix=int(deadline.timestamp()),
            ).send_kwargs()
        )
        window = _RescueWindow(
            guild_id=guild_id,
            channel_id=channel.id,
            message=message,
            deadline=deadline,
            restore_value=restore_value,
            failed_user_id=failed_user_id,
            failed_user_is_sub=failed_user_is_sub,
        )
        window.task = asyncio.create_task(self._run_rescue_updates(guild_id), name=f"count-rescue-{guild_id}")
        self._rescue_windows[guild_id] = window

    async def _run_rescue_updates(self, guild_id: int) -> None:
        try:
            while True:
                window = self._rescue_windows.get(guild_id)
                if window is None:
                    return
                remaining = int((window.deadline - datetime.now(timezone.utc)).total_seconds())
                if remaining <= 0:
                    await self._expire_rescue_window(guild_id)
                    return
                await asyncio.sleep(min(self.rescue_tick_seconds, remaining))
                window = self._rescue_windows.get(guild_id)
                if window is None:
                    return
                remaining = max(0, int((window.deadline - datetime.now(timezone.utc)).total_seconds()))
                try:
                    await window.message.edit(
                        **count_rescue_needed_card(
                            remaining_seconds=remaining,
                            deadline_unix=int(window.deadline.timestamp()),
                        ).edit_kwargs()
                    )
                except discord.HTTPException:
                    continue
        except asyncio.CancelledError:
            return

    async def _expire_rescue_window(self, guild_id: int) -> None:
        window = self._rescue_windows.get(guild_id)
        if window is None:
            return
        state = await self.get_or_create_state(guild_id)
        await self.counting.upsert(
            guild_id=state.guild_id,
            channel_id=state.channel_id,
            current_number=0,
            last_user_id=None,
            is_enabled=state.is_enabled,
            pending_restore=False,
        )
        try:
            await window.message.edit(**count_failed_card().edit_kwargs())
        except discord.HTTPException:
            pass
        # TODO: `count_sub_blocked` and `count_domme_failed_recovery` are defined,
        # but current v2 counting does not yet apply a true timed block or Dom/me
        # rescue branch to map those unlocks accurately.
        await self._clear_rescue_window(guild_id)

    async def _clear_rescue_window(self, guild_id: int) -> None:
        window = self._rescue_windows.pop(guild_id, None)
        if window is None:
            return
        if window.task is not None and not window.task.done():
            window.task.cancel()
