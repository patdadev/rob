from __future__ import annotations

import discord

from rob.achievements.definitions import ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY, AchievementDefinition
from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_ROB_PURPLE

_HELPER_LINE = "-# Cat Bot has achievements, why not Rob?"


def achievement_unlocked_card(
    achievement: AchievementDefinition,
    *,
    include_meta_line: bool = False,
) -> RenderedMessage:
    require_components_v2()
    view = discord.ui.LayoutView(timeout=1800)
    children: list[discord.ui.Item] = [
        discord.ui.TextDisplay(f"### {achievement.title}"),
        discord.ui.Separator(),
        discord.ui.TextDisplay(achievement.description),
        discord.ui.Separator(),
    ]
    if include_meta_line:
        children.append(
            discord.ui.TextDisplay(
                f"-# Key: {achievement.key} | Category: {achievement.category} | Rarity: {achievement.rarity}"
            )
        )
        children.append(discord.ui.Separator())
    children.append(discord.ui.TextDisplay(_HELPER_LINE))
    view.add_item(discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE))
    return RenderedMessage(view=view)


def achievements_overview_cards(
    *,
    display_name: str,
    unlocked_keys: set[str],
    for_self: bool,
) -> list[RenderedMessage]:
    require_components_v2()
    known_unlocked = {key for key in unlocked_keys if key in ACHIEVEMENTS_BY_KEY}

    rows: list[str] = []
    for achievement in ACHIEVEMENTS:
        if achievement.key in known_unlocked:
            rows.append(f"- {achievement.title}")
        elif achievement.hidden:
            rows.append("- || Secret Achievement ||")

    if not rows:
        rows = ["- No achievements unlocked yet."]

    chunks: list[list[str]] = []
    chunk_size = 35
    for start in range(0, len(rows), chunk_size):
        chunks.append(rows[start : start + chunk_size])

    cards: list[RenderedMessage] = []
    for index, chunk in enumerate(chunks):
        view = discord.ui.LayoutView(timeout=1800)
        if index == 0:
            title = "## Your Achievements" if for_self else f"## {display_name}'s Achievements"
            stats_line = f"-# Achievements Collected: **{len(known_unlocked)}/{len(ACHIEVEMENTS)}**"
            entries = "\n".join(chunk)
            body = f"{stats_line}\n\n**Achievements So Far:**\n\n{entries}"
            children: list[discord.ui.Item] = [
                discord.ui.TextDisplay(title),
                discord.ui.Separator(),
                discord.ui.TextDisplay(body),
                discord.ui.Separator(),
                discord.ui.TextDisplay(_HELPER_LINE),
            ]
        else:
            children = [
                discord.ui.TextDisplay("## Achievements (continued)"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("\n".join(chunk)),
            ]
        view.add_item(discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE))
        cards.append(RenderedMessage(view=view))

    return cards
