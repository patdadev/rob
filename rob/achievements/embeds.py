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
                f"-# Achievements Unlock by {unlocked_by_display_name}"
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
    unlocked_total = len(unlocked_achievements)
    page_count = max(1, math.ceil(unlocked_total / _ENTRIES_PER_PAGE)) if unlocked_total else 1
    summary_line = f"Achievements unlocked: {unlocked_total}/{len(ENABLED_ACHIEVEMENTS)}"
    if newly_unlocked_count and newly_unlocked_count > 0:
        summary_line = f"{summary_line} +{newly_unlocked_count}"

    cards: list[RenderedMessage] = []
    for index in range(page_count):
        start = index * _ENTRIES_PER_PAGE
        page_achievements = unlocked_achievements[start : start + _ENTRIES_PER_PAGE]

        embed = discord.Embed(
            title="Rob Achievements",
            description=summary_line,
            colour=COLOR_ROB_PURPLE,
        )
        embed.set_author(name=f"{display_name}'s achievements" if not for_self else f"{display_name}'s achievements")
        embed.set_footer(text=f"Page {index + 1}/{page_count}")

        if not page_achievements:
            empty_state = "You have not unlocked any achievements yet."
            if not for_self:
                empty_state = f"{display_name} has not unlocked any achievements yet."
            embed.add_field(
                name="Nothing here yet",
                value=f"{empty_state}\nGo do something suspiciously Rob-shaped.",
                inline=False,
            )
            cards.append(RenderedMessage(embeds=[embed], view=discord.ui.View(timeout=1800), mode="embed"))
            continue

        for achievement in page_achievements:
            embed.add_field(name=achievement.title, value=achievement.description, inline=True)

        cards.append(RenderedMessage(embeds=[embed], view=discord.ui.View(timeout=1800), mode="embed"))

    return cards
