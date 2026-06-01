from __future__ import annotations

from rob.achievements.definitions import (
    ACHIEVEMENTS,
    ACHIEVEMENTS_BY_KEY,
    CATEGORY_LABEL,
    RARITY_LABEL,
    RARITY_ORDER,
    achievements_by_category,
    sort_by_rarity,
)
from rob.achievements.embeds import achievement_unlocked_card


def test_achievement_keys_are_unique():
    keys = [achievement.key for achievement in ACHIEVEMENTS]
    assert len(keys) == len(set(keys))


def test_required_achievement_keys_exist():
    required = {
        "count_67",
        "count_4321",
        "domme_first_tracked_send",
        "sub_first_send",
        "throne_tracking_started",
        "first_achievement_view",
    }
    assert required.issubset(set(ACHIEVEMENTS_BY_KEY))


def test_count_67_and_4321_use_required_copy():
    count_67 = ACHIEVEMENTS_BY_KEY["count_67"]
    count_4321 = ACHIEVEMENTS_BY_KEY["count_4321"]
    assert count_67.title == "The 67 Incident"
    assert (
        count_67.description
        == "You said 67. Rob doesn’t know why this matters, but apparently it does."
    )
    assert count_4321.title == "Suspiciously Numerical"
    assert (
        count_4321.description
        == "You said 4321. That’s not a number, that’s a countdown in disguise."
    )


def test_secret_achievement_is_hidden():
    achievement = ACHIEVEMENTS_BY_KEY["secret_command"]
    assert achievement.hidden is True
    assert achievement.rarity == "secret"
    assert achievement.enabled is True


def test_preview_renderer_can_iterate_all_achievements():
    for achievement in ACHIEVEMENTS:
        rendered = achievement_unlocked_card(achievement, include_meta_line=True)
        assert rendered.view is not None
        assert rendered.view.children


def test_rarity_order_covers_all_rarity_values():
    rarities_in_achievements = {a.rarity for a in ACHIEVEMENTS}
    for rarity in rarities_in_achievements:
        assert rarity in RARITY_ORDER
        assert rarity in RARITY_LABEL


def test_category_label_covers_all_category_values():
    categories_in_achievements = {a.category for a in ACHIEVEMENTS}
    for category in categories_in_achievements:
        assert category in CATEGORY_LABEL


def test_achievement_definition_rarity_rank_property():
    common = ACHIEVEMENTS_BY_KEY["count_start"]
    legendary = ACHIEVEMENTS_BY_KEY["count_10000"]
    secret = ACHIEVEMENTS_BY_KEY["secret_command"]
    assert common.rarity_rank < legendary.rarity_rank
    assert secret.rarity_rank == RARITY_ORDER["secret"]


def test_achievement_definition_label_properties():
    achievement = ACHIEVEMENTS_BY_KEY["count_10"]
    assert achievement.rarity_label == "Common"
    assert achievement.category_label == "Counting"


def test_sort_by_rarity_orders_correctly():
    items = [
        ACHIEVEMENTS_BY_KEY["count_10000"],  # legendary
        ACHIEVEMENTS_BY_KEY["count_start"],  # common
        ACHIEVEMENTS_BY_KEY["count_420"],  # rare
    ]
    sorted_items = sort_by_rarity(items)
    assert sorted_items[0].rarity == "common"
    assert sorted_items[1].rarity == "rare"
    assert sorted_items[2].rarity == "legendary"

    reversed_items = sort_by_rarity(items, reverse=True)
    assert reversed_items[0].rarity == "legendary"
    assert reversed_items[2].rarity == "common"


def test_achievements_by_category_groups_correctly():
    grouped = achievements_by_category(ACHIEVEMENTS)
    assert "count" in grouped
    assert "sends_domme" in grouped
    assert all(a.category == "count" for a in grouped["count"])
    assert all(a.category == "sends_domme" for a in grouped["sends_domme"])
