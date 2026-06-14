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
    terms_accepted_card,
    terms_declined_card,
    terms_dm_blocked_card,
    terms_prompt_card,
)

if TYPE_CHECKING:
    from rob.discord.client import RobBot


log = logging.getLogger(__name__)

ALLOWED_TERMS_COMMANDS = frozenset({"termsreset"})


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

    def _can_reset_terms(self, user: discord.abc.User) -> bool:
        service = self.service
        if service is not None and service.owner_user_id is not None and user.id == service.owner_user_id:
            return True
        permissions = getattr(user, "guild_permissions", None)
        if permissions is None:
            return False
        return bool(
            getattr(permissions, "administrator", False)
            or getattr(permissions, "manage_guild", False)
        )

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
            "server and I'll send a fresh copy."
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
            version=service.terms_version,
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
        name="termsreset",
        description="Reset a user's Terms acceptance state for testing.",
    )
    @app_commands.describe(user="Optional user to reset. Defaults to yourself.")
    async def terms_reset(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
    ) -> None:
        service = self.service
        if service is None:
            await interaction.response.send_message(
                "Rob couldn't load the Terms tools right now.",
                ephemeral=True,
            )
            return
        if interaction.guild is None or not service.is_enabled_for(interaction.guild_id):
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return
        if interaction.user is None or not self._can_reset_terms(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner or a server manager can run this command.",
                ephemeral=True,
            )
            return

        target = user or interaction.user
        had_state = await service.reset_for_user(discord_user_id=target.id)
        if target.id == interaction.user.id:
            if had_state:
                message = (
                    "Your Terms acceptance state has been reset. The next gated "
                    "command you run will send a fresh Terms DM."
                )
            else:
                message = (
                    "You didn't have an active Terms state, so there was nothing "
                    "to clear. The next gated command you run will still send a "
                    "fresh Terms DM."
                )
        else:
            mention = getattr(target, "mention", None) or self._display_name(target)
            if had_state:
                message = (
                    f"Reset Terms acceptance for {mention}. Their next gated "
                    "command will send a fresh Terms DM."
                )
            else:
                message = (
                    f"{mention} didn't have an active Terms state, so there was "
                    "nothing to clear. Their next gated command will still send a "
                    "fresh Terms DM."
                )
        await interaction.response.send_message(message, ephemeral=True)
