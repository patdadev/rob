from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from rob.ui.cards.errors import error_card, error_permission
from rob.ui.components import make_card, render
from rob.ui.theme import (
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_LEADERBOARD,
    COLOR_ROB_PURPLE,
    COLOR_SUCCESS,
    COLOR_WARNING,
)

if TYPE_CHECKING:
    from rob.discord.client import RobBot


_STYLE_TO_COLOR = {
    "purple": COLOR_ROB_PURPLE,
    "info": COLOR_INFO,
    "success": COLOR_SUCCESS,
    "warning": COLOR_WARNING,
    "danger": COLOR_DANGER,
    "leaderboard": COLOR_LEADERBOARD,
}

_PING_TO_CONTENT = {
    "none": None,
    "everyone": "@everyone",
    "here": "@here",
}


class _BroadcastModal(discord.ui.Modal, title="Owner Broadcast"):
    def __init__(
        self,
        *,
        cog: "BroadcastCog",
        style: str,
        ping: str,
        image_url: str | None,
    ) -> None:
        super().__init__()
        self.cog = cog
        self.style = style
        self.ping = ping
        self.image_url = image_url

        self.guild_id = discord.ui.TextInput(
            label="Guild ID",
            style=discord.TextStyle.short,
            required=True,
            max_length=20,
            placeholder="123456789012345678",
        )
        self.channel_id = discord.ui.TextInput(
            label="Channel ID",
            style=discord.TextStyle.short,
            required=True,
            max_length=20,
            placeholder="123456789012345678",
        )
        self.title_input = discord.ui.TextInput(
            label="Card title",
            style=discord.TextStyle.short,
            required=True,
            max_length=120,
        )
        self.body_input = discord.ui.TextInput(
            label="Card body",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )
        self.helper_input = discord.ui.TextInput(
            label="Helper line (optional)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
            placeholder="Optional helper/footer line",
        )
        self.add_item(self.guild_id)
        self.add_item(self.channel_id)
        self.add_item(self.title_input)
        self.add_item(self.body_input)
        self.add_item(self.helper_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.submit_broadcast(
            interaction,
            guild_id_raw=str(self.guild_id.value).strip(),
            channel_id_raw=str(self.channel_id.value).strip(),
            title=str(self.title_input.value).strip(),
            body=str(self.body_input.value).strip(),
            helper=(str(self.helper_input.value).strip() or None),
            style=self.style,
            ping=self.ping,
            image_url=self.image_url,
        )


class BroadcastCog(commands.Cog):
    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

    async def _is_owner(self, user_id: int) -> bool:
        configured = getattr(self.bot.settings, "inactivity_owner_user_id", None)
        if configured is not None and configured == user_id:
            return True

        try:
            app_info = await self.bot.application_info()
        except discord.HTTPException:
            return False

        owner = app_info.owner
        if owner is None:
            return False
        if getattr(owner, "id", None) == user_id:
            return True

        # Team-owned applications can expose member IDs through owner.members.
        members = getattr(owner, "members", None) or []
        return any(getattr(member, "id", None) == user_id for member in members)

    @app_commands.command(
        name="broadcast",
        description="Owner-only DM broadcast form for Rob cards.",
    )
    @app_commands.describe(
        style="Card style/accent to use.",
        ping="Optional ping content for the broadcast message.",
        image_url="Optional image URL to include in the card.",
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="Rob Purple", value="purple"),
            app_commands.Choice(name="Info Blue", value="info"),
            app_commands.Choice(name="Success Green", value="success"),
            app_commands.Choice(name="Warning Gold", value="warning"),
            app_commands.Choice(name="Danger Red", value="danger"),
            app_commands.Choice(name="Leaderboard Purple", value="leaderboard"),
        ],
        ping=[
            app_commands.Choice(name="No ping", value="none"),
            app_commands.Choice(name="@everyone", value="everyone"),
            app_commands.Choice(name="@here", value="here"),
        ],
    )
    async def broadcast(
        self,
        interaction: discord.Interaction,
        style: app_commands.Choice[str],
        ping: Optional[app_commands.Choice[str]] = None,
        image_url: Optional[str] = None,
    ) -> None:
        if interaction.user is None:
            await interaction.response.send_message(
                **error_card("Rob could not resolve your user identity.").send_kwargs(),
                ephemeral=True,
            )
            return
        if interaction.guild is not None:
            await interaction.response.send_message(
                **error_permission("This command is DM-only. Open a DM with Rob to use /broadcast.").send_kwargs(),
                ephemeral=True,
            )
            return
        if not await self._is_owner(interaction.user.id):
            await interaction.response.send_message(
                **error_permission("Only the bot owner can run this command.").send_kwargs(),
            )
            return

        await interaction.response.send_modal(
            _BroadcastModal(
                cog=self,
                style=style.value,
                ping=ping.value if ping is not None else "none",
                image_url=(image_url or "").strip() or None,
            )
        )

    async def submit_broadcast(
        self,
        interaction: discord.Interaction,
        *,
        guild_id_raw: str,
        channel_id_raw: str,
        title: str,
        body: str,
        helper: str | None,
        style: str,
        ping: str,
        image_url: str | None,
    ) -> None:
        if interaction.user is None or not await self._is_owner(interaction.user.id):
            await interaction.response.send_message(
                **error_permission("Only the bot owner can run this command.").send_kwargs(),
            )
            return

        if not guild_id_raw.isdigit() or not channel_id_raw.isdigit():
            await interaction.response.send_message(
                **error_card("Guild ID and Channel ID must be numeric Discord IDs.").send_kwargs(),
            )
            return
        if not title or not body:
            await interaction.response.send_message(
                **error_card("Title and body are required.").send_kwargs(),
            )
            return

        guild_id = int(guild_id_raw)
        channel_id = int(channel_id_raw)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await interaction.response.send_message(
                **error_card(f"Rob is not currently in guild `{guild_id}`.").send_kwargs(),
            )
            return

        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                fetched = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.HTTPException):
                fetched = None
            channel = fetched

        if not isinstance(channel, discord.TextChannel) or channel.guild.id != guild_id:
            await interaction.response.send_message(
                **error_card(
                    "Target channel was not found as a text channel in that guild.",
                    "Check the guild/channel IDs and try again.",
                ).send_kwargs(),
            )
            return

        color = _STYLE_TO_COLOR.get(style, COLOR_ROB_PURPLE)
        card = make_card(
            title=title,
            body=body,
            color=color,
            footer=helper,
            image_url=image_url,
        )
        rendered = render(card)
        send_kwargs = rendered.send_kwargs()
        ping_content = _PING_TO_CONTENT.get(ping, None)
        if ping_content:
            send_kwargs["content"] = ping_content

        try:
            message = await channel.send(**send_kwargs)
        except discord.HTTPException:
            await interaction.response.send_message(
                **error_card("Broadcast failed to send to that channel.").send_kwargs(),
            )
            return

        confirmation = render(
            make_card(
                title="Broadcast Sent",
                body=(
                    f"Guild: **{guild.name}** (`{guild.id}`)\n"
                    f"Channel: <#{channel.id}>\n"
                    f"Message ID: `{message.id}`"
                ),
                color=COLOR_SUCCESS,
                footer="Rob delivered the broadcast.",
            )
        )
        await interaction.response.send_message(**confirmation.send_kwargs())
