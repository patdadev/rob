from __future__ import annotations

from rob.achievements.embeds import achievement_unlocked_card, achievements_overview_cards
from rob.achievements.definitions import ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY


def _card_text(card) -> str:
    view = card.view
    assert view is not None
    return "\n".join(
        str(getattr(item, "content", ""))
        for container in view.children
        for item in getattr(container, "children", [])
    )


def _catalogue_entry_count(card) -> int:
    view = card.view
    assert view is not None
    container = view.children[0]
    count = 0
    for item in getattr(container, "children", []):
        content = str(getattr(item, "content", "")).strip()
        if not content:
            continue
        if content.startswith("## Rob Achievements"):
            continue
        if content.startswith("Achievements unlocked:"):
            continue
        if content.startswith("-# Your unlocked achievements"):
            continue
        if content.startswith("-# Viewing:"):
            continue
        if content.startswith("-# Page "):
            continue
        count += len([part for part in content.split("\n\n") if part.strip()])
    return count


def test_achievements_catalogue_uses_compact_entry_layout():
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_keys={"domme_first_tracked_send"},
        for_self=True,
    )
    text = _card_text(cards[0])
    assert "## Rob Achievements" in text
    assert "Achievements unlocked: **1/" in text
    assert "🏆 **First Send Tracked**" in text
    assert "Ooo, you got your first tracked send." in text


def test_locked_hidden_achievements_do_not_render_in_user_catalogue():
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_keys=set(),
        for_self=True,
    )
    text = "\n".join(_card_text(card) for card in cards)
    assert "Secret Achievement" not in text
    assert "???" not in text
    assert "You have not unlocked any achievements yet." in text


def test_catalogue_pages_cap_entries_per_page_to_ten():
    unlocked_keys = {achievement.key for achievement in ACHIEVEMENTS[:15]}
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_keys=unlocked_keys,
        for_self=True,
    )
    assert cards
    for card in cards:
        assert _catalogue_entry_count(card) <= 10


def test_unlock_card_header_and_unlocked_by_line():
    achievement = ACHIEVEMENTS_BY_KEY["count_4321"]
    card = achievement_unlocked_card(
        achievement,
        unlocked_by_display_name="Adore's Pickle Pat",
    )
    text = _card_text(card)
    assert "Achievement Unlocked" not in text
    assert f"## 🥇 {achievement.title}" in text
    assert achievement.title in text
    assert achievement.description in text
    assert "Unlocked by Adore's Pickle Pat" in text


def test_unlock_card_hides_debug_metadata_by_default():
    achievement = ACHIEVEMENTS_BY_KEY["sub_100_sent"]
    card = achievement_unlocked_card(achievement, unlocked_by_display_name="Pat")
    text = _card_text(card)
    assert "Key:" not in text
    assert "Category:" not in text
    assert "Rarity:" not in text


def test_unlock_card_can_show_debug_metadata_when_explicitly_enabled():
    achievement = ACHIEVEMENTS_BY_KEY["sub_100_sent"]
    card = achievement_unlocked_card(
        achievement,
        unlocked_by_display_name="Pat",
        include_meta_line=True,
    )
    text = _card_text(card)
    assert "Key:" in text
