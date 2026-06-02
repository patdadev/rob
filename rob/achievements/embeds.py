from __future__ import annotations

import math
from datetime import datetime

import discord

from rob.achievements.definitions import (
    CATEGORY_ICON,
    ENABLED_ACHIEVEMENTS,
    RARITY_ORDER,
    AchievementCategory,
    AchievementDefinition,
    achievements_by_category,
)
from rob.achievements.service import AchievementServerStats, AchievementUnlockState
from rob.ui.render import RenderedMessage, require_components_v2
from rob.ui.theme import COLOR_ROB_PURPLE, COLOR_SUCCESS, ROB_GOLD

_ENTRIES_PER_PAGE = 6
_ALL_CATEGORIES = "__all__"
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

_STATE_FILTER_LABELS: dict[str, str] = {
    "all": "All",
    "unlocked": "Unlocked",
    "locked": "Locked",
}


def _progress_bar(unlocked: int, total: int, *, width: int = 10) -> str:
    """Render a text-based progress bar."""
    if total == 0:
        return "░" * width
    filled = round((unlocked / total) * width)
    filled = min(filled, width)
    return "▓" * filled + "░" * (width - filled)


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "Locked"
    return value.strftime("%Y-%m-%d")


def _completion_text(unlocked: int, total: int) -> str:
    percent = 0 if total == 0 else round((unlocked / total) * 100)
    return f"{_progress_bar(unlocked, total, width=12)}  **{unlocked}/{total}** · {percent}%"


def _achievement_title(state: AchievementUnlockState) -> str:
    if not state.unlocked and state.definition.hidden:
        return "???"
    return state.definition.title


def _achievement_description(state: AchievementUnlockState) -> str:
    if not state.unlocked and state.definition.hidden:
        return "Hidden achievement — unlock it to reveal the details."
    return state.definition.description


def _achievement_detail_lines(state: AchievementUnlockState) -> str:
    rarity_emoji = _RARITY_EMOJIS.get(state.definition.rarity, "⚪")
    status = (
        f"Unlocked {_format_timestamp(state.unlocked_at)}"
        if state.unlocked
        else "Locked"
    )
    return (
        f"{state.definition.display_icon} **{_achievement_title(state)}**\n"
        f"-# {_achievement_description(state)}\n"
        f"-# {rarity_emoji} {state.definition.rarity_label} · {status}"
    )


def _target_thumbnail(icon_url: str | None) -> discord.ui.Thumbnail | None:
    if not icon_url:
        return None
    return discord.ui.Thumbnail(media=icon_url)


def _summary_section(text: str, *, icon_url: str | None) -> discord.ui.Item:
    thumbnail = _target_thumbnail(icon_url)
    if thumbnail is None:
        return discord.ui.TextDisplay(text)
    return discord.ui.Section(discord.ui.TextDisplay(text), accessory=thumbnail)


class _AchievementStateSelect(discord.ui.Select):
    def __init__(self, view: "_AchievementCatalogueView") -> None:
        options = [
            discord.SelectOption(
                label=label,
                value=value,
                default=view.state_filter == value,
            )
            for value, label in _STATE_FILTER_LABELS.items()
        ]
        super().__init__(placeholder="Show locked, unlocked, or all", options=options)
        self.catalogue_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.catalogue_view.set_state_filter(interaction, self.values[0])


class _AchievementCategorySelect(discord.ui.Select):
    def __init__(self, view: "_AchievementCatalogueView") -> None:
        options = [
            discord.SelectOption(
                label="All categories",
                value=_ALL_CATEGORIES,
                default=view.category_filter == _ALL_CATEGORIES,
            )
        ]
        for category, states in view.category_groups.items():
            unlocked = sum(1 for state in states if state.unlocked)
            options.append(
                discord.SelectOption(
                    label=f"{CATEGORY_ICON.get(category, '🏆')} {states[0].definition.category_label}",
                    value=category,
                    description=f"{unlocked}/{len(states)} unlocked",
                    default=view.category_filter == category,
                )
            )
        super().__init__(placeholder="Filter by category", options=options)
        self.catalogue_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.catalogue_view.set_category_filter(interaction, self.values[0])


class _AchievementPageButton(discord.ui.Button):
    def __init__(self, view: "_AchievementCatalogueView", *, direction: int) -> None:
        label = "◀ Previous" if direction < 0 else "Next ▶"
        disabled = direction < 0 and view.page_index <= 0
        if direction > 0 and view.page_index >= view.page_count - 1:
            disabled = True
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=disabled)
        self.catalogue_view = view
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.catalogue_view.turn_page(interaction, self.direction)


