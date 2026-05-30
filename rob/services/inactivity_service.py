from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord

from rob.database.repositories.bot_state import BotStateRepository
from rob.database.repositories.guild_settings import GuildSettingsRepository
from rob.services.maintenance_service import MaintenanceService
from rob.ui.cards.inactivity import final_inactivity_warning_card, first_inactivity_warning_card

log = logging.getLogger(__name__)

_STATE_UNSET = object()


@dataclass(frozen=True)
class InactivitySnapshot:
    member: discord.Member
    remove_at: datetime


class InactivityService:
    def __init__(
        self,
        *,
        bot_state: BotStateRepository,
        guild_settings: GuildSettingsRepository,
        enabled_default: bool,
        new_member_grace_days: int,
        assignment_grace_days: int,
        bootstrap_grace_days: int,
        final_notice_days: int,
        notice_channel_id: int | None,
        maintenance: MaintenanceService | None = None,
    ) -> None:
        self.bot_state = bot_state
        self.guild_settings = guild_settings
        self.enabled_default = enabled_default
        self.new_member_grace = timedelta(days=max(1, new_member_grace_days))
        self.assignment_grace = timedelta(days=max(1, assignment_grace_days))
        self.bootstrap_grace = timedelta(days=max(1, bootstrap_grace_days))
        self.final_notice_window = timedelta(days=max(1, final_notice_days))
        self.notice_channel_id = notice_channel_id
        self.maintenance = maintenance

    def _enabled_key(self, guild_id: int) -> str:
        return f"inactivity:{guild_id}:enabled"

    def _bootstrapped_key(self, guild_id: int) -> str:
        return f"inactivity:{guild_id}:bootstrapped_at"

    def _member_prefix(self, guild_id: int, member_id: int) -> str:
        return f"inactivity:{guild_id}:user:{member_id}"

    def _member_keys(self, guild_id: int, member_id: int) -> dict[str, str]:
        prefix = self._member_prefix(guild_id, member_id)
        return {
            "assigned_at": f"{prefix}:assigned_at",
            "remove_at": f"{prefix}:remove_at",
            "initial_notice_sent": f"{prefix}:initial_notice_sent",
            "final_notice_sent": f"{prefix}:final_notice_sent",
        }

    @staticmethod
    def _parse_bool(raw: str | None, *, default: bool = False) -> bool:
        if raw is None:
            return default
        lowered = raw.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _parse_optional_datetime(raw: str | None) -> datetime | None:
        if raw is None:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _is_eligible_member(member: discord.Member) -> bool:
        return not member.bot

    def _notice_channel_hint(self) -> str:
        if self.notice_channel_id:
            return f"<#{self.notice_channel_id}>"
        return "the server chat"

    def _first_warning_due_at(self, assigned_at: datetime, remove_at: datetime) -> datetime:
        return min(assigned_at + self.new_member_grace, remove_at)

    def _build_first_notice(self, member: discord.Member, remove_at: datetime, guild_name: str) -> dict[str, object]:
        ts = int(remove_at.timestamp())
        rendered = first_inactivity_warning_card(
            display_name=(member.nick or member.display_name or member.name).strip() or member.name,
            server_name=guild_name,
            remove_at_unix=ts,
            main_chat_channel=self._notice_channel_hint(),
        )
        return rendered.send_kwargs()

    def _build_final_notice(self, member: discord.Member, remove_at: datetime, guild_name: str) -> dict[str, object]:
        ts = int(remove_at.timestamp())
        rendered = final_inactivity_warning_card(
            display_name=(member.nick or member.display_name or member.name).strip() or member.name,
            server_name=guild_name,
            remove_at_unix=ts,
            main_chat_channel=self._notice_channel_hint(),
        )
        return rendered.send_kwargs()

    async def _send_dm(self, member: discord.Member, *, message_kwargs: dict[str, object], label: str) -> None:
        try:
            await member.send(**message_kwargs)
            log.info("Sent inactivity %s DM to user_id=%s", label, member.id)
        except discord.Forbidden:
            log.info("Could not DM user_id=%s for inactivity %s (DMs closed).", member.id, label)
        except discord.HTTPException:
            log.warning("Failed to DM user_id=%s for inactivity %s", member.id, label, exc_info=True)

    async def is_enabled(self, guild_id: int) -> bool:
        value = await self.bot_state.get_text(self._enabled_key(guild_id))
        return self._parse_bool(value, default=self.enabled_default)

    async def set_enabled(self, guild_id: int, enabled: bool) -> None:
        await self.bot_state.set_value(self._enabled_key(guild_id), "true" if enabled else "false")

    async def _load_member_state(self, guild_id: int, member_id: int) -> dict[str, datetime | bool | None]:
        keys = self._member_keys(guild_id, member_id)
        values = await self.bot_state.get_values(list(keys.values()))
        return {
            "assigned_at": self._parse_optional_datetime(values.get(keys["assigned_at"])),
            "remove_at": self._parse_optional_datetime(values.get(keys["remove_at"])),
            "initial_notice_sent": self._parse_bool(values.get(keys["initial_notice_sent"]), default=False),
            "final_notice_sent": self._parse_bool(values.get(keys["final_notice_sent"]), default=False),
        }

    async def _save_member_state(self, guild_id: int, member_id: int, *, assigned_at: datetime | None | object = _STATE_UNSET, remove_at: datetime | None | object = _STATE_UNSET, initial_notice_sent: bool | None | object = _STATE_UNSET, final_notice_sent: bool | None | object = _STATE_UNSET) -> None:
        keys = self._member_keys(guild_id, member_id)
        values: dict[str, str | None] = {}
        if assigned_at is not _STATE_UNSET:
            values[keys["assigned_at"]] = assigned_at.isoformat() if isinstance(assigned_at, datetime) else None
        if remove_at is not _STATE_UNSET:
            values[keys["remove_at"]] = remove_at.isoformat() if isinstance(remove_at, datetime) else None
        if initial_notice_sent is not _STATE_UNSET:
            values[keys["initial_notice_sent"]] = ("true" if bool(initial_notice_sent) else "false") if isinstance(initial_notice_sent, bool) else None
        if final_notice_sent is not _STATE_UNSET:
            values[keys["final_notice_sent"]] = ("true" if bool(final_notice_sent) else "false") if isinstance(final_notice_sent, bool) else None
        await self.bot_state.set_values(values)

    async def clear_member_state(self, guild_id: int, member_id: int) -> None:
        await self._save_member_state(guild_id, member_id, assigned_at=None, remove_at=None, initial_notice_sent=None, final_notice_sent=None)

    async def process_guild(self, guild: discord.Guild, *, send_notifications: bool, perform_kicks: bool) -> list[InactivitySnapshot]:
        guild_id = guild.id
        if not await self.is_enabled(guild_id):
            return []
        if self.maintenance is not None and await self.maintenance.notifications_suppressed():
            send_notifications = False
            perform_kicks = False

        settings = await self.guild_settings.get(guild_id)
        if settings is None or settings.inactive_role_id is None:
            return []
        inactive_role = guild.get_role(settings.inactive_role_id)
        if inactive_role is None:
            return []

        members = [member for member in inactive_role.members if self._is_eligible_member(member)]
        if not members:
            return []

        now = datetime.now(timezone.utc)
        bootstrapped_at = self._parse_optional_datetime(await self.bot_state.get_text(self._bootstrapped_key(guild_id)))
        is_bootstrap_run = bootstrapped_at is None
        snapshots: list[InactivitySnapshot] = []

        for member in members:
            state = await self._load_member_state(guild_id, member.id)
            assigned_at = state["assigned_at"] if isinstance(state["assigned_at"], datetime) else None
            remove_at = state["remove_at"] if isinstance(state["remove_at"], datetime) else None
            initial_notice_sent = bool(state["initial_notice_sent"])
            final_notice_sent = bool(state["final_notice_sent"])

            if assigned_at is None or remove_at is None:
                if member.joined_at is not None and member.joined_at.tzinfo is not None and (now - member.joined_at) <= self.bootstrap_grace:
                    assigned_at = member.joined_at
                    remove_at = assigned_at + self.new_member_grace + self.assignment_grace
                else:
                    assigned_at = now
                    grace = self.bootstrap_grace if is_bootstrap_run else self.assignment_grace
                    remove_at = now + grace
                initial_notice_sent = False
                final_notice_sent = False
                await self._save_member_state(guild_id, member.id, assigned_at=assigned_at, remove_at=remove_at, initial_notice_sent=False, final_notice_sent=False)

            first_warning_due_at = self._first_warning_due_at(assigned_at, remove_at)
            if send_notifications and not initial_notice_sent and now >= first_warning_due_at:
                await self._send_dm(member, message_kwargs=self._build_first_notice(member, remove_at, guild.name), label="warning-notice")
                await self._save_member_state(guild_id, member.id, initial_notice_sent=True)

            if perform_kicks and now >= remove_at:
                try:
                    await member.kick(reason=f"Inactive member auto-removal scheduled at {remove_at.isoformat()}")
                    await self.clear_member_state(guild_id, member.id)
                    log.info("Kicked inactive member user_id=%s guild_id=%s", member.id, guild_id)
                except discord.Forbidden:
                    log.warning("Missing permission to kick inactive member user_id=%s guild_id=%s", member.id, guild_id)
                except discord.HTTPException:
                    log.warning("Failed to kick inactive member user_id=%s guild_id=%s", member.id, guild_id, exc_info=True)
                continue

            if send_notifications and not final_notice_sent and now < remove_at and (remove_at - now) <= self.final_notice_window:
                await self._send_dm(member, message_kwargs=self._build_final_notice(member, remove_at, guild.name), label="final-notice")
                await self._save_member_state(guild_id, member.id, final_notice_sent=True)

            snapshots.append(InactivitySnapshot(member=member, remove_at=remove_at))

        if is_bootstrap_run:
            await self.bot_state.set_value(self._bootstrapped_key(guild_id), now.isoformat())
        return snapshots
