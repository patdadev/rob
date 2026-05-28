from __future__ import annotations

from rob.achievements.definitions import ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY
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


def test_preview_renderer_can_iterate_all_achievements():
    for achievement in ACHIEVEMENTS:
        rendered = achievement_unlocked_card(achievement, include_meta_line=True)
        assert rendered.view is not None
        assert rendered.view.children

