from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from rob.ui.cards.privacy import privacy_card

if TYPE_CHECKING:
    from rob.discord.client import RobBot


class PrivacyCog(commands.Cog):
    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

    @app_commands.command(name="privacy", description="Show Rob's privacy and data use notice.")
    async def privacy(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(**privacy_card().send_kwargs(), ephemeral=False)
