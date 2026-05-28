from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from rob.achievements.embeds import achievement_unlocked_card, achievements_overview_cards
from rob.ui.cards.errors import error_card, error_permission
from rob.ui.copy import PERMISSION_ROLE_MISSING

if TYPE_CHECKING:
    from rob.discord.client import RobBot

log = logging.getLogger(__name__)


class AchievementsCog(commands.Cog):
    test_group = app_commands.Group(name="test", description="Developer test commands.")

    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

    @app_commands.command(name="achievements", description="View your achievements or another member's achievements.")
    @app_commands.describe(user="Optional member to view instead of yourself.")
    async def achievements(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(
                **error_card("This command can only be used in a server.").send_kwargs(),
                ephemeral=True,
            )
            return

        if isinstance(interaction.user, discord.Member):
            viewer = interaction.user
        else:
            viewer = interaction.guild.get_member(interaction.user.id)
            if viewer is None:
                await interaction.response.send_message(
                    **error_card("Rob could not resolve your member profile in this server.").send_kwargs(),
                    ephemeral=True,
                )
                return

        target = user or viewer

        await self.bot.achievements_service.unlock_achievement(
            guild_id=interaction.guild.id,
            discord_user_id=viewer.id,
            achievement_key="first_achievement_view",
            source="slash:/achievements",
        )
        if target.id != viewer.id:
            await self.bot.achievements_service.unlock_achievement(
                guild_id=interaction.guild.id,
                discord_user_id=viewer.id,
                achievement_key="viewed_other_achievements",
                source="slash:/achievements",
                metadata={"target_user_id": target.id},
            )

        unlocked_keys = await self.bot.achievements_service.get_user_achievement_keys(
            guild_id=interaction.guild.id,
            discord_user_id=target.id,
        )
        cards = achievements_overview_cards(
            display_name=target.display_name,
            unlocked_keys=unlocked_keys,
            for_self=target.id == viewer.id,
        )
        first, *rest = cards
        await interaction.response.send_message(**first.send_kwargs(), ephemeral=False)
        for card in rest:
            await interaction.followup.send(**card.send_kwargs(), ephemeral=False)

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
    async def test_achievements(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(
                **error_card("This command can only be used in a server.").send_kwargs(),
                ephemeral=True,
            )
            return

        if not await self._can_use_test_achievements(interaction):
            await interaction.response.send_message(
                **error_permission(PERMISSION_ROLE_MISSING).send_kwargs(),
                ephemeral=True,
            )
            return

        await interaction.response.send_message("Generating achievement preview embeds...", ephemeral=True)
        channel = interaction.channel
        if channel is None:
            return

        achievements = self.bot.achievements_service.all_definitions()
        for achievement in achievements:
            try:
                await channel.send(**achievement_unlocked_card(achievement, include_meta_line=True).send_kwargs())
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
        guild_id = guild_ids[0]
        await self.bot.achievements_service.unlock_achievement(
            guild_id=guild_id,
            discord_user_id=message.author.id,
            achievement_key="dm_rob",
            source="dm",
        )

