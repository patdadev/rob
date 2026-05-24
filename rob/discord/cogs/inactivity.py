from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from rob.ui.cards.errors import error_card

if TYPE_CHECKING:
    from rob.discord.client import RobBot

log = logging.getLogger(__name__)


class InactivityCog(commands.Cog):
    def __init__(self, bot: RobBot) -> None:
        self.bot = bot
        self.inactivity_loop.change_interval(minutes=max(1, bot.settings.inactivity_loop_minutes))
        self.inactivity_loop.start()

    def cog_unload(self) -> None:
        self.inactivity_loop.cancel()

    @tasks.loop(minutes=60)
    async def inactivity_loop(self) -> None:
        guild_ids = await self.bot.guild_settings_repo.list_guild_ids()
        for guild_id in guild_ids:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            try:
                await self.bot.inactivity_service.process_guild(
                    guild,
                    send_notifications=True,
                    perform_kicks=True,
                )
            except Exception:  # pragma: no cover - safety logging around runtime loop
                log.exception("Inactivity loop failed for guild_id=%s", guild_id)

    @inactivity_loop.before_loop
    async def _before_inactivity_loop(self) -> None:
        await self.bot.wait_until_ready()

    def _member_has_role(self, member: discord.Member, role_id: int | None) -> bool:
        return role_id is not None and any(role.id == role_id for role in member.roles)

    def _can_manage(self, user: discord.Member | discord.User) -> bool:
        owner_id = self.bot.settings.inactivity_owner_user_id
        if owner_id is not None and user.id == owner_id:
            return True
        return isinstance(user, discord.Member) and user.guild_permissions.manage_guild

    @app_commands.command(name="inactivitytest", description="DM inactivity template messages to yourself.")
    @app_commands.choices(
        notice_type=[
            app_commands.Choice(name="All notices", value="all"),
            app_commands.Choice(name="First notice", value="first"),
            app_commands.Choice(name="Warning notice", value="warning"),
            app_commands.Choice(name="Final notice", value="final"),
        ]
    )
    async def inactivity_test(
        self,
        interaction: discord.Interaction,
        notice_type: app_commands.Choice[str],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                **error_card("This command can only be used in a server.").send_kwargs(),
                ephemeral=True,
            )
            return
        if not self._can_manage(interaction.user):
            await interaction.response.send_message(
                **error_card("Only configured inactivity managers can run this command.").send_kwargs(),
                ephemeral=True,
            )
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
        if member is None:
            await interaction.response.send_message(
                **error_card("Rob could not resolve your member record in this server.").send_kwargs(),
                ephemeral=True,
            )
            return
        remove_at = datetime.now(timezone.utc) + timedelta(days=self.bot.settings.inactivity_assignment_grace_days)
        value = notice_type.value
        messages: list[str] = []
        if value in {"all", "first"}:
            messages.append(self.bot.inactivity_service._build_first_notice(member, remove_at))
        if value in {"all", "warning"}:
            messages.append(self.bot.inactivity_service._build_warning_notice(member, remove_at))
        if value in {"all", "final"}:
            messages.append(self.bot.inactivity_service._build_final_notice(member, remove_at))

        for message in messages:
            await member.send(message)

        await interaction.response.send_message(
            f"Sent {len(messages)} inactivity test message(s) to your DMs.",
            ephemeral=True,
        )

    @app_commands.command(name="inactivelist", description="List inactive members and scheduled removal times.")
    async def inactivity_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                **error_card("This command can only be used in a server.").send_kwargs(),
                ephemeral=True,
            )
            return
        if not self._can_manage(interaction.user):
            await interaction.response.send_message(
                **error_card("Only configured inactivity managers can run this command.").send_kwargs(),
                ephemeral=True,
            )
            return

        snapshots = await self.bot.inactivity_service.process_guild(
            interaction.guild,
            send_notifications=False,
            perform_kicks=False,
        )
        if not snapshots:
            await interaction.response.send_message("No eligible inactive members found.", ephemeral=True)
            return

        lines = ["## Inactive Members", "", f"Total: **{len(snapshots)}**", ""]
        for snapshot in snapshots:
            ts = int(snapshot.remove_at.timestamp())
            lines.append(
                f"- {snapshot.member.mention} (`{snapshot.member.id}`) — remove <t:{ts}:R> / <t:{ts}:F>"
            )
        await interaction.response.send_message("\n".join(lines[:200]), ephemeral=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        settings = await self.bot.guild_settings_repo.get(after.guild.id)
        inactive_role_id = settings.inactive_role_id if settings is not None else None
        if inactive_role_id is None:
            return
        had_inactive_role = self._member_has_role(before, inactive_role_id)
        has_inactive_role = self._member_has_role(after, inactive_role_id)
        if had_inactive_role and not has_inactive_role:
            await self.bot.inactivity_service.clear_member_state(after.guild.id, after.id)
        if has_inactive_role and not self.bot.inactivity_service._is_eligible_member(after):
            await self.bot.inactivity_service.clear_member_state(after.guild.id, after.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        settings = await self.bot.guild_settings_repo.get(member.guild.id)
        inactive_role_id = settings.inactive_role_id if settings is not None else None
        if inactive_role_id is None:
            return
        if self._member_has_role(member, inactive_role_id):
            await self.bot.inactivity_service.clear_member_state(member.guild.id, member.id)
