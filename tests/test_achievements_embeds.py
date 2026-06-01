from __future__ import annotations

from rob.achievements.definitions import ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY
from rob.achievements.embeds import achievement_unlocked_card, achievements_overview_cards


def _card_text(card) -> str:
    if card.embeds:
        embed = card.embeds[0]
        parts = [embed.title or "", embed.description or ""]
        parts.extend(field.name for field in embed.fields)
        parts.extend(field.value for field in embed.fields)
        parts.append(embed.footer.text if embed.footer else "")
        return "\n".join(part for part in parts if part)

    view = card.view
    assert view is not None
    return "\n".join(
        str(getattr(item, "content", ""))
        for container in view.children
        for item in getattr(container, "children", [])
    )


def _separator_count(card) -> int:
    view = card.view
    assert view is not None
    return sum(
        1
        for container in view.children
        for item in getattr(container, "children", [])
        if item.__class__.__name__ == "Separator"
    )


def test_achievements_catalogue_uses_compact_embed_field_layout():
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_achievements=[ACHIEVEMENTS_BY_KEY["count_10"]],
        for_self=True,
    )
    text = _card_text(cards[0])
    assert cards[0].embeds == []
    assert "Your achievements" in text
    assert "**1/" in text
    assert "unlocked" in text
    assert "**Double Digits**" in text
    assert "You counted to 10. Humanity may yet survive." in text


def test_locked_catalogue_entries_do_not_render_when_user_has_none_unlocked():
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_achievements=[],
        for_self=True,
    )
    text = "\n".join(_card_text(card) for card in cards)
    assert "Double Digits" not in text
    assert "haven't unlocked any achievements yet" in text
    assert "Go do something suspiciously Rob-shaped." in text


def test_other_user_empty_state_omits_self_prompt_copy():
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_achievements=[],
        for_self=False,
    )
    text = "\n".join(_card_text(card) for card in cards)
    assert "Pat hasn't unlocked any achievements yet." in text
    assert "Go do something suspiciously Rob-shaped." not in text


def test_catalogue_newly_unlocked_summary_label_is_explicit():
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_achievements=[ACHIEVEMENTS_BY_KEY["count_10"]],
        for_self=True,
        newly_unlocked_count=2,
    )
    text = _card_text(cards[0])
    assert "*(+2 new)*" in text


def test_catalogue_adds_separator_between_achievement_entries_only():
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_achievements=[ACHIEVEMENTS_BY_KEY["count_10"], ACHIEVEMENTS_BY_KEY["count_67"]],
        for_self=True,
    )
    # 2 entries with 1 separator between them, plus structural separators (after header, after progress)
    assert _separator_count(cards[0]) == 3


def test_catalogue_pages_cap_entries_per_page():
    unlocked = list(ACHIEVEMENTS)
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_achievements=unlocked,
        for_self=True,
    )
    assert cards
    total_rendered = 0
    for card in cards:
        text = _card_text(card)
        rendered_count = sum(
            1 for achievement in unlocked if f"**{achievement.title}**" in text
        )
        assert rendered_count <= 8
        total_rendered += rendered_count
    assert total_rendered == len(unlocked)


def test_unlock_card_uses_plain_title_and_unlocked_by_line():
    achievement = ACHIEVEMENTS_BY_KEY["count_4321"]
    card = achievement_unlocked_card(
        achievement,
        unlocked_by_display_name="Adore's Pickle Pat",
        unlocked_by_user_id=42,
    )
    text = _card_text(card)
    assert f"### {achievement.title}" in text
    assert achievement.description in text
    assert "Achievement Unlocked by Adore's Pickle Pat" in text
    assert card.content == "<@42>"


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


def test_unlock_card_shows_rarity_label():
    achievement = ACHIEVEMENTS_BY_KEY["count_420"]
    card = achievement_unlocked_card(achievement, unlocked_by_display_name="Pat")
    text = _card_text(card)
    assert "Rare" in text
    assert "🔵" in text


def test_unlock_card_shows_achievement_unlocked_header():
    achievement = ACHIEVEMENTS_BY_KEY["count_10"]
    card = achievement_unlocked_card(achievement, unlocked_by_display_name="Pat")
    text = _card_text(card)
    assert "Achievement Unlocked" in text


def test_overview_progress_bar_shows_for_partial_progress():
    from rob.achievements.embeds import _progress_bar
    bar = _progress_bar(5, 10)
    assert "▓" in bar
    assert "░" in bar
    assert len(bar) == 10
    assert bar.count("▓") == 5
    assert bar.count("░") == 5


def test_overview_progress_bar_full():
    from rob.achievements.embeds import _progress_bar
    bar = _progress_bar(10, 10)
    assert bar == "▓" * 10


def test_overview_progress_bar_empty():
    from rob.achievements.embeds import _progress_bar
    bar = _progress_bar(0, 10)
    assert bar == "░" * 10


def test_overview_sorts_by_rarity_descending():
    """Higher rarity achievements should appear first in the overview."""
    achievements = [
        ACHIEVEMENTS_BY_KEY["count_start"],  # common
        ACHIEVEMENTS_BY_KEY["count_10000"],  # legendary
        ACHIEVEMENTS_BY_KEY["count_420"],  # rare
    ]
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_achievements=achievements,
        for_self=True,
    )
    text = _card_text(cards[0])
    # Legendary should appear before rare, which should appear before common
    legendary_pos = text.find("Count Goblin Supreme")
    rare_pos = text.find("Suspiciously Herbal")
    common_pos = text.find("In the Beninging")
    assert legendary_pos < rare_pos < common_pos


def test_overview_page_number_only_shown_when_multi_page():
    cards = achievements_overview_cards(
        display_name="Pat",
        unlocked_achievements=[ACHIEVEMENTS_BY_KEY["count_10"]],
        for_self=True,
    )
    text = _card_text(cards[0])
    assert "Page" not in text
