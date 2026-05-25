from __future__ import annotations

from datetime import datetime, timezone

from rob.database.repositories.models import LeaderboardEntry, LeaderboardSummary, SendRecord
from rob.services.leaderboard_status import LeaderboardStatus
from rob.services.send_display import build_sub_display
from rob.ui.cards.leader_alert import leader_alert_card
from rob.ui.cards.leaderboard import leaderboard_card, leaderboard_stats_card
from rob.ui.cards.privacy import privacy_card
from rob.ui.cards.send import send_card
from rob.ui.copy import throne_setup_steps
from rob.ui.theme import COLOR_LEADER_ALERT, COLOR_SEND


def _send(
    sub_name: str | None = None,
    *,
    item_image_url: str | None = None,
    is_test_send: bool = False,
) -> SendRecord:
    now = datetime.now(timezone.utc)
    return SendRecord(
        1,
        1,
        None,
        10,
        None,
        None,
        sub_name,
        1099,
        "USD",
        None,
        "throne_webhook",
        "Flowers",
        item_image_url,
        None,
        None,
        None,
        False,
        False,
        now,
        now,
        "posted",
        None,
        None,
        None,
        now,
        is_test_send,
    )


def test_setup_step_2_contains_almighty_link():
    text = throne_setup_steps("https://example.com/hook")
    assert "The almighty link" in text
    assert "https://example.com/hook" in text


def test_send_card_renders_thumbnail_image_and_currency_name():
    msg = send_card(
        send=_send("marie_123", item_image_url="https://example.com/item.png", is_test_send=True),
        domme_label="@Domme",
        sub_display="Throne's Test User",
    )
    container = msg.view.children[0]
    section = container.children[2]
    all_text = "\n".join(
        str(getattr(child, "content", ""))
        for child in [container.children[0], section.children[0]]
    )

    assert [type(child).__name__ for child in container.children] == [
        "TextDisplay",
        "Separator",
        "Section",
    ]
    assert type(section.accessory).__name__ == "Thumbnail"
    assert "New Send to @Domme" in all_text
    assert "Throne's Test User" in all_text
    assert "$10.99 (United States Dollar)" in all_text
    assert "Rob Send ID" not in all_text
    assert "rank after this send" not in all_text
    assert "<t:" not in all_text
    assert msg.view.children[0].accent_color == COLOR_SEND
    payload = msg.view.to_components()
    assert payload[0]["components"][2]["type"] == 9
    assert payload[0]["components"][2]["accessory"]["type"] == 11
    assert payload[0]["components"][2]["accessory"]["media"]["url"] == "https://example.com/item.png"


def test_send_card_without_image_uses_text_display_and_no_footer():
    msg = send_card(send=_send("gifter_name"), domme_label="@Domme", sub_display="gifter_name with no nickname claimed")
    container = msg.view.children[0]
    contents = "\n".join(str(getattr(ch, "content", "")) for ch in container.children)
    assert [type(child).__name__ for child in container.children] == [
        "TextDisplay",
        "Separator",
        "TextDisplay",
    ]
    assert "gifter_name with no nickname claimed" in contents
    assert "-#" not in contents


def test_send_request_send_card_shows_sub_mention_when_sub_user_is_known():
    now = datetime.now(timezone.utc)
    send = SendRecord(
        9,
        1,
        None,
        10,
        None,
        42,
        None,
        2499,
        "USD",
        "paypal",
        "send_request",
        "Thanks",
        None,
        None,
        None,
        None,
        False,
        False,
        now,
        now,
        "posted",
        None,
        None,
        None,
        now,
    )
    msg = send_card(
        send=send,
        domme_label="@Dom/me",
        sub_display=build_sub_display(send),
    )
    contents = "\n".join(str(getattr(ch, "content", "")) for ch in msg.view.children[0].children)
    assert "**Sub:** <@42>" in contents
    assert "**Service:** paypal" in contents
    assert "Rob Send ID" not in contents