class _SharePubliclyButton(discord.ui.Button):
    def __init__(self, view: "_AchievementCatalogueView") -> None:
        super().__init__(label="Share publicly", style=discord.ButtonStyle.primary)
        self.catalogue_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.catalogue_view.share_publicly(interaction)


class _AchievementCatalogueView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        owner_user_id: int,
        title: str,
        subtitle: str,
        icon_url: str | None,
        states: list[AchievementUnlockState],
        empty_callout: str,
        allow_public_share: bool,
    ) -> None:
        super().__init__(timeout=1800)
        self.owner_user_id = owner_user_id
        self.title = title
        self.subtitle = subtitle
        self.icon_url = icon_url
        self.states = states
        self.empty_callout = empty_callout
        self.allow_public_share = allow_public_share
        self.category_groups: dict[AchievementCategory, list[AchievementUnlockState]] = {}
        for state in states:
            self.category_groups.setdefault(state.definition.category, []).append(state)
        self.category_filter = _ALL_CATEGORIES
        self.state_filter = "all"
        self.page_index = 0
        self._rebuild()

    @property
    def unlocked_total(self) -> int:
        return sum(1 for state in self.states if state.unlocked)

    @property
    def page_count(self) -> int:
        return max(1, math.ceil(len(self._filtered_states()) / _ENTRIES_PER_PAGE))

    def _filtered_states(self) -> list[AchievementUnlockState]:
        states = self.states
        if self.category_filter != _ALL_CATEGORIES:
            states = [state for state in states if state.definition.category == self.category_filter]
        if self.state_filter == "unlocked":
            states = [state for state in states if state.unlocked]
        elif self.state_filter == "locked":
            states = [state for state in states if not state.unlocked]
        return states

    def _page_states(self) -> list[AchievementUnlockState]:
        filtered = self._filtered_states()
        start = self.page_index * _ENTRIES_PER_PAGE
        return filtered[start : start + _ENTRIES_PER_PAGE]

    def _category_summary(self, category: AchievementCategory) -> str:
        category_states = [state for state in self.states if state.definition.category == category]
        unlocked = sum(1 for state in category_states if state.unlocked)
        total = len(category_states)
        return f"{CATEGORY_ICON.get(category, '🏆')} {category_states[0].definition.category_label} · {unlocked}/{total}"

    def _header_container(self) -> discord.ui.Container:
        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## 🏆 {self.title}"),
            discord.ui.Separator(),
            _summary_section(
                f"**{self.subtitle}**\n-# {_completion_text(self.unlocked_total, len(self.states))}",
                icon_url=self.icon_url,
            ),
        ]
        return discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE)

    def _entries_container(self) -> discord.ui.Container:
        page_states = self._page_states()
        children: list[discord.ui.Item] = []
        if not page_states:
            children.extend(
                [
                    discord.ui.TextDisplay("### Nothing matches this filter yet"),
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(self.empty_callout),
                ]
            )
        else:
            grouped: dict[AchievementCategory, list[AchievementUnlockState]] = {}
            for state in page_states:
                grouped.setdefault(state.definition.category, []).append(state)
            for category_index, (category, grouped_states) in enumerate(grouped.items()):
                if category_index > 0:
                    children.append(discord.ui.Separator())
                children.append(discord.ui.TextDisplay(f"### {self._category_summary(category)}"))
                for state in grouped_states:
                    children.append(
                        discord.ui.Section(
                            discord.ui.TextDisplay(_achievement_detail_lines(state)),
                            accessory=discord.ui.Button(
                                label="Unlocked" if state.unlocked else "Locked",
                                style=discord.ButtonStyle.success if state.unlocked else discord.ButtonStyle.secondary,
                                disabled=True,
                            ),
                        )
                    )
        children.extend(
            [
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"-# Page {self.page_index + 1} of {self.page_count} · {_STATE_FILTER_LABELS[self.state_filter]}"
                ),
            ]
        )
        return discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE)

    def _rebuild(self) -> None:
        self.clear_items()
        self.page_index = max(0, min(self.page_index, self.page_count - 1))
        self.add_item(self._header_container())
        self.add_item(self._entries_container())
        self.add_item(discord.ui.ActionRow(_AchievementCategorySelect(self)))
        self.add_item(discord.ui.ActionRow(_AchievementStateSelect(self)))
        controls: list[discord.ui.Item] = [
            _AchievementPageButton(self, direction=-1),
            _AchievementPageButton(self, direction=1),
        ]
        if self.allow_public_share:
            controls.append(_SharePubliclyButton(self))
        self.add_item(discord.ui.ActionRow(*controls))

    async def _ensure_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user is None or interaction.user.id != self.owner_user_id:
            await interaction.response.send_message(
                "This achievement view belongs to someone else.",
                ephemeral=True,
            )
            return False
        return True

    def render_message(self) -> RenderedMessage:
        return RenderedMessage(view=self)

    def clone_message(self, *, allow_public_share: bool | None = None) -> RenderedMessage:
        cloned = _AchievementCatalogueView(
            owner_user_id=self.owner_user_id,
            title=self.title,
            subtitle=self.subtitle,
            icon_url=self.icon_url,
            states=self.states,
            empty_callout=self.empty_callout,
            allow_public_share=self.allow_public_share if allow_public_share is None else allow_public_share,
        )
        cloned.category_filter = self.category_filter
        cloned.state_filter = self.state_filter
        cloned.page_index = self.page_index
        cloned._rebuild()
        return RenderedMessage(view=cloned)

    async def set_state_filter(self, interaction: discord.Interaction, value: str) -> None:
        if not await self._ensure_owner(interaction):
            return
        self.state_filter = value
        self.page_index = 0
        self._rebuild()
        await interaction.response.edit_message(**self.render_message().edit_kwargs())

    async def set_category_filter(self, interaction: discord.Interaction, value: str) -> None:
        if not await self._ensure_owner(interaction):
            return
        self.category_filter = value
        self.page_index = 0
        self._rebuild()
        await interaction.response.edit_message(**self.render_message().edit_kwargs())

    async def turn_page(self, interaction: discord.Interaction, direction: int) -> None:
        if not await self._ensure_owner(interaction):
            return
        next_index = max(0, min(self.page_count - 1, self.page_index + direction))
        if next_index == self.page_index:
            await interaction.response.defer()
            return
        self.page_index = next_index
        self._rebuild()
        await interaction.response.edit_message(**self.render_message().edit_kwargs())

    async def share_publicly(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_owner(interaction):
            return
        if interaction.channel is None:
            await interaction.response.send_message(
                "Rob couldn't find a channel to share this in.",
                ephemeral=True,
            )
            return
        await interaction.channel.send(**self.clone_message(allow_public_share=False).send_kwargs())
        await interaction.response.send_message("Shared publicly.", ephemeral=True)


class _AchievementServerCategorySelect(discord.ui.Select):
    def __init__(self, view: "_AchievementServerView") -> None:
        options = [
            discord.SelectOption(
                label="All categories",
                value=_ALL_CATEGORIES,
                default=view.category_filter == _ALL_CATEGORIES,
            )
        ]
        for category in view.available_categories:
            definition = view.first_definition_for(category)
            options.append(
                discord.SelectOption(
                    label=f"{CATEGORY_ICON.get(category, '🏆')} {definition.category_label}",
                    value=category,
                    default=view.category_filter == category,
                )
            )
        super().__init__(placeholder="Filter server stats by category", options=options)
        self.server_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.server_view.category_filter = self.values[0]
        self.server_view.page_index = 0
        self.server_view.rebuild()
        await interaction.response.edit_message(**self.server_view.render_message().edit_kwargs())


class _AchievementServerPageButton(discord.ui.Button):
    def __init__(self, view: "_AchievementServerView", *, direction: int) -> None:
        label = "◀ Previous" if direction < 0 else "Next ▶"
        disabled = direction < 0 and view.page_index <= 0
        if direction > 0 and view.page_index >= view.page_count - 1:
            disabled = True
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=disabled)
        self.server_view = view
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        next_index = max(0, min(self.server_view.page_count - 1, self.server_view.page_index + self.direction))
        if next_index == self.server_view.page_index:
            await interaction.response.defer()
            return
        self.server_view.page_index = next_index
        self.server_view.rebuild()
        await interaction.response.edit_message(**self.server_view.render_message().edit_kwargs())


