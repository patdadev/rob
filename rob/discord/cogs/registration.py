from __future__ import annotations

from typing import TYPE_CHECKING
import logging

import discord
from discord import app_commands
from discord.ext import commands

from rob.ui.cards.errors import error_card
from rob.ui.cards.registration import domme_registered_card, registration_card, throne_setup_card
from rob.ui.render import add_action_row

if TYPE_CHECKING:
    from rob.discord.client import RobBot


log = logging.getLogger(__name__)

SUCCESS_GIF_URL = "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExMDN5OW9vZTYyODl4MnRmd3A5aGVxeWVkNWF2eTY4ZnhwdXVpeW4wYyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uLiEXaouJVkuA/giphy.gif"


def add_setup_buttons(view: discord.ui.LayoutView, *, creator_id: int, webhook_url: str, send_track_channel_id: int | None) -> None:

    class ContinueSetupButton(discord.ui.Button):
        def __init__(self) -> None:
            super().__init__(label="Continue Setup", style=discord.ButtonStyle.primary)

        async def callback(self, interaction: discord.Interaction) -> None:
            body = (
                "To make sure Rob gets the right information, you'll need to set up the Webhook Integration in your Throne settings.\n\n"
                "Here's how:\n\n"
                "1. Head to https://throne.com/ and sign in.\n2. Go to Settings, then click Integrations.\n3. Scroll until you see Webhooks.\n"
                "4. Click Enable Webhooks.\n5. Under Subscriber URLs, click Add URL.\n6. Enter the almighty link below.\n"
                "7. Click Save Settings, then click Test Webhook and wait for the success message.\n\n"
                "Once done, come back here and I'll let you know if it worked.\n\n"
                f"The almighty link:\n```\n{webhook_url}\n```\nDid it work?"
            )
            msg = throne_setup_card(body)
            add_action_row(msg.view, YesButton(creator_id, send_track_channel_id), NotYetButton())
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

    add_action_row(view, ContinueSetupButton(), NotNowButton())


class YesButton(discord.ui.Button):
    def __init__(self, creator_id: int, send_track_channel_id: int | None) -> None:
        super().__init__(label="Yes", style=discord.ButtonStyle.success)
        self.creator_id = creator_id
        self.send_track_channel_id = send_track_channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = interaction.client
        creator = await bot.throne_creators_repo.get(self.creator_id)
        if creator and (creator.setup_verified_at or creator.last_test_webhook_at or creator.last_successful_event_at):
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
                    ("How it is used", "- To post send notifications in the configured send tracking channel\n- To update Domme/Sub leaderboards\n- To prevent duplicate webhook events being counted twice\n- To help server staff troubleshoot tracking issues\n- To let you rebuild your webhook URL if it needs to be rotated"),
                    ("Important notes", "- Rob does not need your Throne password.\n- Rob cannot access private Throne account settings.\n- Your webhook URL should be treated like a secret.\n- If you think your webhook URL was shared accidentally, ask staff to rebuild it."),
                ],
            )
            await interaction.followup.send(**info_msg.send_kwargs())
            return

        msg = throne_setup_card(
            "Not seeing it yet.\n\nPlease make sure you clicked Save Settings in Throne, then click Test Webhook again. "
            "Once Throne shows a success message, press Yes here again."
        )
        add_action_row(msg.view, YesButton(self.creator_id, self.send_track_channel_id), NotYetButton())
        await interaction.response.edit_message(**msg.edit_kwargs())


class NotYetButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Not Yet", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()


class RegistrationCog(commands.Cog):
    register_group = app_commands.Group(name="register", description="Register as a Domme or Sub.")

    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

    @register_group.command(name="domme", description="Register a Domme Throne profile.")
    @app_commands.describe(throne="Your Throne profile URL or username.")
    async def register_domme(self, interaction: discord.Interaction, throne: str) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(**error_card("This command can only be used in a server.").send_kwargs(), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.registration_service.register_domme(guild_id=interaction.guild.id, discord_user_id=interaction.user.id, throne_input=throne)
        except ValueError as exc:
            await interaction.followup.send(**error_card("Domme registration could not be completed.", str(exc)).send_kwargs(), ephemeral=True)
            return

        if not result.webhook_url:
            await interaction.followup.send(**error_card("Webhook URL setup is unavailable.", "Ask staff to verify THRONE_WEBHOOK_BASE_URL on the bot server.").send_kwargs(), ephemeral=True)
            return

        settings = await self.bot.guild_settings_repo.get(interaction.guild.id)
        try:
            dm_msg = throne_setup_card("Howdy Partner!\n\nYou've received this DM because you've enabled Throne tracking for yourself. Before we can continue, we'll need you to do some extra steps inside Throne first.")
            add_setup_buttons(dm_msg.view, creator_id=result.creator.id, webhook_url=result.webhook_url, send_track_channel_id=settings.send_track_channel_id if settings else None)
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
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.registration_service.register_sub(guild_id=interaction.guild.id, discord_user_id=interaction.user.id, send_name=send_name)
        except ValueError as exc:
            await interaction.followup.send(**error_card("Sub registration could not be completed.", str(exc)).send_kwargs(), ephemeral=True)
            return

        await interaction.followup.send(**registration_card(title="Rob | Sub Registered", summary="Your send-claim name is now active.", details=[("Tracked Name", result.sub.send_name)]).send_kwargs(), ephemeral=True)
