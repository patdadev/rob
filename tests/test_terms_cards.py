from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from rob.ui.cards.terms import (
    AcceptButton,
    DeclineButton,
    ID_TERMS_ACCEPT,
    ID_TERMS_DECLINE,
    current_privacy_card,
    current_terms_card,
    terms_accepted_card,
    terms_declined_card,
    terms_dm_blocked_card,
    terms_prompt_card,
)


def _find_button(view: discord.ui.LayoutView, *, custom_id: str) -> discord.ui.Button | None:
    for item in view.walk_children():
        if isinstance(item, discord.ui.Button) and item.custom_id == custom_id:
            return item
    return None


def _find_link_buttons(view: discord.ui.LayoutView) -> list[discord.ui.Button]:
    buttons: list[discord.ui.Button] = []
    for item in view.walk_children():
        if isinstance(item, discord.ui.Button) and item.url:
            buttons.append(item)
    return buttons


def _all_text(view: discord.ui.LayoutView) -> str:
    return " ".join(
        item.content for item in view.walk_children() if isinstance(item, discord.ui.TextDisplay)
    )


def test_terms_prompt_card_has_links_and_accept_decline_buttons():
    rendered = terms_prompt_card(
        terms_url="https://example.com/terms",
        privacy_url="https://example.com/privacy",
    )
    assert _find_button(rendered.view, custom_id=ID_TERMS_ACCEPT) is not None
    assert _find_button(rendered.view, custom_id=ID_TERMS_DECLINE) is not None
    link_buttons = _find_link_buttons(rendered.view)
    assert [button.label for button in link_buttons] == ["Terms of Use", "Privacy Notice"]


def test_terms_accepted_card_disables_accept_and_removes_decline():
    rendered = terms_accepted_card()
    accept = _find_button(rendered.view, custom_id=ID_TERMS_ACCEPT)
    decline = _find_button(rendered.view, custom_id=ID_TERMS_DECLINE)
    assert accept is not None
    assert accept.disabled is True
    assert accept.label == "Accepted"
    assert decline is None


def test_terms_declined_card_disables_decline_and_removes_accept():
    rendered = terms_declined_card()
    accept = _find_button(rendered.view, custom_id=ID_TERMS_ACCEPT)
    decline = _find_button(rendered.view, custom_id=ID_TERMS_DECLINE)
    assert accept is None
    assert decline is not None
    assert decline.disabled is True
    assert decline.label == "Declined"


def test_terms_dm_blocked_card_contains_expected_copy():
    rendered = terms_dm_blocked_card(name="Aria")
    text = _all_text(rendered.view)
    assert "I couldn't send you a DM" in text
    assert "Hey Aria!" in text
    assert "Please allow DMs from this server" in text


def test_terms_and_privacy_cards_include_current_version_and_link_buttons():
    terms = current_terms_card(
        terms_version="2026-06-05",
        terms_url="https://example.com/terms",
    )
    privacy = current_privacy_card(
        terms_version="2026-06-05",
        privacy_url="https://example.com/privacy",
    )
    assert "2026-06-05" in _all_text(terms.view)
    assert "2026-06-05" in _all_text(privacy.view)
    assert [button.label for button in _find_link_buttons(terms.view)] == ["Open Terms of Use"]
    assert [button.label for button in _find_link_buttons(privacy.view)] == ["Open Privacy Notice"]


def test_accept_and_decline_buttons_route_to_cog_callbacks():
    cog = SimpleNamespace(
        handle_accept=AsyncMock(),
        handle_decline=AsyncMock(),
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=1),
        response=SimpleNamespace(send_message=AsyncMock()),
        data={"custom_id": "x"},
        channel_id=10,
        guild_id=None,
    )

    asyncio.run(AcceptButton(cog).callback(interaction))
    asyncio.run(DeclineButton(cog).callback(interaction))

    cog.handle_accept.assert_awaited_once_with(interaction)
    cog.handle_decline.assert_awaited_once_with(interaction)