def test_leaderboard_main_and_stats_titles_and_separators():
    entries = [
        LeaderboardEntry("@A", 1, 12345, 7),
        LeaderboardEntry("@B", 2, 9000, 3),
        LeaderboardEntry("@C", 3, 5000, 2),
        LeaderboardEntry("@D", 4, 0, 0),
    ]
    summary = LeaderboardSummary(26345, 12, 4, 2, 1, 1099)
    main = leaderboard_card(title="ignored", entries=entries, summary=summary)
    stats = leaderboard_stats_card(summary, entries)
    main_children = main.view.children[0].children
    stats_children = stats.view.children[0].children
    main_contents = "\n".join(str(getattr(ch, "content", "")) for ch in main_children)
    stats_contents = "\n".join(str(getattr(ch, "content", "")) for ch in stats_children)

    assert [type(child).__name__ for child in main_children] == [
        "TextDisplay",
        "Separator",
        "TextDisplay",
        "Separator",
        "TextDisplay",
        "Separator",
        "TextDisplay",
    ]
    assert "🏆 Thy Send Leaderboard" in main_contents
    assert "🥇" in main_contents and "🥈" in main_contents and "🥉" in main_contents and "#4" in main_contents
    assert "-# 🟢 Live" in main_contents

    assert [type(child).__name__ for child in stats_children] == ["TextDisplay", "Separator", "TextDisplay"]
    assert "🏆 Thy Send Leaderboard | Stats" in stats_contents
    assert "Leaderboard last updated" in stats_contents
    assert "Unclaimed Sends" in stats_contents
    assert "👑" not in stats_contents and "🦹‍♀️" not in stats_contents and "💸" not in stats_contents
    assert "-# " in stats_contents


def test_leaderboard_offline_status_renders_when_explicit():
    summary = LeaderboardSummary(0, 0, 0, 0, 0, 0)
    msg = leaderboard_card(
        title="ignored",
        entries=[],
        summary=summary,
        status=LeaderboardStatus.OFFLINE,
    )
    contents = "\n".join(str(getattr(ch, "content", "")) for ch in msg.view.children[0].children)
    assert "-# 🔴 Offline" in contents


def test_leaderboard_stats_footer_is_only_rendered_when_explicit():
    summary = LeaderboardSummary(0, 0, 1, 0, 0, 0)
    msg = leaderboard_stats_card(summary, [], footer="Explicit footer only")
    children = msg.view.children[0].children
    contents = "\n".join(str(getattr(ch, "content", "")) for ch in children)

    assert [type(child).__name__ for child in children] == [
        "TextDisplay",
        "Separator",
        "TextDisplay",
        "Separator",
        "TextDisplay",
    ]
    assert "-# Explicit footer only" in contents


def test_leaderboard_empty_state_uses_same_separator_structure():
    summary = LeaderboardSummary(0, 0, 0, 0, 0, 0)
    main = leaderboard_card(title="ignored", entries=[], summary=summary)
    children = main.view.children[0].children
    assert [type(child).__name__ for child in children] == [
        "TextDisplay",
        "Separator",
        "TextDisplay",
        "Separator",
        "TextDisplay",
        "Separator",
        "TextDisplay",
    ]
    assert "No sends have made it onto the board yet." in children[4].content


def test_leader_alert_card_shape_and_color():
    msg = leader_alert_card("<@123>")
    children = msg.view.children[0].children
    all_text = "\n".join(str(getattr(ch, "content", "")) for ch in children)
    assert [type(child).__name__ for child in children] == [
        "TextDisplay",
        "Separator",
        "TextDisplay",
        "Separator",
        "TextDisplay",
    ]
    assert "👑 NEW LEADER ALERT!" in all_text
    assert msg.view.children[0].accent_color == COLOR_LEADER_ALERT


def test_privacy_card_uses_multiple_containers_and_policy_language():
    msg = privacy_card()
    assert len(msg.view.children) >= 4
    for container in msg.view.children:
        assert type(container).__name__ == "Container"
    all_text = "\n".join(
        str(getattr(item, "content", ""))
        for container in msg.view.children
        for item in getattr(container, "children", [])
    )
    assert "Rob Privacy Notice" in all_text
    assert "Information Collected or Received" in all_text
    assert "Purpose of Processing" in all_text
    assert "Data Minimisation and Third-Party Services" in all_text
    assert "Privacy Notice valid as of 25/05/2026" in all_text
