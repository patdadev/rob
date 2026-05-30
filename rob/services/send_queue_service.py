from __future__ import annotations

import asyncio
import logging

import discord

from rob.achievements.embeds import achievement_unlocked_card
from rob.achievements.service import AchievementsService
from rob.database.repositories.guild_settings import GuildSettingsRepository
from rob.database.repositories.leaderboards import LeaderboardsRepository
from rob.database.repositories.sends import SendsRepository
from rob.services.counting_service import CountingService
from rob.services.leaderboard_service import LeaderboardService
from rob.services.maintenance_service import MaintenanceService
from rob.services.send_display import build_sub_display
from rob.ui.cards.send import send_card

log = logging.getLogger(__name__)


class SendQueueService:
    def __init__(
        self,
        *,
        bot: discord.Client,
        sends: SendsRepository,
        guild_settings: GuildSettingsRepository,
        maintenance: MaintenanceService,
        leaderboard_service: LeaderboardService,
        counting_service: CountingService | None = None,
        achievements: AchievementsService | None = None,
        leaderboards: LeaderboardsRepository | None = None,
        include_test_sends: bool = False,
        owner_test_user_id: int | None = None,
        test_gifter_usernames: tuple[str, ...] = (),
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self.bot = bot
        self.sends = sends
        self.guild_settings = guild_settings
        self.maintenance = maintenance
        self.leaderboard_service = leaderboard_service
        self.counting_service = counting_service
        self.achievements = achievements
        self.leaderboards = leaderboards
        self.include_test_sends = include_test_sends
        self.owner_test_user_id = owner_test_user_id
        self.test_gifter_usernames = test_gifter_usernames
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._startup_leaderboard_refresh_done = False
        self._send_notifications: asyncio.Queue[int] | None = None

    def _notification_queue(self) -> asyncio.Queue[int]:
        if self._send_notifications is None:
            self._send_notifications = asyncio.Queue()
        return self._send_notifications

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="rob-send-queue")

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        await self._refresh_leaderboards_on_startup()
        while not self._stopping:
            try:
                try:
                    send_id = await asyncio.wait_for(
                        self._notification_queue().get(),
                        timeout=self.poll_interval_seconds,
                    )
                except TimeoutError:
                    await self.process_idle_tasks()
                else:
                    await self.process_send_by_id(send_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Send queue cycle failed.")

    async def _refresh_leaderboards_on_startup(self) -> None:
        if self._startup_leaderboard_refresh_done:
            return
        self._startup_leaderboard_refresh_done = True
        try:
            log.info("Refreshing all leaderboard messages on bot startup.")
            await self.leaderboard_service.refresh_all_guilds()
        except Exception:
            log.exception("Startup leaderboard refresh failed.")

    async def process_cycle(self) -> None:
        if not await self.maintenance.is_enabled():
            released = await self.sends.release_queued_maintenance()
            if released:
                log.info("Released %s queued maintenance send(s).", released)

        log.info("Send queue cycle started.")
        pending = await self.sends.fetch_for_status("pending", limit=50)
        log.info("Pending sends found: %s", len(pending))
        if self.counting_service is not None:
            queued_maintenance = await self.sends.fetch_for_status("queued_maintenance", limit=50)
            recovery_candidates = list(pending) + list(queued_maintenance)
            for send in recovery_candidates:
                try:
                    await self.counting_service.process_send_for_count_rescue(send)
                except Exception:
                    log.exception(
                        "Count rescue evaluation failed for send_id=%s guild_id=%s.",
                        send.id,
                        send.guild_id,
                    )

        for send in pending:
            ok = await self._post_send(send)
            if ok:
                log.info("Posted send id=%s guild_id=%s", send.id, send.guild_id)
                try:
                    log.info("Refreshing leaderboard for guild_id=%s", send.guild_id)
                    await self.leaderboard_service.refresh_guild(send.guild_id)
                except Exception:
                    log.exception(
                        "Leaderboard refresh failed after posted send_id=%s guild_id=%s.",
                        send.id,
                        send.guild_id,
                    )

        if await self.maintenance.consume_leaderboard_refresh_request():
            await self.leaderboard_service.refresh_all_guilds()

    async def process_idle_tasks(self) -> None:
        """Run slow maintenance work without sweeping pending sends every tick."""
        if not await self.maintenance.is_enabled():
            released = await self.sends.release_queued_maintenance()
            if released:
                log.info("Released %s queued maintenance send(s).", released)
                await self.process_cycle()

        if await self.maintenance.consume_leaderboard_refresh_request():
            await self.leaderboard_service.refresh_all_guilds()

    async def notify_send(self, send_id: int) -> None:
        self._notification_queue().put_nowait(int(send_id))

    async def process_send_by_id(self, send_id: int) -> bool:
        send = await self.sends.get(int(send_id))
        if send is None:
            log.warning("Send notification ignored because send_id=%s was not found.", send_id)
            return False
        return await self._process_send_record(send)

    async def _process_send_record(self, send) -> bool:
        if self.counting_service is not None:
            try:
                await self.counting_service.process_send_for_count_rescue(send)
            except Exception:
                log.exception(
                    "Count rescue evaluation failed for send_id=%s guild_id=%s.",
                    send.id,
                    send.guild_id,
                )

        if send.discord_post_status == "queued_maintenance":
            if await self.maintenance.is_enabled():
                log.info(
                    "Send id=%s guild_id=%s is queued until maintenance ends.",
                    send.id,
                    send.guild_id,
                )
                return False
            released = await self.sends.release_queued_maintenance()
            if released:
                log.info("Released %s queued maintenance send(s).", released)
            send = await self.sends.get(send.id)
            if send is None:
                return False

        if send.discord_post_status != "pending":
            log.info(
                "Send notification ignored for send_id=%s guild_id=%s status=%s.",
                send.id,
                send.guild_id,
                send.discord_post_status,
            )
            return False

        ok = await self._post_send(send)
        if ok:
            log.info("Posted send id=%s guild_id=%s", send.id, send.guild_id)
            try:
                log.info("Refreshing leaderboard for guild_id=%s", send.guild_id)
                await self.leaderboard_service.refresh_guild(send.guild_id)
            except Exception:
                log.exception(
                    "Leaderboard refresh failed after posted send_id=%s guild_id=%s.",
                    send.id,
                    send.guild_id,
                )
        return ok

    async def _post_send(self, send) -> bool:
        settings = await self.guild_settings.get(send.guild_id)
        if settings is None or settings.send_track_channel_id is None:
            await self.sends.mark_failed(send.id, error="Missing send tracking channel configuration.")
            return False

        guild = self.bot.get_guild(send.guild_id)
        if guild is None:
            await self.sends.mark_failed(send.id, error="Guild not available to bot.")
            return False

        channel = guild.get_channel(settings.send_track_channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(settings.send_track_channel_id)
            except (discord.NotFound, discord.HTTPException) as exc:
                await self.sends.mark_failed(send.id, error=f"Send tracking channel unavailable: {exc}")
                return False

        if not isinstance(channel, discord.TextChannel):
            await self.sends.mark_failed(send.id, error="Configured send tracking channel is not a text channel.")
            return False

        previous_leader = await self.leaderboard_service.get_current_leader(send.guild_id)
        try:
            msg = send_card(
                send=send,
                domme_label=f"<@{send.domme_user_id}>",
                sub_display=build_sub_display(
                    send,
                    test_gifter_usernames=self.test_gifter_usernames,
                ),
            )
            message = await channel.send(**msg.send_kwargs())
        except discord.HTTPException as exc:
            await self.sends.mark_failed(send.id, error=f"Discord post failed: {exc}")
            return False

        await self.sends.mark_posted(send.id, message_id=message.id)
        log.info("Marked send posted id=%s message_id=%s", send.id, message.id)
        try:
            await self._unlock_send_achievements(
                send,
                previous_leader_user_id=previous_leader.user_id if previous_leader is not None else None,
                announce_channel=channel,
            )
        except Exception:
            log.exception(
                "Achievement unlock evaluation failed for send_id=%s guild_id=%s.",
                send.id,
                send.guild_id,
            )
        try:
            await self.leaderboard_service.maybe_post_leader_alert(
                send.guild_id,
                previous_leader_user_id=previous_leader.user_id if previous_leader is not None else None,
            )
        except Exception:
            log.exception(
                "Leader alert failed for send_id=%s guild_id=%s after successful send post.",
                send.id,
                send.guild_id,
            )
        return True

    async def _unlock_send_achievements(
        self,
        send,
        *,
        previous_leader_user_id: int | None,
        announce_channel: discord.TextChannel | None,
    ) -> None:
        if self.achievements is None:
            return

        guild_id = send.guild_id
        domme_user_id = send.domme_user_id
        guild = self.bot.get_guild(guild_id)

        def _unlock_display_name(user_id: int) -> str:
            member = guild.get_member(user_id) if guild is not None else None
            if member is not None:
                return member.display_name
            return f"<@{user_id}>"

        def _announce_callback(user_id: int):
            if announce_channel is None:
                return None

            async def _callback(achievement) -> None:
                await announce_channel.send(
                    **achievement_unlocked_card(
                        achievement,
                        unlocked_by_display_name=_unlock_display_name(user_id),
                        unlocked_by_user_id=user_id,
                    ).send_kwargs()
                )

            return _callback

        async def _unlock(
            *,
            user_id: int,
            achievement_key: str,
            source: str,
            metadata: dict | None = None,
        ) -> bool:
            return await self.achievements.unlock_achievement(
                guild_id=guild_id,
                discord_user_id=user_id,
                achievement_key=achievement_key,
                source=source,
                metadata=metadata,
                on_unlocked=_announce_callback(user_id),
            )

        if send.is_test_send:
            await _unlock(
                user_id=domme_user_id,
                achievement_key="domme_first_test_send",
                source="send:test",
            )
        else:
            await _unlock(
                user_id=domme_user_id,
                achievement_key="domme_first_tracked_send",
                source="send:posted",
            )

        if send.source.startswith("manual:"):
            await _unlock(
                user_id=domme_user_id,
                achievement_key="domme_manual_send",
                source="send:manual",
            )

        if send.source == "throne_webhook" and not send.is_test_send:
            await _unlock(
                user_id=domme_user_id,
                achievement_key="throne_first_real_auto_send",
                source="send:throne",
            )

        if self.leaderboards is None:
            return

        stats = await self.leaderboards.get_domme_stats(
            guild_id,
            domme_user_id=domme_user_id,
            include_test_sends=self.include_test_sends,
            test_gifter_usernames=self.test_gifter_usernames,
            owner_test_user_id=self.owner_test_user_id,
        )
        if not send.is_test_send:
            if stats.total_cents >= 10_000:
                await _unlock(
                    user_id=domme_user_id,
                    achievement_key="domme_100_tracked",
                    source="send:posted",
                )
            if stats.total_cents >= 100_000:
                await _unlock(
                    user_id=domme_user_id,
                    achievement_key="domme_1000_tracked",
                    source="send:posted",
                )
            if stats.total_cents >= 500_000:
                await _unlock(
                    user_id=domme_user_id,
                    achievement_key="domme_5000_tracked",
                    source="send:posted",
                )

        for threshold, key in ((10, "domme_10_sends_received"), (50, "domme_50_sends_received"), (100, "domme_100_sends_received")):
            if stats.send_count >= threshold:
                await _unlock(
                    user_id=domme_user_id,
                    achievement_key=key,
                    source="send:posted",
                )

        rank = await self.leaderboards.get_domme_rank(
            guild_id,
            domme_user_id=domme_user_id,
            include_test_sends=self.include_test_sends,
            test_gifter_usernames=self.test_gifter_usernames,
            owner_test_user_id=self.owner_test_user_id,
        )
        if rank is not None and rank <= 10:
            await _unlock(
                user_id=domme_user_id,
                achievement_key="domme_top_10",
                source="leaderboard:rank",
                metadata={"rank": rank},
            )
        if rank == 1:
            already_unlocked = await self.achievements.get_user_achievement_keys(
                guild_id=guild_id,
                discord_user_id=domme_user_id,
            )
            await self.achievements.unlock_achievement(
                guild_id=guild_id,
                discord_user_id=domme_user_id,
                achievement_key="domme_first_place",
                source="leaderboard:rank",
                on_unlocked=_announce_callback(domme_user_id),
            )
            if (
                previous_leader_user_id is not None
                and previous_leader_user_id != domme_user_id
                and "domme_first_place" in already_unlocked
            ):
                await _unlock(
                    user_id=domme_user_id,
                    achievement_key="domme_regain_first",
                    source="leaderboard:rank",
                )

        sub_user_id = send.sub_user_id
        if sub_user_id is None:
            return

        await _unlock(
            user_id=sub_user_id,
            achievement_key="sub_first_send",
            source="send:posted",
        )

        sub_stats = await self.leaderboards.get_sub_stats(
            guild_id,
            sub_user_id=sub_user_id,
            include_test_sends=self.include_test_sends,
            test_gifter_usernames=self.test_gifter_usernames,
            owner_test_user_id=self.owner_test_user_id,
        )
        if sub_stats.total_cents >= 10_000:
            await _unlock(
                user_id=sub_user_id,
                achievement_key="sub_100_sent",
                source="send:posted",
            )
        if sub_stats.total_cents >= 100_000:
            await _unlock(
                user_id=sub_user_id,
                achievement_key="sub_1000_sent",
                source="send:posted",
            )
        if sub_stats.total_cents >= 500_000:
            await _unlock(
                user_id=sub_user_id,
                achievement_key="sub_5000_sent",
                source="send:posted",
            )

        for threshold, key in ((10, "sub_10_sends"), (50, "sub_50_sends"), (100, "sub_100_sends")):
            if sub_stats.send_count >= threshold:
                await _unlock(
                    user_id=sub_user_id,
                    achievement_key=key,
                    source="send:posted",
                )

        current_leader = await self.leaderboard_service.get_current_leader(guild_id)
        if (
            current_leader is not None
            and current_leader.user_id == domme_user_id
            and previous_leader_user_id is not None
            and previous_leader_user_id != domme_user_id
        ):
            await _unlock(
                user_id=sub_user_id,
                achievement_key="sub_kingmaker",
                source="leaderboard:leader_change",
                metadata={"new_leader_user_id": domme_user_id},
            )
