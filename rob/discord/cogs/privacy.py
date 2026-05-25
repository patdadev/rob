from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from rob.ui.cards.privacy import privacy_notice_message

if TYPE_CHECKING:
    from rob.discord.client import RobBot


class PrivacyCog(commands.Cog):
    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="privacy",
        description="View Rob's privacy notice, including what information may be collected, stored, and used.",
    )
    async def privacy(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            **privacy_notice_message().send_kwargs(),
            ephemeral=True,
        )
