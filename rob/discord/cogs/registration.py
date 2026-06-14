from __future__ import annotations

from typing import TYPE_CHECKING
import inspect
import logging

import discord
from discord import app_commands
from discord.ext import commands

from rob.discord.permissions import member_has_role
from rob.ui.cards.errors import error_card, error_permission
from rob.ui.cards.registration import registration_card
from rob.ui.copy import (
    PERMISSION_ROLE_MISSING,
    PERMISSION_ROLE_NOT_CONFIGURED,
)
from rob.utils.text import collapse_whitespace

if TYPE_CHECKING:
    from rob.discord.client import RobBot


log = logging.getLogger(__name__)

_RESERVED_SUB_NAMES = {"anonymous", "anon", "private", "hidden"}


def _dm_blocked_error_card():
    return error_card(
        "You're registered, but Rob couldn't DM you.",
        "This usually means Discord blocked the DM. Please check:\n\n"
        "- Server Privacy Settings → Allow direct messages from server members\n"
        "- You have not blocked this bot\n"
        "- Your Discord privacy settings allow bot/member DMs\n\n"
        "Once fixed, run /register domme again.",
    )


class RegistrationCog(commands.Cog):
    register_group = app_commands.Group(name="register", description="Register as a Dom/me or Sub.")

    def __init__(self, bot: RobBot) -> None:
        self.bot = bot
        self._active_domme_submission_keys: set[tuple[int, int]] = set()

    async def _require_configured_role(
        self,
        interaction: discord.Interaction,
        *,
        role_id: int | None,
    ) -> bool:
        if role_id is None:
            await interaction.response.send_message(
                **error_permission(PERMISSION_ROLE_NOT_CONFIGURED).send_kwargs(),
                ephemeral=True,
            )
            return False
        if not member_has_role(interaction.user, role_id):
            await interaction.response.send_message(
                **error_permission(PERMISSION_ROLE_MISSING).send_kwargs(),
                ephemeral=True,
            )
            return False
        return True

    async def _registrations_blocked_for_guild(self, guild_id: int | None) -> bool:
        maintenance = getattr(self.bot, "maintenance_service", None)
        if maintenance is None:
            return False
        checker = getattr(maintenance, "registrations_blocked_for_guild", None)
        if checker is not None:
            result = checker(guild_id)
            if inspect.isawaitable(result):
                return bool(await result)
        legacy_checker = getattr(maintenance, "registrations_blocked", None)
        if legacy_checker is not None:
            result = legacy_checker()
            if inspect.isawaitable(result):
                return bool(await result)
            if isinstance(result, bool):
                return result
        return False

    async def _require_registration_available(self, interaction: discord.Interaction) -> bool:
        if not await self._registrations_blocked_for_guild(interaction.guild.id if interaction.guild else None):
            return True
        await interaction.response.send_message(
            **error_card(
                "Rob is under maintenance right now.",
                "Dom/me and Sub registration are paused until the maintenance window is over. Counting and approved manual send work can still continue.",
            ).send_kwargs(),
            ephemeral=True,
        )
        return False

    @register_group.command(name="domme", description="Register a Dom/me Throne profile.")
    async def register_domme(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(**error_card("This command can only be used in a server.").send_kwargs(), ephemeral=True)
            return
        if not await self._require_registration_available(interaction):
            return
        log.info(
            "/register domme invoked guild_id=%s discord_user_id=%s",
            interaction.guild.id,
            interaction.user.id,
        )

        settings = await self.bot.guild_settings_repo.get(interaction.guild.id)
        if not await self._require_configured_role(
            interaction,
            role_id=settings.domme_role_id if settings is not None else None,
        ):
            return

        # Route to the DM-first onboarding flow.
        dm_cog = self.bot.get_cog("DMOnboardingCog")
        if dm_cog is None:
            log.error(
                "/register domme: DMOnboardingCog not loaded guild_id=%s",
                interaction.guild.id,
            )
            await interaction.response.send_message(
                **error_card(
                    "Rob couldn't start setup.",
                    "The onboarding system isn't available right now. Please ask staff.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return

        ok, _message, error_text = await dm_cog.start_onboarding_dm(
            user=interaction.user,
            guild_id=interaction.guild.id,
        )
        if ok:
            await interaction.response.send_message(
                **registration_card(
                    title="Rob | Setup Sent",
                    summary=(
                        "I've sent your setup to your DMs. Open that "
                        "message and tap **Enter Throne details** to begin."
                    ),
                ).send_kwargs(),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                **_dm_blocked_error_card().send_kwargs(),
                ephemeral=True,
            )
            if error_text:
                log.info(
                    "DM onboarding start failed guild_id=%s user_id=%s: %s",
                    interaction.guild.id,
                    interaction.user.id,
                    error_text,
                )

    @register_group.command(name="sub", description="Register a sending name to claim sends.")
    async def register_sub(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(**error_card("This command can only be used in a server.").send_kwargs(), ephemeral=True)
            return
        if not await self._require_registration_available(interaction):
            return

        settings = await self.bot.guild_settings_repo.get(interaction.guild.id)
        if not await self._require_configured_role(
            interaction,
            role_id=settings.sub_role_id if settings is not None else None,
        ):
            return

        await interaction.response.send_modal(
            _SubRegistrationModal(
                cog=self,
                guild_id=interaction.guild.id,
                discord_user_id=interaction.user.id,
            )
        )


class _SubRegistrationModal(discord.ui.Modal, title="Rob | Sub Registration"):
    send_name_1 = discord.ui.TextInput(
        label="Throne username / send name 1",
        placeholder="Required",
        required=True,
        max_length=120,
    )
    send_name_2 = discord.ui.TextInput(
        label="Throne username / send name 2",
        placeholder="Optional",
        required=False,
        max_length=120,
    )
    send_name_3 = discord.ui.TextInput(
        label="Throne username / send name 3",
        placeholder="Optional",
        required=False,
        max_length=120,
    )

    def __init__(
        self,
        *,
        cog: RegistrationCog,
        guild_id: int,
        discord_user_id: int,
    ) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.guild_id = guild_id
        self.discord_user_id = discord_user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user is None or interaction.user.id != self.discord_user_id:
            await interaction.response.send_message(
                **error_card("This registration flow belongs to someone else.").send_kwargs(),
                ephemeral=True,
            )
            return

        raw_names = [
            str(self.send_name_1.value),
            str(self.send_name_2.value),
            str(self.send_name_3.value),
        ]
        cleaned = [collapse_whitespace(value.strip()) for value in raw_names if value and value.strip()]
        if not cleaned:
            await interaction.response.send_message(
                **error_card("Sub registration could not be completed.", "At least one sending name is required.").send_kwargs(),
                ephemeral=True,
            )
            return
        if len(cleaned) > 3:
            await interaction.response.send_message(
                **error_card("Sub registration could not be completed.", "You can register up to 3 sending names.").send_kwargs(),
                ephemeral=True,
            )
            return

        seen: set[str] = set()
        for name in cleaned:
            lowered = name.casefold()
            if lowered in seen:
                await interaction.response.send_message(
                    **error_card("Sub registration could not be completed.", "Duplicate sending names are not allowed.").send_kwargs(),
                    ephemeral=True,
                )
                return
            if lowered in _RESERVED_SUB_NAMES:
                await interaction.response.send_message(
                    **error_card("Sub registration could not be completed.", f"'{name}' is reserved and cannot be claimed.").send_kwargs(),
                    ephemeral=True,
                )
                return
            seen.add(lowered)

        await interaction.response.defer(ephemeral=True)
        if await self.cog._registrations_blocked_for_guild(self.guild_id):
            await interaction.followup.send(
                **error_card(
                    "Rob is under maintenance right now.",
                    "Sub registration is paused until the maintenance window is over.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return
        try:
            result = await self.cog.bot.registration_service.register_sub(
                guild_id=self.guild_id,
                discord_user_id=self.discord_user_id,
                send_names=cleaned,
            )
        except ValueError as exc:
            await interaction.followup.send(
                **error_card("Sub registration could not be completed.", str(exc)).send_kwargs(),
                ephemeral=True,
            )
            return

        details = [(f"Tracked Name {idx + 1}", name) for idx, name in enumerate(result.send_names)]
        await interaction.followup.send(
            **registration_card(
                title="Rob | Sub Registered",
                summary="Your send-claim names are now active.",
                details=details,
            ).send_kwargs(),
            ephemeral=True,
        )
