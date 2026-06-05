from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from rob.services.terms_service import TermsError
from rob.ui.cards.terms import (
    AcceptButton,
    DeclineButton,
    ID_TERMS_ACCEPT,
    ID_TERMS_DECLINE,
    current_privacy_card,
    current_terms_card,
    terms_accepted_card,
    terms_declined_card,
    terms_dm_blocked_card,
    terms_prompt_card,
)

if TYPE_CHECKING:
    from rob.discord.client import RobBot


log = logging.getLogger(__name__)

ALLOWED_TERMS_COMMANDS = frozenset({"terms", "privacy"})


class _PersistentTermsView(discord.ui.View):
    def __init__(self, cog: "TermsCog") -> None:
        super().__init__(timeout=None)
        self.add_item(AcceptButton(cog))
        self.add_item(DeclineButton(cog))


class TermsCog(commands.Cog):
    def __init__(self, bot: "RobBot") -> None:
        self.bot = bot

    @property
    def service(self):
        return getattr(self.bot, "terms_service", None)

    def register_persistent_views(self) -> None:
        try:
            self.bot.add_view(_PersistentTermsView(self))
        except Exception:
            log.warning(
                "Failed to register persistent Terms view; post-restart interactions may not route.",
                exc_info=True,
            )
            return
        log.info("Registered persistent Terms view")

    @staticmethod
    def is_terms_command_name(command_name: str | None) -> bool:
        if not command_name:
            return False
        return command_name in ALLOWED_TERMS_COMMANDS

    @staticmethod
    def is_terms_custom_id(custom_id: str | None) -> bool:
        return custom_id in {ID_TERMS_ACCEPT, ID_TERMS_DECLINE}

    @classmethod
    def is_terms_interaction(cls, interaction: discord.Interaction) -> bool:
        command_name = getattr(interaction.command, "qualified_name", None)
        if cls.is_terms_command_name(command_name):
            return True
        data = getattr(interaction, "data", None) or {}
        custom_id = (
            data.get("custom_id")
            if isinstance(data, dict)
            else getattr(data, "custom_id", None)
        )
        return cls.is_terms_custom_id(custom_id)

    @staticmethod
    def _display_name(user: discord.abc.User) -> str:
        display_name = getattr(user, "display_name", None)
        if display_name:
            return display_name
        return user.name

    def _welcome_text(self, *, name: str) -> str:
        return (
            f"Hey {name}! Welcome to Rob, VIB's very own Discord bot!\n\n"
            "Before you can use Rob's features, you'll need to agree to the "
            "Terms of Use and Privacy Notice I've sent to you in a DM.\n\n"
            "Once accepted, you'll be all good to use Rob!"
        )

    def _pending_text(self, *, name: str) -> str:
        owner_text = (
            f"feel free to DM {self.service.owner_mention} for assistance."
            if self.service is not None
            else "feel free to DM the bot owner for assistance."
        )
        return (
            f"Hey {name}! It looks like you're still yet to accept or decline "
            "Rob's Terms of Use and Privacy Notice.\n\n"
            "I've already sent them to you in a DM. Once accepted, you'll be "
            "able to run this command without this pesky notice!\n\n"
            f"-# If you've already accepted and you're still seeing this, {owner_text}"
        )

    @staticmethod
    def _stale_text() -> str:
        return (
            "That Terms message is no longer active. Run any Rob command in the "
            "test server and I'll send a fresh copy."
        )

    async def _send_terms_dm(
        self,
        *,
        user: discord.abc.User,
    ) -> tuple[bool, str | None]:
        service = self.service
        if service is None:
            return False, "unavailable"

        rendered = terms_prompt_card(
            terms_url=service.terms_url,
            privacy_url=service.privacy_url,
            cog=self,
        )
        try:
            message = await user.send(**rendered.send_kwargs())
        except discord.Forbidden:
            log.warning("Terms DM blocked for user_id=%s", user.id)
            return False, "dm_blocked"
        except discord.HTTPException:
            log.exception("Terms DM send failed for user_id=%s", user.id)
            return False, "dm_blocked"

        try:
            await service.record_prompt(
                discord_user_id=user.id,
                dm_channel_id=int(message.channel.id),
                dm_message_id=int(message.id),
            )
        except Exception:
            log.exception("Failed to persist Terms prompt for user_id=%s", user.id)
            return False, "internal"
        return True, None

    async def ensure_terms_acceptance(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        service = self.service
        if service is None or interaction.user is None:
            return True
        if not service.is_enabled_for(interaction.guild_id):
            return True

        gate_status = await service.gate_status_for_user(interaction.user.id)
        display_name = self._display_name(interaction.user)

        if gate_status == "accepted":
            return True

        if gate_status == "pending":
            await interaction.response.send_message(
                self._pending_text(name=display_name),
                ephemeral=True,
            )
            return False

        ok, error_kind = await self._send_terms_dm(user=interaction.user)
        if not ok:
            if error_kind == "internal":
                await interaction.response.send_message(
                    "Rob couldn't start the Terms flow right now. Please try again in a moment.",
                    ephemeral=True,
                )
                return False
            await interaction.response.send_message(
                **terms_dm_blocked_card(name=display_name).send_kwargs(),
                ephemeral=True,
            )
            return False

        await interaction.response.send_message(
            self._welcome_text(name=display_name),
            ephemeral=True,
        )
        return False

    async def _get_active_state_for_interaction(
        self,
        interaction: discord.Interaction,
    ):
        service = self.service
        if service is None or interaction.user is None:
            return None

        state = await service.get_state(interaction.user.id)
        message_id = getattr(interaction.message, "id", None)
        if state is None or state.dm_message_id is None:
            return None
        if message_id is not None and int(message_id) != int(state.dm_message_id):
            return None
        return state

    async def handle_accept(self, interaction: discord.Interaction) -> None:
        service = self.service
        if service is None or interaction.user is None:
            await interaction.response.send_message(self._stale_text(), ephemeral=True)
            return

        state = await self._get_active_state_for_interaction(interaction)
        if state is None:
            await interaction.response.send_message(self._stale_text(), ephemeral=True)
            return

        try:
            await service.accept(discord_user_id=interaction.user.id)
        except TermsError:
            await interaction.response.send_message(self._stale_text(), ephemeral=True)
            return

        await interaction.response.edit_message(**terms_accepted_card().edit_kwargs())

    async def handle_decline(self, interaction: discord.Interaction) -> None:
        service = self.service
        if service is None or interaction.user is None:
            await interaction.response.send_message(self._stale_text(), ephemeral=True)
            return

        state = await self._get_active_state_for_interaction(interaction)
        if state is None:
            await interaction.response.send_message(self._stale_text(), ephemeral=True)
            return

        try:
            await service.decline(discord_user_id=interaction.user.id)
        except TermsError:
            await interaction.response.send_message(self._stale_text(), ephemeral=True)
            return

        await interaction.response.edit_message(**terms_declined_card().edit_kwargs())

    @app_commands.command(
        name="terms",
        description="View Rob's current Terms of Use.",
    )
    async def terms(self, interaction: discord.Interaction) -> None:
        service = self.service
        if service is None:
            await interaction.response.send_message(
                "Rob couldn't load the Terms right now.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            **current_terms_card(
                terms_version=service.terms_version,
                terms_url=service.terms_url,
            ).send_kwargs(),
            ephemeral=True,
        )

    @app_commands.command(
        name="privacy",
        description="View Rob's current Privacy Notice.",
    )
    async def privacy(self, interaction: discord.Interaction) -> None:
        service = self.service
        if service is None:
            await interaction.response.send_message(
                "Rob couldn't load the Privacy Notice right now.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            **current_privacy_card(
                terms_version=service.terms_version,
                privacy_url=service.privacy_url,
            ).send_kwargs(),
            ephemeral=True,
        )