class _AchievementServerView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        owner_user_id: int,
        server_name: str,
        server_icon_url: str | None,
        member_count: int,
        stats: AchievementServerStats,
    ) -> None:
        super().__init__(timeout=1800)
        self.owner_user_id = owner_user_id
        self.server_name = server_name
        self.server_icon_url = server_icon_url
        self.member_count = member_count
        self.stats = stats
        self.category_filter = _ALL_CATEGORIES
        self.page_index = 0
        self.available_categories = tuple(
            category for category in achievements_by_category(ENABLED_ACHIEVEMENTS).keys()
        )
        self.rebuild()

    def first_definition_for(self, category: AchievementCategory) -> AchievementDefinition:
        return next(definition for definition in ENABLED_ACHIEVEMENTS if definition.category == category)

    def _filtered_definitions(self) -> list[AchievementDefinition]:
        definitions = [definition for definition in ENABLED_ACHIEVEMENTS if self.stats.unlock_counts.get(definition.key, 0) > 0]
        if self.category_filter != _ALL_CATEGORIES:
            definitions = [definition for definition in definitions if definition.category == self.category_filter]
        return sorted(
            definitions,
            key=lambda definition: (
                self.stats.unlock_counts.get(definition.key, 0),
                RARITY_ORDER.get(definition.rarity, 0),
                definition.title,
            ),
        )

    @property
    def page_count(self) -> int:
        return max(1, math.ceil(len(self._filtered_definitions()) / _ENTRIES_PER_PAGE))

    def _header_container(self) -> discord.ui.Container:
        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## 🏆 {self.server_name} achievements"),
            discord.ui.Separator(),
            _summary_section(
                f"**Server overview**\n"
                f"-# {_completion_text(len(self.stats.unlock_counts), len(ENABLED_ACHIEVEMENTS))}",
                icon_url=self.server_icon_url,
            ),
        ]
        return discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE)

    def _most_unlocked(self) -> tuple[AchievementDefinition, int] | None:
        if not self.stats.unlock_counts:
            return None
        key, count = max(self.stats.unlock_counts.items(), key=lambda item: (item[1], item[0]))
        definition = next((achievement for achievement in ENABLED_ACHIEVEMENTS if achievement.key == key), None)
        if definition is None:
            return None
        return definition, count

    def _rarest_unlocked(self) -> tuple[AchievementDefinition, int] | None:
        if not self.stats.unlock_counts:
            return None
        key, count = min(self.stats.unlock_counts.items(), key=lambda item: (item[1], item[0]))
        definition = next((achievement for achievement in ENABLED_ACHIEVEMENTS if achievement.key == key), None)
        if definition is None:
            return None
        return definition, count

    def _summary_container(self) -> discord.ui.Container:
        rarest = self._rarest_unlocked()
        most_unlocked = self._most_unlocked()
        recent_lines = (
            "\n".join(
                f"• <@{unlock.discord_user_id}> — {unlock.definition.title} · {_format_timestamp(unlock.unlocked_at)}"
                for unlock in self.stats.recent_unlocks
            )
            if self.stats.recent_unlocks
            else "No recent unlocks yet."
        )
        leaderboard_lines = (
            "\n".join(
                f"• <@{standing.discord_user_id}> — {standing.unlocked_count}"
                for standing in self.stats.top_users
            )
            if self.stats.top_users
            else "No leaderboard yet."
        )
        denominator = max(1, self.member_count or self.stats.members_with_unlocks or 1)
        rarest_text = "Nothing unlocked yet."
        if rarest is not None:
            rarest_text = f"{rarest[0].title} · {rarest[1]}/{denominator}"
        most_unlocked_text = "Nothing unlocked yet."
        if most_unlocked is not None:
            most_unlocked_text = f"{most_unlocked[0].title} · {most_unlocked[1]} unlocks"
        return discord.ui.Container(
            discord.ui.TextDisplay(
                f"### Server snapshot\n"
                f"-# Members with unlocks: **{self.stats.members_with_unlocks}**\n"
                f"-# Rarest unlocked: **{rarest_text}**\n"
                f"-# Most unlocked: **{most_unlocked_text}**"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**Just unlocked**\n{recent_lines}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**Leaderboard**\n{leaderboard_lines}"),
            accent_color=COLOR_ROB_PURPLE,
        )

    def _breakdown_container(self) -> discord.ui.Container:
        definitions = self._filtered_definitions()
        start = self.page_index * _ENTRIES_PER_PAGE
        page_definitions = definitions[start : start + _ENTRIES_PER_PAGE]
        children: list[discord.ui.Item] = []
        if not page_definitions:
            children.extend(
                [
                    discord.ui.TextDisplay("### No unlocked achievements yet"),
                    discord.ui.Separator(),
                    discord.ui.TextDisplay("Once someone unlocks an achievement, its server stats will show up here."),
                ]
            )
        else:
            denominator = max(1, self.member_count or self.stats.members_with_unlocks or 1)
            for definition in page_definitions:
                unlock_count = self.stats.unlock_counts.get(definition.key, 0)
                percent = round((unlock_count / denominator) * 100)
                children.append(
                    discord.ui.Section(
                        discord.ui.TextDisplay(
                            f"{definition.display_icon} **{definition.title}**\n"
                            f"-# {definition.description}\n"
                            f"-# {unlock_count} unlocked · {percent}% of members"
                        ),
                        accessory=discord.ui.Button(
                            label=definition.rarity_label,
                            style=discord.ButtonStyle.secondary,
                            disabled=True,
                        ),
                    )
                )
        children.extend(
            [
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# Page {self.page_index + 1} of {self.page_count}"),
            ]
        )
        return discord.ui.Container(*children, accent_color=COLOR_ROB_PURPLE)

    def rebuild(self) -> None:
        self.clear_items()
        self.page_index = max(0, min(self.page_index, self.page_count - 1))
        self.add_item(self._header_container())
        self.add_item(self._summary_container())
        self.add_item(self._breakdown_container())
        self.add_item(discord.ui.ActionRow(_AchievementServerCategorySelect(self)))
        self.add_item(
            discord.ui.ActionRow(
                _AchievementServerPageButton(self, direction=-1),
                _AchievementServerPageButton(self, direction=1),
            )
        )

    def render_message(self) -> RenderedMessage:
        return RenderedMessage(view=self)


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
        discord.ui.TextDisplay(f"-# {rarity_emoji} {achievement.rarity_label}"),
    ]
    if include_meta_line:
        children.append(
            discord.ui.TextDisplay(
                f"-# Key: {achievement.key} | Category: {achievement.category} | Rarity: {achievement.rarity}"
            )
        )
    if unlocked_by_display_name:
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# Achievement Unlocked by {unlocked_by_display_name}"))
    if unlocked_by_user_id is not None:
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"<@{unlocked_by_user_id}>"))
    view.add_item(discord.ui.Container(*children, accent_color=accent))
    return RenderedMessage(view=view)


