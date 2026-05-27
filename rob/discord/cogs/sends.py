from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from discord import app_commands
from discord.ext import commands

from rob.ui.cards.errors import error_card
from rob.ui.cards.registration import registration_card
from rob.utils.money import dollars_to_cents, format_money_from_cents

if TYPE_CHECKING:
    import discord

    from rob.discord.client import RobBot


_MANUAL_METHODS = ["cashapp", "venmo", "paypal", "onlyfans", "loyalfans", "youpay", "other"]


class SendsCog(commands.Cog):
    def __init__(self, bot: RobBot) -> None:
        self.bot = bot

    @app_commands.command(name="add", description="Log a manual send for the leaderboard.")
    @app_commands.describe(
        amount="Amount sent in USD.",
        method="Where the send happened.",
        sub="Optional sending name to attribute.",
        note="Optional item or note for the send.",
    )
    @app_commands.choices(method=[app_commands.Choice(name=value, value=value) for value in _MANUAL_METHODS])
    async def add_send(
        self,
        interaction: "discord.Interaction",
        amount: app_commands.Range[float, 0.01],
        method: app_commands.Choice[str],
        sub: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        if interaction.guild is None or interaction.user is None:
            await interaction.response.send_message(
                **error_card("This command can only be used in a server.").send_kwargs(),
                ephemeral=True,
            )
            return

        domme = await self.bot.dommes_repo.get_by_user_id(
            interaction.guild.id,
            interaction.user.id,
        )
        if domme is None:
            await interaction.response.send_message(
                **error_card("Only registered Dom/mes can use `/add`.").send_kwargs(),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        send = await self.bot.send_service.record_manual_send(
            guild_id=interaction.guild.id,
            domme_id=domme.id,
            domme_user_id=interaction.user.id,
            sub_name=(sub or "").strip() or None,
            amount_cents=dollars_to_cents(float(amount)),
            currency="USD",
            method=method.value,
            note=(note or "").strip() or None,
        )
        if send is None:
            await interaction.followup.send(
                **error_card("That send could not be recorded.").send_kwargs(),
                ephemeral=True,
            )
            return

        queue_label = (
            "queued for after maintenance"
            if send.discord_post_status == "queued_maintenance"
            else "queued for posting"
        )
        await interaction.followup.send(
            **registration_card(
                title="Rob | Send Logged",
                summary=f"Recorded {format_money_from_cents(send.amount_cents)} and {queue_label}.",
                details=[
                    ("Method", method.value),
                    ("Sender", send.sub_name or "Unclaimed"),
                ],
            ).send_kwargs(),
            ephemeral=True,
        )

