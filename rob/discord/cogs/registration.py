from __future__ import annotations

from typing import TYPE_CHECKING
import logging

import discord
from discord import app_commands
from discord.ext import commands

from rob.discord.permissions import member_has_role
from rob.ui.cards.errors import error_card, error_permission
from rob.ui.cards.registration import domme_registered_card, registration_card, throne_setup_card
from rob.ui.copy import (
    PERMISSION_ROLE_MISSING,
    PERMISSION_ROLE_NOT_CONFIGURED,
    THRONE_SETUP_INTRO,
    throne_setup_steps,
)
from rob.ui.render import add_card_actions

if TYPE_CHECKING:
    from rob.discord.client import RobBot


log = logging.getLogger(__name__)

SUCCESS_GIF_URL = "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExMDN5OW9vZTYyODl4MnRmd3A5aGVxeWVkNWF2eTY4ZnhwdXVpeW4wYyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uLiEXaouJVkuA/giphy.gif"


def add_setup_buttons(view: discord.ui.LayoutView, *, domme_id: int, webhook_url: str, send_track_channel_id: int | None) -> None:

    class ContinueSetupButton(discord.ui.Button):
        def __init__(self) -> None:
            super().__init__(label="Continue Setup", style=discord.ButtonStyle.primary)

        async def callback(self, interaction: discord.Interaction) -> None:
            msg = throne_setup_card(throne_setup_steps(webhook_url))
            add_card_actions(msg.view, YesButton(domme_id, send_track_channel_id), NotYetButton())
            await interaction.response.edit_message(**msg.edit_kwargs())

    class NotNowButton(discord.ui.Button):
        def __init__(self) -> None:
            super().__init__(label="Not Now", style=discord.ButtonStyle.secondary)

        async def callback(self, interaction: discord.Interaction) -> None:
            msg = throne_setup_card(
                "No worries — your Throne profile is linked, but tracking won't start until the webhook URL is added to Throne.\n\n"
                "You can run /register domme again when you're ready."
            )
            await interaction.response.edit_message(**msg.edit_kwargs())

    add_card_actions(view, ContinueSetupButton(), NotNowButton())


class YesButton(discord.ui.Button):
    def __init__(self, domme_id: int, send_track_channel_id: int | None) -> None:
        super().__init__(label="Yes", style=discord.ButtonStyle.success)
        self.domme_id = domme_id
        self.send_track_channel_id = send_track_channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = interaction.client
        domme = await bot.dommes_repo.get(self.domme_id)
        if domme and (domme.webhook_connected_at or domme.last_successful_event_at):
            destination = f"<#{self.send_track_channel_id}>" if self.send_track_channel_id else "the send tracking channel"
            success_msg = throne_setup_card(
                "That worked!\n\n"
                f"Your Throne sends will now appear in {destination} as soon as you receive them.\n\n"
                "Please read the information below so you know what Rob collects and how it's used.",
                image_url=SUCCESS_GIF_URL,
            )
            await interaction.response.edit_message(**success_msg.edit_kwargs())
            info_msg = registration_card(
                title="What Rob Collects",
                summary="Rob only stores the information needed to track and display Throne sends inside this Discord server.",
                details=[
                    ("Collected information", "- Your Discord user ID\n- Your Throne handle and creator ID\n- Public wishlist item names\n- Public wishlist item prices\n- Public wishlist item images, when available\n- Send/purchase amounts provided by Throne webhook events\n- Item names and item images from send events\n- Sender/display names provided by Throne, when available\n- Webhook status details, such as when Rob last received a successful event"),
                    ("How it is used", "- To post send notifications in the configured send tracking channel\n- To update Dom/me/Sub leaderboards\n- To prevent duplicate webhook events being counted twice\n- To help server staff troubleshoot tracking issues\n- To let you rebuild your webhook URL if it needs to be rotated"),
                    ("Important notes", "- Rob does not need your Throne password.\n- Rob cannot access private Throne account settings.\n- Your webhook URL should be treated like a secret.\n- If you think your webhook URL was shared accidentally, ask staff to rebuild it."),
                ],
            )
            await interaction.followup.send(**info_msg.send_kwargs())
            return

        msg = throne_setup_card(
            "Not seeing it yet.\n\nPlease make sure you clicked Save Settings in Throne, then click Test Webhook again. "
            "Once Throne shows a success message, press Yes here again."
        )
        add_card_actions(msg.view, YesButton(self.domme_id, self.send_track_channel_id), NotYetButton())
        await interaction.response.edit_message(**msg.edit_kwargs())


class NotYetButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Not Yet", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()


