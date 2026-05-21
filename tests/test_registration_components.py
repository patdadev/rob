from __future__ import annotations

import discord

from rob.discord.cogs.registration import add_setup_buttons
from rob.ui.cards.registration import throne_setup_card


def test_add_setup_buttons_creates_action_row_not_top_level_buttons():
    msg = throne_setup_card("setup")
    add_setup_buttons(msg.view, creator_id=1, webhook_url="https://example.com/webhook", send_track_channel_id=123)
    assert type(msg.view.children[0]).__name__ == "Container"
    assert type(msg.view.children[1]).__name__ == "ActionRow"
    assert all(isinstance(child, discord.ui.Button) for child in msg.view.children[1].children)
    assert all(type(child).__name__ != "Button" for child in msg.view.children)
