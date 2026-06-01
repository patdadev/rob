from __future__ import annotations

import discord

from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_LEADER_ALERT


def leader_alert_card(user_mention: str) -> RenderedMessage:
    require_components_v2()
    view = discord.ui.LayoutView(timeout=1800)
    children = [
        discord.ui.TextDisplay("## 👑 NEW LEADER ALERT!"),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"Watch out every one! {user_mention} is now #1 on the send leaderboard!"),
        discord.ui.Separator(),
        discord.ui.TextDisplay("-# To view your rank on the leaderboard, run /leaderboard"),
    ]
    view.add_item(discord.ui.Container(*children, accent_color=COLOR_LEADER_ALERT))
    return RenderedMessage(view=view)
