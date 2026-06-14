"""``/settings`` slash command for the test guild only.

Lets a registered Dom/me change their leaderboard visibility, and any member
opt into the leaderboard access role. All other guilds receive an ephemeral
"not available here" response.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from rob.config.guilds import is_test_guild
from rob.discord.leaderboard_access import apply_leaderboard_access
from rob.ui.cards.dm_onboarding import PreferencesView
from rob.ui.cards.errors import error_card
from rob.ui.components import make_card, render
from rob.ui.theme import COLOR_SUCCESS

if TYPE_CHECKING:
    from rob.discord.client import RobBot


log = logging.getLogger(__name__)


def _not_available_response() -> dict:
    return error_card(
        "Not available here",
        "`/settings` is only available in the test guild right now.",
    ).send_kwargs()


class SettingsCog(commands.Cog):
    settings_group = app_commands.Group(
        name="settings",
        description="Manage your Rob preferences (test guild only).",
    )

    def __init__(self, bot: "RobBot") -> None:
        self.bot = bot

    async def _resolve_domme(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.user is None:
            return None
        return await self.bot.dommes_repo.get_by_user_id(
            interaction.guild.id, interaction.user.id
        )

    async def _send_preferences_panel(self, interaction: discord.Interaction) -> None:
        """Build and send the preferences panel (shared by ``/preferences`` and
        ``/settings preferences``).

        Shows the Dom/me-only leaderboard-visibility control when the caller is a
        registered Dom/me, and the universal leaderboard-access control whenever
        an access role is configured. On save it persists the Dom/me preference
        and assigns/removes the leaderboard access role to match the caller's
        choice.
        """

        if not is_test_guild(interaction.guild_id):
            await interaction.response.send_message(**_not_available_response(), ephemeral=True)
            return

        member = interaction.user
        domme = await self._resolve_domme(interaction)
        settings = await self.bot.guild_settings_repo.get(interaction.guild_id)
        access_role_id = getattr(settings, "leaderboard_view_role_id", None) if settings else None
        show_access = access_role_id is not None
        has_access = (
            show_access
            and isinstance(member, discord.Member)
            and any(role.id == access_role_id for role in member.roles)
        )

        if domme is None and not show_access:
            await interaction.response.send_message(
                **error_card(
                    "Nothing to configure yet",
                    "There aren't any Rob preferences available to you here right now. "
                    "Register as a Dom/me, or ask staff to set up the leaderboard access role.",
                ).send_kwargs(),
                ephemeral=True,
            )
            return

        view = PreferencesView(
            default_leaderboard_visible=domme.leaderboard_visible if domme else True,
            default_leaderboard_access=has_access,
            show_domme_controls=domme is not None,
            show_leaderboard_access=show_access,
            intro_lines=(
                "## ⚙️ Your Rob preferences",
                "Pick your options below, then hit **Save preferences**.",
            ),
        )
        save_button = view.save_button

        async def _save_callback(inner: discord.Interaction) -> None:  # noqa: ANN001
            try:
                if domme is not None:
                    await self.bot.dommes_repo.set_preferences(
                        guild_id=inner.guild_id,
                        discord_user_id=inner.user.id,
                        leaderboard_visible=view.chosen_leaderboard_visible,
                        confirm=True,
                    )
                if show_access:
                    await apply_leaderboard_access(
                        self.bot,
                        guild_id=inner.guild_id,
                        user_id=inner.user.id,
                        enabled=view.chosen_leaderboard_access,
                    )
            except Exception:  # pragma: no cover - defensive
                log.exception("Failed to save preferences for user_id=%s", inner.user.id)
                await inner.response.send_message(
                    **error_card("Couldn't save", "Please try again later.").send_kwargs(),
                    ephemeral=True,
                )
                return
            await inner.response.edit_message(
                **render(
                    make_card(
                        title="Preferences saved!",
                        body="Your Rob preferences have been updated.",
                        color=COLOR_SUCCESS,
                        variant="success",
                    )
                ).edit_kwargs()
            )

        save_button.callback = _save_callback  # type: ignore[assignment]

        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(
        name="preferences",
        description="Change your leaderboard visibility and leaderboard access.",
    )
    async def preferences_command(self, interaction: discord.Interaction) -> None:
        await self._send_preferences_panel(interaction)

    @settings_group.command(
        name="preferences",
        description="Choose whether you appear on the leaderboard and your leaderboard access.",
    )
    async def preferences(self, interaction: discord.Interaction) -> None:
        await self._send_preferences_panel(interaction)
