from __future__ import annotations

import pytest
import discord

from rob.ui.cards.registration import throne_setup_card
from rob.ui.render import CardSection, RenderedMessage, RobCard, add_action_row, render_card, supports_components_v2


def test_components_v2_support_check_exposes_required_runtime():
    assert supports_components_v2() is True


def test_render_card_returns_layoutview_not_embed():
    msg = render_card(RobCard(title="T", body="B", sections=[CardSection(title="S", text="V")]))
    assert msg.view is not None
    assert msg.mode == "components_v2"


def test_send_kwargs_do_not_include_embed_fields():
    kwargs = RenderedMessage(view=None).send_kwargs()
    assert "embed" not in kwargs
    assert "embeds" not in kwargs


def test_v2_edit_kwargs_clear_legacy_fields_and_keep_view():
    msg = render_card(RobCard(title="T", body="B"))
    kwargs = msg.edit_kwargs()
    assert kwargs["content"] is None
    assert kwargs["embed"] is None
    assert kwargs["embeds"] is None
    assert kwargs["attachments"] is None
    assert kwargs["view"] is msg.view


def test_setup_success_card_accepts_image_url_without_embed_mutation():
    msg = throne_setup_card("ok", image_url="https://example.com/test.gif")
    assert msg.view is not None


def test_render_card_raises_if_components_v2_missing(monkeypatch: pytest.MonkeyPatch):
    import discord

    monkeypatch.delattr(discord.ui, "LayoutView", raising=False)
    with pytest.raises(RuntimeError):
        render_card(RobCard(title="X", body="Y"))


def test_render_card_rejects_prepopulated_layout_to_enforce_container_first_order():
    import discord

    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Button(label="X"))
    with pytest.raises(RuntimeError):
        render_card(RobCard(title="T", body="B"), view=view)


def test_title_uses_h2_markdown():
    msg = render_card(RobCard(title="Hello", body="Body"))
    assert "## Hello" in str(msg.view.children[0].children[0].content)


def test_add_action_row_puts_buttons_in_top_level_action_row():
    msg = throne_setup_card("hello")
    add_action_row(msg.view, discord.ui.Button(label="Continue"), discord.ui.Button(label="Not Now"))
    assert type(msg.view.children[0]).__name__ == "Container"
    assert type(msg.view.children[1]).__name__ == "ActionRow"
    assert type(msg.view.children[1].children[0]).__name__ == "Button"
    assert type(msg.view.children[1].children[1]).__name__ == "Button"
