from __future__ import annotations

import math

import discord

from rob.achievements.definitions import (
    ENABLED_ACHIEVEMENTS,
    RARITY_ORDER,
    AchievementDefinition,
)
from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_ROB_PURPLE, COLOR_SUCCESS, ROB_GOLD

_ENTRIES_PER_PAGE = 8
_RARITY_EMOJIS: dict[str, str] = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
    "secret": "🤫",
}

_RARITY_COLORS: dict[str, discord.Colour] = {
    "common": COLOR_SUCCESS,
    "uncommon": COLOR_SUCCESS,
    "rare": discord.Colour.from_rgb(59, 130, 246),
    "epic": COLOR_ROB_PURPLE,
    "legendary": ROB_GOLD,
    "secret": discord.Colour.from_rgb(120, 120, 120),
}


def _progress_bar(unlocked: int, total: int, *, width: int = 10) -> str:
    """Render a text-based progress bar."""
    if total == 0:
        return "░" * width
    filled = round((unlocked / total) * width)
    filled = min(filled, width)
    return "▓" * filled + "░" * (width - filled)


def achievement_unlocked_card(
    achievement: AchievementDefinition,
    *,
    unlocked_by_display_name: str | None = None,
    unlocked_by_user_id: int | None = None,
    include_meta_line: bool = False,
) -> RenderedMessage:
    require_components_v2()
    rarity_emoji = _RARITY_EMOJIS.get(achievement.rarity, "⚪")
    accent = _RARITY_COLORS.get(achievement.rarity, COLOR_SUCCESS)

    view = discord.ui.LayoutView(timeout=1800)
    children: list[discord.ui.Item] = [
        discord.ui.TextDisplay("-# 🏆 Achievement Unlocked"),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"### {achievement.title}"),
        discord.ui.TextDisplay(achievement.description),
        discord.ui.Separator(),
        discord.ui.TextDisplay(
            f"-# {rarity_emoji} {achievement.rarity_label}"
        ),
    ]
    if include_meta_line:
        children.append(
            discord.ui.TextDisplay(
                f"-# Key: {achievement.key} | Category: {achievement.category} | Rarity: {achievement.rarity}"
            )
        )
    if unlocked_by_display_name:
        children.append(discord.ui.Separator())
        children.append(
            discord.ui.TextDisplay(
                f"-# Achievement Unlocked by {unlocked_by_display_name}"
            )
        )
    view.add_item(discord.ui.Container(*children, accent_color=accent))
    content = None
    if unlocked_by_user_id is not None:
        content = f"<@{unlocked_by_user_id}>"
    return RenderedMessage(content=content, view=view)


def achievements_overview_cards(
    *,
    display_name: str,
    unlocked_achievements: list[AchievementDefinition],
    for_self: bool,
    newly_unlocked_count: int | None = None,
) -> list[RenderedMessage]:
    require_components_v2()
    unlocked_total = len(unlocked_achievements)
    total = len(ENABLED_ACHIEVEMENTS)
    page_count = max(1, math.ceil(unlocked_total / _ENTRIES_PER_PAGE)) if unlocked_total else 1

    progress = _progress_bar(unlocked_total, total)
    summary_line = f"{progress}  **{unlocked_total}/{total}** unlocked"
    if newly_unlocked_count and newly_unlocked_count > 0:
        summary_line = f"{summary_line} *(+{newly_unlocked_count} new)*"

    subtitle = "Your achievements" if for_self else f"{display_name}'s achievements"

    # Sort by rarity (higher rarity first) for display
    sorted_achievements = sorted(
        unlocked_achievements,
        key=lambda a: RARITY_ORDER.get(a.rarity, 0),
        reverse=True,
    )

    cards: list[RenderedMessage] = []
    for index in range(page_count):
        start = index * _ENTRIES_PER_PAGE
        page_achievements = sorted_achievements[start : start + _ENTRIES_PER_PAGE]
        view = discord.ui.LayoutView(timeout=1800)
        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## 🏆 {subtitle}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(summary_line),
            discord.ui.Separator(),
        ]

        if not page_achievements:
            empty_state = "No achievements unlocked yet."
            if for_self:
                empty_state = "You haven't unlocked any achievements yet."
                children.append(discord.ui.TextDisplay(empty_state))
                children.append(discord.ui.TextDisplay("-# Go do something suspiciously Rob-shaped."))
            else:
                empty_state = f"{display_name} hasn't unlocked any achievements yet."
                children.append(discord.ui.TextDisplay(empty_state))
        else:
            for achievement_index, achievement in enumerate(page_achievements):
                rarity_emoji = _RARITY_EMOJIS.get(achievement.rarity, "⚪")
                children.append(
                    discord.ui.TextDisplay(
                        f"{rarity_emoji} **{achievement.title}**\n-# {achievement.description}"
                    )
                )
                if achievement_index < len(page_achievements) - 1:
                    children.append(discord.ui.Separator())

        if page_count > 1:
            children.extend(
                [
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(f"-# Page {index + 1} of {page_count}"),
                ]
            )
        view.add_item(discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE))
        cards.append(RenderedMessage(view=view))

    return cards
