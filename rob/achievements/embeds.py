from __future__ import annotations

import discord

from rob.achievements.definitions import ENABLED_ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY, AchievementDefinition
from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_ROB_PURPLE, COLOR_SUCCESS

_ENTRIES_PER_PAGE = 10


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


def _catalogue_entry(achievement: AchievementDefinition) -> str:
    return f"{achievement_icon(achievement, unlocked=True)} **{achievement.title}**\n{achievement.description}"


def achievement_unlocked_card(
    achievement: AchievementDefinition,
    *,
    unlocked_by_display_name: str | None = None,
    include_meta_line: bool = False,
) -> RenderedMessage:
    require_components_v2()
    view = discord.ui.LayoutView(timeout=1800)
    title_icon = achievement_icon(achievement, unlocked=True)
    children: list[discord.ui.Item] = [
        discord.ui.TextDisplay(f"## {title_icon} {achievement.title}"),
        discord.ui.Separator(),
        discord.ui.TextDisplay(achievement.description),
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
    enabled_keys = {achievement.key for achievement in ENABLED_ACHIEVEMENTS}
    known_unlocked = known_unlocked & enabled_keys
    unlocked_achievements = [
        achievement for achievement in ENABLED_ACHIEVEMENTS if achievement.key in known_unlocked
    ]
    entries = [_catalogue_entry(achievement) for achievement in unlocked_achievements]

    pages: list[list[str]] = []
    if entries:
        for start in range(0, len(entries), _ENTRIES_PER_PAGE):
            pages.append(entries[start : start + _ENTRIES_PER_PAGE])
    else:
        pages.append([])

    summary_line = f"Achievements unlocked: **{len(known_unlocked)}/{len(ENABLED_ACHIEVEMENTS)}**"
    if newly_unlocked_count and newly_unlocked_count > 0:
        summary_line = f"{summary_line} +{newly_unlocked_count}"
    subtitle = "-# Your unlocked achievements" if for_self else f"-# Viewing: {display_name}"

    cards: list[RenderedMessage] = []
    for index, page in enumerate(pages):
        view = discord.ui.LayoutView(timeout=1800)
        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay("## Rob Achievements"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"{summary_line}\n{subtitle}"),
            discord.ui.Separator(),
        ]

        if page:
            children.append(discord.ui.TextDisplay("\n\n".join(page)))
        elif for_self:
            children.append(
                discord.ui.TextDisplay(
                    "You have not unlocked any achievements yet.\n"
                    "Go do something suspiciously Rob-shaped."
                )
            )
        else:
            children.append(discord.ui.TextDisplay(f"{display_name} has not unlocked any achievements yet."))

        if len(pages) > 1:
            children.append(discord.ui.Separator())
            children.append(discord.ui.TextDisplay(f"-# Page {index + 1}/{len(pages)}"))
        view.add_item(discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE))
        cards.append(RenderedMessage(view=view))

    return cards
