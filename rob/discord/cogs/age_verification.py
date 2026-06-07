from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from rob.database.repositories.age_verification import STATUS_PENDING
from rob.discord.permissions import is_staff_member
from rob.services.age_verification_backend_client import (
    AgeVerificationBackendClientError,
)
from rob.ui.cards.age_verification import (
    age_verification_launch_card,
    age_verification_status_card,
)
from rob.ui.cards.errors import error_card

if TYPE_CHECKING:
    from rob.discord.client import RobBot


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgeVerificationRoleSyncResult:
    status: str
    action: str
    changed: bool
    error: str | None = None


class AgeVerificationCog(commands.Cog):
    def __init__(self, bot: "RobBot") -> None:
        self.bot = bot

    @property
    def service(self):
        return getattr(self.bot, "age_verification_service", None)

    @property
    def backend(self):
        return getattr(self.bot, "age_verification_backend_client", None)

    def _feature_enabled(self, guild_id: int | None) -> bool:
        service = self.service
        return service is not None and service.is_enabled_for(guild_id)

    async def _ensure_command_available(
        self,
        interaction: discord.Interaction,
        *,
        command_name: str,
    ) -> bool:
        guild_id = interaction.guild_id
        service = self.service

        if interaction.guild is None or guild_id is None:
            rendered = error_card(
                "Not available here",
                f"`/{command_name}` can't be used in DMs.",
            )
        elif service is None:
            rendered = error_card(
                "Age verification unavailable",
                "Rob couldn't load the age-verification tools right now.",
            )
        elif not service.enabled:
            rendered = error_card(
                "Age verification unavailable",
                "Rob's age-verification feature is currently disabled on this bot.",
            )
        elif service.is_enabled_for(guild_id):
            return True
        elif service.test_only:
            rendered = error_card(
                "Not available here",
                f"`/{command_name}` is only available in the test guild right now.",
            )
        else:
            rendered = error_card(
                "Not available here",
                f"`/{command_name}` isn't enabled in this server right now.",
            )

        await interaction.response.send_message(
            **rendered.send_kwargs(),
            ephemeral=True,
        )
        return False

    async def _require_staff(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        settings = await self.bot.vib_settings_repo.get(interaction.guild_id)
        if is_staff_member(interaction.user, settings):
            return True
        await interaction.response.send_message(
            **error_card(
                "Staff only",
                "Only staff or admins can manage age-verification decisions.",
            ).send_kwargs(),
            ephemeral=True,
        )
        return False

    @staticmethod
    def _subject_for_status(
        *,
        user: discord.abc.User,
        self_view: bool,
    ) -> str:
        if self_view:
            return "You"
        mention = getattr(user, "mention", None)
        if mention:
            return mention
        return getattr(user, "display_name", None) or user.name

    async def _sync_verified_role(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AgeVerificationRoleSyncResult:
        service = self.service
        if service is None:
            return AgeVerificationRoleSyncResult(
                status="unknown",
                action="none",
                changed=False,
                error="service_unavailable",
            )

        record = await service.get_status_record(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
        status = record.status if record is not None else "not_started"
        role_id = self.bot.settings.rob_age_verified_role_id
        if role_id is None:
            return AgeVerificationRoleSyncResult(
                status=status,
                action="none",
                changed=False,
                error="role_not_configured",
            )

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return AgeVerificationRoleSyncResult(
                status=status,
                action="none",
                changed=False,
                error="guild_not_cached",
            )
        role = guild.get_role(role_id)
        if role is None:
            return AgeVerificationRoleSyncResult(
                status=status,
                action="none",
                changed=False,
                error="role_not_found",
            )

        member = guild.get_member(discord_user_id)
        if member is None:
            try:
                member = await guild.fetch_member(discord_user_id)
            except (discord.NotFound, discord.HTTPException):
                member = None
        if member is None:
            return AgeVerificationRoleSyncResult(
                status=status,
                action="none",
                changed=False,
                error="member_not_found",
            )

        has_role = any(existing_role.id == role_id for existing_role in member.roles)
        should_have_role = service.should_have_verified_role(record)
        if should_have_role and not has_role:
            try:
                await member.add_roles(
                    role,
                    reason="Rob age verification approved.",
                )
            except (discord.Forbidden, discord.HTTPException):
                log.warning(
                    "Failed to add 18+ role guild_id=%s user_id=%s role_id=%s",
                    guild_id,
                    discord_user_id,
                    role_id,
                    exc_info=True,
                )
                return AgeVerificationRoleSyncResult(
                    status=status,
                    action="grant",
                    changed=False,
                    error="role_update_failed",
                )
            return AgeVerificationRoleSyncResult(
                status=status,
                action="grant",
                changed=True,
            )
        if not should_have_role and has_role:
            try:
                await member.remove_roles(
                    role,
                    reason="Rob age verification no longer active.",
                )
            except (discord.Forbidden, discord.HTTPException):
                log.warning(
                    "Failed to remove 18+ role guild_id=%s user_id=%s role_id=%s",
                    guild_id,
                    discord_user_id,
                    role_id,
                    exc_info=True,
                )
                return AgeVerificationRoleSyncResult(
                    status=status,
                    action="remove",
                    changed=False,
                    error="role_update_failed",
                )
            return AgeVerificationRoleSyncResult(
                status=status,
                action="remove",
                changed=True,
            )
        return AgeVerificationRoleSyncResult(
            status=status,
            action="none",
            changed=False,
        )

    async def on_age_verification_status_changed(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> AgeVerificationRoleSyncResult:
        return await self._sync_verified_role(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )

    async def _send_status_card(
        self,
        *,
        interaction: discord.Interaction,
        payload: dict,
        user: discord.abc.User,
        self_view: bool,
    ) -> None:
        subject = self._subject_for_status(user=user, self_view=self_view)
        await interaction.response.send_message(
            **age_verification_status_card(
                status=str(payload.get("status") or "not_started"),
                subject=subject,
                expires_at=payload.get("expires_at"),
                verification_url=payload.get("verification_url"),
                method=payload.get("yoti_method"),
                summary=payload.get("yoti_result_summary"),
                reason=payload.get("manual_review_reason"),
            ).send_kwargs(),
            ephemeral=True,
        )

    @app_commands.command(
        name="verify-age",
        description="Start the Yoti age-verification flow in the test server.",
    )
    async def verify_age(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_command_available(
            interaction,
            command_name="verify-age",
        ):
            return
        if interaction.user is None or self.backend is None:
            await interaction.response.send_message(
                **error_card(
                    "Age verification unavailable",
                    "Rob couldn't load the age-verification tools right now.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return
        try:
            payload = await self.backend.start(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
            )
        except AgeVerificationBackendClientError as exc:
            await interaction.response.send_message(
                **error_card("Age verification unavailable", str(exc)).send_kwargs(),
                ephemeral=True,
            )
            return

        status = str(payload.get("status") or "not_started")
        if status == STATUS_PENDING and payload.get("verification_url"):
            await interaction.response.send_message(
                **age_verification_launch_card(
                    verification_url=str(payload["verification_url"]),
                    expires_at=payload.get("expires_at"),
                ).send_kwargs(),
                ephemeral=True,
            )
            return
        await self._sync_verified_role(
            guild_id=interaction.guild_id,
            discord_user_id=interaction.user.id,
        )
        await self._send_status_card(
            interaction=interaction,
            payload=payload,
            user=interaction.user,
            self_view=True,
        )

    @app_commands.command(
        name="age-status",
        description="Check your current test-server age-verification status.",
    )
    async def age_status(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_command_available(
            interaction,
            command_name="age-status",
        ):
            return
        if interaction.user is None or self.backend is None:
            await interaction.response.send_message(
                **error_card(
                    "Age verification unavailable",
                    "Rob couldn't load the age-verification tools right now.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return
        try:
            payload = await self.backend.status(
                guild_id=interaction.guild_id,
                discord_user_id=interaction.user.id,
            )
        except AgeVerificationBackendClientError as exc:
            await interaction.response.send_message(
                **error_card("Age verification unavailable", str(exc)).send_kwargs(),
                ephemeral=True,
            )
            return
        await self._sync_verified_role(
            guild_id=interaction.guild_id,
            discord_user_id=interaction.user.id,
        )
        await self._send_status_card(
            interaction=interaction,
            payload=payload,
            user=interaction.user,
            self_view=True,
        )

    @app_commands.command(
        name="age-approve",
        description="Manually mark a member as verified 18+ in the test guild.",
    )
    async def age_approve(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        if not await self._ensure_command_available(
            interaction,
            command_name="age-approve",
        ):
            return
        if not await self._require_staff(interaction):
            return
        record = await self.service.manual_approve(
            guild_id=interaction.guild_id,
            discord_user_id=user.id,
            staff_user_id=interaction.user.id if interaction.user else None,
            reason=reason,
        )
        sync = await self._sync_verified_role(
            guild_id=interaction.guild_id,
            discord_user_id=user.id,
        )
        detail = (
            "Rob marked them as verified 18+."
            if sync.error is None
            else f"Rob marked them as verified 18+, but role sync reported `{sync.error}`."
        )
        await interaction.response.send_message(
            **age_verification_status_card(
                status=record.status,
                subject=user.mention,
                expires_at=record.expires_at,
                method=record.yoti_method,
                summary=detail,
                reason=record.manual_review_reason,
            ).send_kwargs(),
            ephemeral=True,
        )

    @app_commands.command(
        name="age-reject",
        description="Manually reject a member's age verification in the test guild.",
    )
    async def age_reject(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        if not await self._ensure_command_available(
            interaction,
            command_name="age-reject",
        ):
            return
        if not await self._require_staff(interaction):
            return
        record = await self.service.manual_reject(
            guild_id=interaction.guild_id,
            discord_user_id=user.id,
            staff_user_id=interaction.user.id if interaction.user else None,
            reason=reason,
        )
        sync = await self._sync_verified_role(
            guild_id=interaction.guild_id,
            discord_user_id=user.id,
        )
        detail = (
            "Rob marked them as not verified."
            if sync.error is None
            else f"Rob marked them as not verified, but role sync reported `{sync.error}`."
        )
        await interaction.response.send_message(
            **age_verification_status_card(
                status=record.status,
                subject=user.mention,
                expires_at=record.expires_at,
                method=record.yoti_method,
                summary=detail,
                reason=record.manual_review_reason,
            ).send_kwargs(),
            ephemeral=True,
        )

    @app_commands.command(
        name="age-revoke",
        description="Revoke a member's verified 18+ status in the test guild.",
    )
    async def age_revoke(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        if not await self._ensure_command_available(
            interaction,
            command_name="age-revoke",
        ):
            return
        if not await self._require_staff(interaction):
            return
        record = await self.service.revoke(
            guild_id=interaction.guild_id,
            discord_user_id=user.id,
            staff_user_id=interaction.user.id if interaction.user else None,
            reason=reason,
        )
        sync = await self._sync_verified_role(
            guild_id=interaction.guild_id,
            discord_user_id=user.id,
        )
        detail = (
            "Rob revoked their verified status."
            if sync.error is None
            else f"Rob revoked their verified status, but role sync reported `{sync.error}`."
        )
        await interaction.response.send_message(
            **age_verification_status_card(
                status=record.status,
                subject=user.mention,
                expires_at=record.expires_at,
                method=record.yoti_method,
                summary=detail,
                reason=record.manual_review_reason,
            ).send_kwargs(),
            ephemeral=True,
        )