class RegistrationCog(commands.Cog):
    register_group = app_commands.Group(name="register", description="Register as a Dom/me or Sub.")

    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

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

    @register_group.command(name="domme", description="Register a Dom/me Throne profile.")
    @app_commands.describe(throne="Your Throne profile URL or username.")
    async def register_domme(self, interaction: discord.Interaction, throne: str) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(**error_card("This command can only be used in a server.").send_kwargs(), ephemeral=True)
            return

        settings = await self.bot.guild_settings_repo.get(interaction.guild.id)
        if not await self._require_configured_role(
            interaction,
            role_id=settings.domme_role_id if settings is not None else None,
        ):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.registration_service.register_domme(guild_id=interaction.guild.id, discord_user_id=interaction.user.id, throne_input=throne)
        except ValueError as exc:
            await interaction.followup.send(**error_card("Dom/me registration could not be completed.", str(exc)).send_kwargs(), ephemeral=True)
            return

        if not result.webhook_url:
            await interaction.followup.send(**error_card("Webhook URL setup is unavailable.", "Ask staff to verify THRONE_WEBHOOK_BASE_URL on the bot server.").send_kwargs(), ephemeral=True)
            return

        domme_result = getattr(result, "domme", None) or getattr(result, "creator", None)
        if domme_result is None or getattr(domme_result, "id", None) is None:
            await interaction.followup.send(
                **error_card(
                    "Dom/me registration completed, but setup could not continue.",
                    "Rob could not resolve the registration record needed for setup buttons. Please ask staff to check the logs.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return

        try:
            dm_msg = throne_setup_card(THRONE_SETUP_INTRO)
            add_setup_buttons(
                dm_msg.view,
                domme_id=int(domme_result.id),
                webhook_url=result.webhook_url,
                send_track_channel_id=settings.send_track_channel_id if settings else None,
            )
            await interaction.user.send(**dm_msg.send_kwargs())
        except discord.Forbidden as exc:
            log.warning("Failed to DM Throne setup flow to user_id=%s guild_id=%s reason=Forbidden status=%s code=%s text=%s", interaction.user.id, interaction.guild.id if interaction.guild else None, getattr(exc, "status", None), getattr(exc, "code", None), getattr(exc, "text", None))
            await interaction.followup.send(**error_card("You're registered, but Rob couldn't DM you.", "This usually means Discord blocked the DM. Please check:\n\n- Server Privacy Settings → Allow direct messages from server members\n- You have not blocked this bot\n- Your Discord privacy settings allow bot/member DMs\n\nOnce fixed, run /register domme again.").send_kwargs(), ephemeral=True)
            return
        except discord.HTTPException as exc:
            log.exception("Failed to DM Throne setup flow to user_id=%s guild_id=%s status=%s code=%s text=%s", interaction.user.id, interaction.guild.id if interaction.guild else None, getattr(exc, "status", None), getattr(exc, "code", None), getattr(exc, "text", None))
            if getattr(exc, "status", None) == 400 and getattr(exc, "code", None) == 50035:
                await interaction.followup.send(**error_card("You're registered, but Rob hit a setup-message error.", "Your profile is linked, but Rob couldn't generate the setup DM correctly. Staff have been given enough detail in the logs to fix it.").send_kwargs(), ephemeral=True)
                return
            await interaction.followup.send(**error_card("You're registered, but Rob couldn't DM you.", "This usually means Discord blocked the DM. Please check:\n\n- Server Privacy Settings → Allow direct messages from server members\n- You have not blocked this bot\n- Your Discord privacy settings allow bot/member DMs\n\nOnce fixed, run /register domme again.").send_kwargs(), ephemeral=True)
            return

        await interaction.followup.send(**domme_registered_card().send_kwargs(), ephemeral=True)

    @register_group.command(name="sub", description="Register a sending name to claim sends.")
    @app_commands.describe(send_name="The exact name you use on Throne sends.")
    async def register_sub(self, interaction: discord.Interaction, send_name: str) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(**error_card("This command can only be used in a server.").send_kwargs(), ephemeral=True)
            return

        settings = await self.bot.guild_settings_repo.get(interaction.guild.id)
        if not await self._require_configured_role(
            interaction,
            role_id=settings.sub_role_id if settings is not None else None,
        ):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.registration_service.register_sub(guild_id=interaction.guild.id, discord_user_id=interaction.user.id, send_name=send_name)
        except ValueError as exc:
            await interaction.followup.send(**error_card("Sub registration could not be completed.", str(exc)).send_kwargs(), ephemeral=True)
            return

        await interaction.followup.send(**registration_card(title="Rob | Sub Registered", summary="Your send-claim name is now active.", details=[("Tracked Name", result.sub.send_name)]).send_kwargs(), ephemeral=True)
