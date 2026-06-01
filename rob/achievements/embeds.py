from __future__ import annotations

import math

import discord

from rob.achievements.definitions import (
    ENABLED_ACHIEVEMENTS,
    AchievementDefinition,
)
from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_ROB_PURPLE, COLOR_SUCCESS

_ENTRIES_PER_PAGE = 10
_RARITY_EMOJIS: dict[str, str] = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
    "secret": "🤫",
}


def achievement_unlocked_card(
    achievement: AchievementDefinition,
    *,
    unlocked_by_display_name: str | None = None,
    unlocked_by_user_id: int | None = None,
    include_meta_line: bool = False,
) -> RenderedMessage:
    require_components_v2()
    view = discord.ui.LayoutView(timeout=1800)
    children: list[discord.ui.Item] = [
        discord.ui.TextDisplay(f"### {achievement.title}"),
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
        children.append(
            discord.ui.TextDisplay(
                f"-# Achievement Unlocked by {unlocked_by_display_name}"
            )
        )
    view.add_item(discord.ui.Container(*children, accent_color=COLOR_SUCCESS))
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
    page_count = max(1, math.ceil(unlocked_total / _ENTRIES_PER_PAGE)) if unlocked_total else 1
    summary_line = f"Achievements unlocked: **{unlocked_total}/{len(ENABLED_ACHIEVEMENTS)}**"
    if newly_unlocked_count and newly_unlocked_count > 0:
        summary_line = f"{summary_line} *(+{newly_unlocked_count} just unlocked)*"
    subtitle = "Your unlocked achievements" if for_self else f"{display_name}'s unlocked achievements"

    cards: list[RenderedMessage] = []
    for index in range(page_count):
        start = index * _ENTRIES_PER_PAGE
        page_achievements = unlocked_achievements[start : start + _ENTRIES_PER_PAGE]
        view = discord.ui.LayoutView(timeout=1800)
        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay("## Rob Achievements"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(summary_line),
            discord.ui.TextDisplay(subtitle),
            discord.ui.Separator(),
        ]

        if not page_achievements:
            empty_state = "You have not unlocked any achievements yet."
            if not for_self:
                empty_state = f"{display_name} has not unlocked any achievements yet."
            children.extend(
                [
                    discord.ui.TextDisplay(empty_state),
                ]
            )
            if for_self:
                children.append(discord.ui.TextDisplay("Go do something suspiciously Rob-shaped."))
        else:
            for achievement_index, achievement in enumerate(page_achievements):
                rarity_emoji = _RARITY_EMOJIS.get(achievement.rarity, "⚪")
                children.append(
                    discord.ui.TextDisplay(
                        f"**{rarity_emoji} {achievement.title}**\n{achievement.description}"
                    )
                )
                if achievement_index < len(page_achievements) - 1:
                    children.append(discord.ui.Separator())

        children.extend(
            [
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# Page {index + 1}/{page_count}"),
            ]
        )
        view.add_item(discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE))
        cards.append(RenderedMessage(view=view))

    return cards
