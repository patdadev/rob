from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from rob.achievements.embeds import (
    achievement_unlocked_card,
    render_server_achievements_message,
    render_user_achievements_message,
)
from rob.ui.cards.errors import error_card, error_permission
from rob.ui.copy import PERMISSION_ROLE_MISSING
from rob.ui.render import RenderedMessage

if TYPE_CHECKING:
    from rob.discord.client import RobBot

log = logging.getLogger(__name__)

_ACHIEVEMENT_SCOPE_CHOICES = [
    app_commands.Choice(name="Me", value="me"),
    app_commands.Choice(name="Server", value="server"),
    app_commands.Choice(name="User", value="user"),
]


class AchievementsCog(commands.Cog):
    test_group = app_commands.Group(name="test", description="Developer test commands.")

    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

    def _make_interaction_achievement_announcer(
        self,
        *,
        interaction: discord.Interaction,
        discord_user_id: int,
        display_name: str,
    ):
        async def _callback(achievement) -> None:
            maintenance = getattr(self.bot, "maintenance_service", None)
            if maintenance is not None and await maintenance.notifications_suppressed():
                return
            channel = interaction.channel
            if channel is None:
                return
            await channel.send(
                **achievement_unlocked_card(
                    achievement,
                    unlocked_by_display_name=display_name,
                    unlocked_by_user_id=discord_user_id,
                ).send_kwargs()
            )

        return _callback

    @app_commands.command(name="achievements", description="View your achievements, another member's, or server-wide stats.")
    @app_commands.choices(scope=_ACHIEVEMENT_SCOPE_CHOICES)
    @app_commands.describe(
        scope="Choose yourself, the server, or another member.",
        user="Optional member to view instead of yourself.",
    )
    async def achievements(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str] | None = None,
        user: Optional[discord.Member] = None,
    ) -> None:
        if not self.bot.achievements_service.enabled:
            await interaction.response.send_message(
                "Hey, this is disabled! We'll bring it back soon.",
                ephemeral=True,
            )
            return
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(
                **error_card(
                    "Use `/achievements` in the server.",
                    "Rob needs the server context so it can match the right achievement list.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return

        if isinstance(interaction.user, discord.Member):
            viewer = interaction.user
        else:
            viewer = interaction.guild.get_member(interaction.user.id)
            if viewer is None:
                await interaction.response.send_message(
                    **error_card(
                        "Rob couldn't find your server profile just now.",
                        "Give it another go in a moment and Rob should behave.",
                    ).send_kwargs(),
                    ephemeral=True,
                )
                return

        scope_value = scope.value if scope is not None else None
        if scope_value == "server":
            target = None
        elif user is not None:
            target = user
        elif scope_value == "user":
            await interaction.response.send_message(
                **error_card(
                    "Pick someone to inspect first.",
                    "Use the `user` option when you choose the user scope.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return
        else:
            target = viewer

        viewer_display_name = viewer.display_name

        newly_unlocked = 0
        if await self.bot.achievements_service.unlock_achievement(
            guild_id=interaction.guild.id,
            discord_user_id=viewer.id,
            achievement_key="first_achievement_view",
            source="slash:/achievements",
            on_unlocked=self._make_interaction_achievement_announcer(
                interaction=interaction,
                discord_user_id=viewer.id,
                display_name=viewer_display_name,
            ),
        ):
            newly_unlocked += 1
        if target is not None and target.id != viewer.id:
            if await self.bot.achievements_service.unlock_achievement(
                guild_id=interaction.guild.id,
                discord_user_id=viewer.id,
                achievement_key="viewed_other_achievements",
                source="slash:/achievements",
                metadata={"target_user_id": target.id},
                on_unlocked=self._make_interaction_achievement_announcer(
                    interaction=interaction,
                    discord_user_id=viewer.id,
                    display_name=viewer_display_name,
                ),
            ):
                newly_unlocked += 1

        if scope_value == "server":
            stats = await self.bot.achievements_service.get_server_stats(guild_id=interaction.guild.id)
            guild_icon = getattr(getattr(interaction.guild, "icon", None), "url", None)
            rendered = render_server_achievements_message(
                owner_user_id=viewer.id,
                server_name=getattr(interaction.guild, "name", f"Server {interaction.guild.id}"),
                server_icon_url=guild_icon,
                member_count=getattr(interaction.guild, "member_count", 0) or 0,
                stats=stats,
            )
            await interaction.response.send_message(**rendered.send_kwargs())
            return

        assert target is not None
        states = await self.bot.achievements_service.get_user_achievement_states(
            guild_id=interaction.guild.id,
            discord_user_id=target.id,
        )
        target_icon = getattr(getattr(target, "display_avatar", None), "url", None)
        rendered = render_user_achievements_message(
            owner_user_id=viewer.id,
            title=target.display_name,
            subtitle=(
                f"Your achievement cabinet · +{newly_unlocked} new"
                if target.id == viewer.id and newly_unlocked
                else (
                    "Your achievement cabinet"
                    if target.id == viewer.id
                    else f"Viewing {target.display_name} in this server"
                )
            ),
            icon_url=target_icon,
            states=states,
            allow_public_share=True,
            empty_callout=(
                "You haven't unlocked anything yet. Go do something suspiciously Rob-shaped."
                if target.id == viewer.id
                else f"{target.display_name} hasn't unlocked any achievements yet."
            ),
        )
        await interaction.response.send_message(**rendered.send_kwargs(), ephemeral=True)

    async def _can_use_test_achievements(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.user is None:
            return False
        if interaction.user.id == (self.bot.settings.inactivity_owner_user_id or -1):
            return True
        if not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.manage_guild:
            return True
        settings = await self.bot.guild_settings_repo.get(interaction.guild.id)
        if settings is None or settings.mod_role_id is None:
            return False
        return any(role.id == settings.mod_role_id for role in interaction.user.roles)

    @test_group.command(name="achievements", description="Preview all configured achievement cards.")
    @app_commands.describe(debug="Include internal metadata lines for each preview card.")
    async def test_achievements(self, interaction: discord.Interaction, debug: bool = False) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(
                **error_card(
                    "Use this test command inside the server.",
                    "Rob needs the guild context before it can build the preview set.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return

        if not await self._can_use_test_achievements(interaction):
            await interaction.response.send_message(
                **error_permission(PERMISSION_ROLE_MISSING).send_kwargs(),
                ephemeral=True,
            )
            return

        await interaction.response.send_message("Building your achievement preview set...", ephemeral=True)
        channel = interaction.channel
        if channel is None:
            return

        achievements = self.bot.achievements_service.all_definitions()
        for achievement in achievements:
            try:
                await channel.send(
                    **achievement_unlocked_card(
                        achievement,
                        unlocked_by_display_name="Preview Mode",
                        include_meta_line=debug,
                    ).send_kwargs()
                )
            except discord.HTTPException:
                log.exception("Failed to send achievement preview key=%s", achievement.key)
                continue

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is not None:
            return
        if message.author.id == (self.bot.user.id if self.bot.user else 0):
            return

        guild_ids = await self.bot.guild_settings_repo.list_guild_ids()
        if not guild_ids:
            return
        maintenance = getattr(self.bot, "maintenance_service", None)
        if maintenance is not None and await maintenance.notifications_suppressed():
            return
        guild_id = guild_ids[0]
        display_name = (
            getattr(message.author, "display_name", None)
            or getattr(message.author, "name", str(message.author.id))
        )
        await self.bot.achievements_service.unlock_achievement(
            guild_id=guild_id,
            discord_user_id=message.author.id,
            achievement_key="dm_rob",
            source="dm",
            on_unlocked=lambda achievement: message.channel.send(
                **achievement_unlocked_card(
                    achievement,
                    unlocked_by_display_name=display_name,
                    unlocked_by_user_id=message.author.id,
                ).send_kwargs()
            ),
        )

    async def _unlock_secret_achievement(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        display_name: str,
    ) -> RenderedMessage | str:
        if not self.bot.achievements_service.enabled:
            return "Achievements are switched off right now, but your existing ones are still there."
        definition = self.bot.achievements_service.get_definition("secret_command")
        if definition is None:
            return "Rob misplaced that secret. Try again in a moment."
        unlocked = await self.bot.achievements_service.unlock_achievement(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            achievement_key="secret_command",
            source="secret-command",
        )
        if not unlocked:
            return "Rob already told you to keep that secret."
        return achievement_unlocked_card(
            definition,
            unlocked_by_display_name=display_name,
        )

    @commands.command(name="secret", hidden=True)
    async def secret_prefix(self, ctx: commands.Context) -> None:
        if ctx.guild is None or ctx.author is None:
            await ctx.reply("Use `!secret` in the server so Rob can attach it to the right guild.", mention_author=False)
            return

        display_name = getattr(ctx.author, "display_name", None) or getattr(
            ctx.author,
            "name",
            str(ctx.author.id),
        )
        payload = await self._unlock_secret_achievement(
            guild_id=ctx.guild.id,
            discord_user_id=ctx.author.id,
            display_name=display_name,
        )

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        if isinstance(payload, str):
            try:
                await ctx.author.send(payload)
            except discord.Forbidden:
                await ctx.reply(
                    "Rob tried to keep that private, but your DMs are closed. Open them and try `!secret` again.",
                    mention_author=False,
                    delete_after=15,
                )
            return

        try:
            await ctx.author.send(**payload.send_kwargs())
        except discord.Forbidden:
            await ctx.reply(
                "Rob couldn't DM you the secret card. Open your DMs and try `!secret` again.",
                mention_author=False,
                delete_after=15,
            )
