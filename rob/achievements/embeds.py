from __future__ import annotations

import discord

from rob.achievements.definitions import ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY, AchievementDefinition
from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_ROB_PURPLE, COLOR_SUCCESS

_ENTRIES_PER_PAGE = 24


def achievement_icon(achievement: AchievementDefinition, *, unlocked: bool) -> str:
    if not unlocked and achievement.hidden:
        return "⚪"
    return {
        "common": "🏆",
        "uncommon": "🥉",
        "rare": "🥈",
        "epic": "🥇",
        "legendary": "👑",
        "secret": "❔",
    }.get(achievement.rarity, "🏆")


def _catalogue_entry(achievement: AchievementDefinition, *, unlocked: bool) -> str:
    if not unlocked and achievement.hidden:
        return "⚪ **Secret Achievement**\n???"
    return f"{achievement_icon(achievement, unlocked=unlocked)} **{achievement.title}**\n{achievement.description}"


def achievement_unlocked_card(
    achievement: AchievementDefinition,
    *,
    unlocked_by_display_name: str | None = None,
    include_meta_line: bool = False,
) -> RenderedMessage:
    require_components_v2()
    view = discord.ui.LayoutView(timeout=1800)
    children: list[discord.ui.Item] = [
        discord.ui.TextDisplay("## 🏆 Achievement Unlocked"),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"**{achievement.title}**\n{achievement.description}"),
    ]
    if include_meta_line:
        children.append(discord.ui.Separator())
        children.append(
            discord.ui.TextDisplay(
                f"-# Key: {achievement.key} | Category: {achievement.category} | Rarity: {achievement.rarity}"
            )
        )
    if unlocked_by_display_name:
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# Unlocked by {unlocked_by_display_name}"))
    view.add_item(discord.ui.Container(*children, accent_color=COLOR_SUCCESS))
    return RenderedMessage(view=view)


def achievements_overview_cards(
    *,
    display_name: str,
    unlocked_keys: set[str],
    for_self: bool,
    newly_unlocked_count: int | None = None,
) -> list[RenderedMessage]:
    require_components_v2()
    known_unlocked = {key for key in unlocked_keys if key in ACHIEVEMENTS_BY_KEY}

    entries = [
        _catalogue_entry(achievement, unlocked=achievement.key in known_unlocked)
        for achievement in ACHIEVEMENTS
    ]

    pages: list[list[str]] = []
    for start in range(0, len(entries), _ENTRIES_PER_PAGE):
        pages.append(entries[start : start + _ENTRIES_PER_PAGE])

    summary_line = f"Achievements unlocked (total): **{len(known_unlocked)}/{len(ACHIEVEMENTS)}**"
    if newly_unlocked_count and newly_unlocked_count > 0:
        summary_line = f"{summary_line} +{newly_unlocked_count}"
    viewed_line = f"-# Viewing: {display_name}"
    subtitle = "-# Your profile" if for_self else viewed_line

    cards: list[RenderedMessage] = []
    for index, page in enumerate(pages):
        view = discord.ui.LayoutView(timeout=1800)
        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay("## Rob Achievements"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"{summary_line}\n{subtitle}"),
            discord.ui.Separator(),
        ]

        for start in range(0, len(page), 8):
            column_chunk = page[start : start + 8]
            if not column_chunk:
                continue
            children.append(discord.ui.TextDisplay("\n\n".join(column_chunk)))

        if len(pages) > 1:
            children.append(discord.ui.Separator())
            children.append(discord.ui.TextDisplay(f"-# Page {index + 1}/{len(pages)}"))
        view.add_item(discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE))
        cards.append(RenderedMessage(view=view))

    return cards