def render_user_achievements_message(
    *,
    owner_user_id: int,
    title: str,
    subtitle: str,
    icon_url: str | None,
    states: list[AchievementUnlockState],
    allow_public_share: bool,
    empty_callout: str,
) -> RenderedMessage:
    require_components_v2()
    view = _AchievementCatalogueView(
        owner_user_id=owner_user_id,
        title=title,
        subtitle=subtitle,
        icon_url=icon_url,
        states=states,
        empty_callout=empty_callout,
        allow_public_share=allow_public_share,
    )
    return view.render_message()


def render_server_achievements_message(
    *,
    owner_user_id: int,
    server_name: str,
    server_icon_url: str | None,
    member_count: int,
    stats: AchievementServerStats,
) -> RenderedMessage:
    require_components_v2()
    view = _AchievementServerView(
        owner_user_id=owner_user_id,
        server_name=server_name,
        server_icon_url=server_icon_url,
        member_count=member_count,
        stats=stats,
    )
    return view.render_message()


def achievements_overview_cards(
    *,
    display_name: str,
    unlocked_achievements: list[AchievementDefinition],
    for_self: bool,
    newly_unlocked_count: int | None = None,
) -> list[RenderedMessage]:
    unlocked_by_key = {achievement.key for achievement in unlocked_achievements}
    subtitle = "Your achievement cabinet" if for_self else f"{display_name}'s achievement cabinet"
    if newly_unlocked_count:
        subtitle = f"{subtitle} · +{newly_unlocked_count} new"
    states = [
        AchievementUnlockState(definition=definition, unlocked_at=datetime(2026, 1, 1))
        if definition.key in unlocked_by_key
        else AchievementUnlockState(definition=definition)
        for definition in ENABLED_ACHIEVEMENTS
    ]
    empty_callout = (
        "You haven't unlocked anything yet. Go do something suspiciously Rob-shaped."
        if for_self
        else f"{display_name} hasn't unlocked any achievements yet."
    )
    return [
        render_user_achievements_message(
            owner_user_id=0,
            title=display_name,
            subtitle=subtitle,
            icon_url=None,
            states=states,
            allow_public_share=False,
            empty_callout=empty_callout,
        )
    ]
