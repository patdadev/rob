from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from rob.achievements.embeds import achievement_unlocked_card, achievements_overview_cards
from rob.ui.cards.errors import error_card, error_permission
from rob.ui.copy import PERMISSION_ROLE_MISSING
from rob.ui.render import RenderedMessage, add_card_actions

if TYPE_CHECKING:
    from rob.discord.client import RobBot

log = logging.getLogger(__name__)


class _AchievementsPager:
    def __init__(
        self,
        *,
        owner_user_id: int,
        cards: list[RenderedMessage],
    ) -> None:
        self.owner_user_id = owner_user_id
        self.cards = cards
        self.page_index = 0
        self._controls_attached: set[int] = set()

    def current_card(self) -> RenderedMessage:
        card = self.cards[self.page_index]
        self._attach_controls(card, page_index=self.page_index)
        return card

    def _attach_controls(self, card: RenderedMessage, *, page_index: int) -> None:
        if page_index in self._controls_attached:
            return
        view = card.view
        if view is None:
            return
        previous = _AchievementsPageButton(self, direction=-1, disabled=page_index <= 0)
        next_button = _AchievementsPageButton(
            self,
            direction=1,
            disabled=page_index >= len(self.cards) - 1,
        )
        if isinstance(view, discord.ui.LayoutView):
            add_card_actions(view, previous, next_button)
        else:
            view.add_item(previous)
            view.add_item(next_button)
        self._controls_attached.add(page_index)

    async def handle_page_turn(self, interaction: discord.Interaction, *, direction: int) -> None:
        interaction_user = interaction.user
        if interaction_user is None or interaction_user.id != self.owner_user_id:
            await interaction.response.send_message(
                "This achievement list belongs to someone else.",
                ephemeral=True,
            )
            return

        next_index = max(0, min(len(self.cards) - 1, self.page_index + direction))
        if next_index == self.page_index:
            await interaction.response.defer()
            return
        self.page_index = next_index
        await interaction.response.edit_message(**self.current_card().edit_kwargs())


class _AchievementsPageButton(discord.ui.Button):
    def __init__(self, pager: _AchievementsPager, *, direction: int, disabled: bool) -> None:
        label = "Previous" if direction < 0 else "Next"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            disabled=disabled,
        )
        self.pager = pager
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.pager.handle_page_turn(interaction, direction=self.direction)


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

        target = user or viewer

        newly_unlocked = 0
        if await self.bot.achievements_service.unlock_achievement(
            guild_id=interaction.guild.id,
            discord_user_id=viewer.id,
            achievement_key="first_achievement_view",
            source="slash:/achievements",
        ):
            newly_unlocked += 1
        if target.id != viewer.id:
            if await self.bot.achievements_service.unlock_achievement(
                guild_id=interaction.guild.id,
                discord_user_id=viewer.id,
                achievement_key="viewed_other_achievements",
                source="slash:/achievements",
                metadata={"target_user_id": target.id},
            ):
                newly_unlocked += 1

        unlocked_achievements = await self.bot.achievements_service.get_user_achievements(
            guild_id=interaction.guild.id,
            discord_user_id=target.id,
        )
        cards = achievements_overview_cards(
            display_name=target.display_name,
            unlocked_achievements=unlocked_achievements,
            for_self=target.id == viewer.id,
            newly_unlocked_count=newly_unlocked,
        )
        if len(cards) == 1:
            await interaction.response.send_message(**cards[0].send_kwargs())
        else:
            pager = _AchievementsPager(owner_user_id=viewer.id, cards=cards)
            await interaction.response.send_message(**pager.current_card().send_kwargs())

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
