from __future__ import annotations

import discord

from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_ROB_PURPLE


def privacy_card() -> RenderedMessage:
    require_components_v2()
    view = discord.ui.LayoutView(timeout=1800)

    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("## Rob Privacy Notice"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "Rob is built to run send tracking and safety features with minimal data use.\n"
                "This card explains what is collected and why."
            ),
            accent_color=COLOR_ROB_PURPLE,
        )
    )

    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("## What Data Rob Collects"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "-# Server and configuration IDs (guild/channel/role IDs)\n"
                "-# Discord user IDs needed for registrations and send attribution\n"
                "-# Send tracking data (amount, currency, method, item name/image, timestamps, status)\n"
                "-# Operational safety data (maintenance state, queue state, blacklist flags)\n"
                "-# Issue reports submitted through `/report`"
            ),
            accent_color=COLOR_ROB_PURPLE,
        )
    )

    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("## How That Data Is Used"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "-# To run leaderboard, send tracking, counting rescue, and registration features\n"
                "-# To prevent duplicate processing and keep webhook/send operations reliable\n"
                "-# To enforce server safety controls (role checks, moderation tooling, blacklist protection)\n"
                "-# To troubleshoot bot issues when a report is submitted"
            ),
            accent_color=COLOR_ROB_PURPLE,
        )
    )

    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("## Data Minimization Commitment"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "Rob and Pat will only use data that is required for Rob features and operations.\n"
                "Personal information that is not needed for send tracking or other Rob features is not part of Rob's intended data use.\n\n"
                "Please avoid submitting sensitive personal information in notes or reports."
            ),
            accent_color=COLOR_ROB_PURPLE,
        )
    )

    return RenderedMessage(view=view)
