from __future__ import annotations

from datetime import datetime

import discord

from rob.achievements.definitions import ACHIEVEMENTS_BY_KEY
from rob.achievements.embeds import (
    achievement_unlocked_card,
    render_server_achievements_message,
    render_user_achievements_message,
)
from rob.achievements.service import (
    AchievementServerRecentUnlock,
    AchievementServerStats,
    AchievementServerUserStanding,
    AchievementUnlockState,
)


def _card_text(card) -> str:
    view = card.view
    assert view is not None

    def _walk(items) -> list[str]:
        parts: list[str] = []
        for item in items:
            content = getattr(item, "content", None)
            if content:
                parts.append(str(content))
            children = getattr(item, "children", None)
            if children:
                parts.extend(_walk(children))
        return parts

    return "\n".join(_walk(view.children))


def _button_labels(card) -> list[str]:
    view = card.view
    assert view is not None
    labels: list[str] = []
    for child in view.children:
        for nested in getattr(child, "children", []):
            label = getattr(nested, "label", None)
            if label is not None:
                labels.append(str(label))
    return labels


def _select_placeholders(card) -> list[str]:
    view = card.view
    assert view is not None
    placeholders: list[str] = []
    for child in view.children:
        for nested in getattr(child, "children", []):
            if isinstance(nested, discord.ui.Select):
                placeholders.append(str(nested.placeholder))
    return placeholders


def test_unlock_card_keeps_mentions_inside_components_v2_view():
    achievement = ACHIEVEMENTS_BY_KEY["count_10"]

    card = achievement_unlocked_card(
        achievement,
        unlocked_by_display_name="Pat",
        unlocked_by_user_id=42,
    )

    assert card.view is not None
    assert "content" not in card.send_kwargs()
    assert "<@42>" in _card_text(card)


def test_user_achievements_renderer_hides_locked_secret_and_adds_filters():
    states = [
        AchievementUnlockState(
            definition=ACHIEVEMENTS_BY_KEY["count_10"],
            unlocked_at=datetime(2026, 1, 2),
        ),
        AchievementUnlockState(definition=ACHIEVEMENTS_BY_KEY["secret_command"]),
    ]

    card = render_user_achievements_message(
        owner_user_id=10,
        title="Pat",
        subtitle="Your achievement cabinet",
        icon_url=None,
        states=states,
        allow_public_share=True,
        empty_callout="Go unlock something.",
    )

    text = _card_text(card)
    assert "Your achievement cabinet" in text
    assert "Double Digits" in text
    assert "???" in text
    assert "Shhhh..." not in text
    assert "content" not in card.send_kwargs()
    assert _button_labels(card) == ["◀ Previous", "Next ▶", "Share publicly"]
    assert _select_placeholders(card) == [
        "Filter by category",
        "Show locked, unlocked, or all",
    ]


def test_server_achievements_renderer_uses_components_v2_payload():
    stats = AchievementServerStats(
        members_with_unlocks=3,
        unlock_counts={
            "count_10": 3,
            "secret_command": 1,
        },
        recent_unlocks=[
            AchievementServerRecentUnlock(
                discord_user_id=42,
                definition=ACHIEVEMENTS_BY_KEY["count_10"],
                unlocked_at=datetime(2026, 1, 2),
            )
        ],
        top_users=[AchievementServerUserStanding(discord_user_id=42, unlocked_count=2)],
    )

    card = render_server_achievements_message(
        owner_user_id=10,
        server_name="VIB",
        server_icon_url=None,
        member_count=10,
        stats=stats,
    )

    text = _card_text(card)
    assert "VIB achievements" in text
    assert "Members with unlocks: **3**" in text
    assert "Just unlocked" in text
    assert "Leaderboard" in text
    assert "content" not in card.send_kwargs()
    assert _select_placeholders(card) == ["Filter server stats by category"]
