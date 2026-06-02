from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from discord import app_commands

from rob.achievements.definitions import ACHIEVEMENTS_BY_KEY, ENABLED_ACHIEVEMENTS
from rob.achievements.service import (
    AchievementServerRecentUnlock,
    AchievementServerStats,
    AchievementServerUserStanding,
    AchievementUnlockState,
)
from rob.discord.cogs.achievements import AchievementsCog


class _FakeResponse:
    def __init__(self):
        self.messages: list[dict] = []
        self.edits: list[dict] = []
        self.deferred = False

    async def send_message(self, *args, **kwargs):
        if args:
            kwargs["content"] = args[0]
        self.messages.append(kwargs)

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)

    async def defer(self):
        self.deferred = True


class _FakeFollowup:
    def __init__(self):
        self.messages: list[dict] = []

    async def send(self, **kwargs):
        self.messages.append(kwargs)


class _FakeChannel:
    def __init__(self):
        self.messages: list[dict] = []

    async def send(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(id=len(self.messages))


class _FakeAvatar:
    def __init__(self, url: str):
        self.url = url


class _FakeGuild:
    def __init__(self, guild_id: int, *, name: str = "VIB", member_count: int = 12):
        self.id = guild_id
        self.name = name
        self.member_count = member_count
        self.icon = _FakeAvatar("https://example.com/server.png")

    def get_member(self, user_id: int):
        return _FakeMember(user_id=user_id, display_name=f"user-{user_id}", role_ids=[], manage_guild=True)


class _FakeMember:
    def __init__(self, *, user_id: int, display_name: str, role_ids: list[int], manage_guild: bool = False):
        self.id = user_id
        self.display_name = display_name
        self.name = display_name
        self.roles = [SimpleNamespace(id=role_id) for role_id in role_ids]
        self.guild_permissions = SimpleNamespace(manage_guild=manage_guild)
        self.dm_messages: list[dict] = []
        self.display_avatar = _FakeAvatar(f"https://example.com/{user_id}.png")

    async def send(self, *args, **kwargs):
        if args:
            kwargs["content"] = args[0]
        self.dm_messages.append(kwargs)


class _FakeInteraction:
    def __init__(self, *, user: _FakeMember, guild: _FakeGuild | None, channel: _FakeChannel):
        self.user = user
        self.guild = guild
        self.channel = channel
        self.response = _FakeResponse()
        self.followup = _FakeFollowup()


class _FakeContext:
    def __init__(self, *, author: _FakeMember, guild: _FakeGuild | None, channel: _FakeChannel):
        self.author = author
        self.guild = guild
        self.channel = channel
        self.message = SimpleNamespace(delete=self._delete)
        self.replies: list[dict] = []
        self.deleted = False

    async def _delete(self):
        self.deleted = True

    async def reply(self, *args, **kwargs):
        if args:
            kwargs["content"] = args[0]
        self.replies.append(kwargs)


class _FakeAchievementsService:
    def __init__(
        self,
        *,
        unlocked_keys: set[str] | None = None,
        unlock_returns: bool = False,
        enabled: bool = True,
    ):
        self.unlock_calls: list[tuple[str, int]] = []
        self.unlocked_keys = unlocked_keys or set()
        self.unlock_returns = unlock_returns
        self.enabled = enabled
        self.server_stats_calls: list[int] = []

    async def unlock_achievement(self, *, guild_id: int, discord_user_id: int, achievement_key: str, **kwargs):
        self.unlock_calls.append((achievement_key, discord_user_id))
        if self.unlock_returns:
            callback = kwargs.get("on_unlocked")
            definition = ACHIEVEMENTS_BY_KEY.get(achievement_key)
            if callback and definition is not None:
                await callback(definition)
        return self.unlock_returns

    async def get_user_achievement_states(self, *, guild_id: int, discord_user_id: int):
        del guild_id, discord_user_id
        return [
            AchievementUnlockState(
                definition=definition,
                unlocked_at=datetime(2026, 1, 2) if definition.key in self.unlocked_keys else None,
            )
            for definition in ENABLED_ACHIEVEMENTS
        ]

    async def get_server_stats(self, *, guild_id: int):
        self.server_stats_calls.append(guild_id)
        return AchievementServerStats(
            members_with_unlocks=2,
            unlock_counts={"count_10": 2, "secret_command": 1},
            recent_unlocks=[
                AchievementServerRecentUnlock(
                    discord_user_id=10,
                    definition=ACHIEVEMENTS_BY_KEY["count_10"],
                    unlocked_at=datetime(2026, 1, 2),
                )
            ],
            top_users=[AchievementServerUserStanding(discord_user_id=10, unlocked_count=2)],
        )

    def get_definition(self, key: str):
        return ACHIEVEMENTS_BY_KEY.get(key)

    def all_definitions(self):
        return (
            ACHIEVEMENTS_BY_KEY["count_10"],
            ACHIEVEMENTS_BY_KEY["secret_command"],
        )


class _FakeBot:
    def __init__(
        self,
        *,
        unlocked_keys: set[str] | None = None,
        unlock_returns: bool = False,
        achievements_enabled: bool = True,
    ):
        self.achievements_service = _FakeAchievementsService(
            unlocked_keys=unlocked_keys,
            unlock_returns=unlock_returns,
            enabled=achievements_enabled,
        )
        self.settings = SimpleNamespace(inactivity_owner_user_id=999)
        self.maintenance_service = SimpleNamespace(notifications_suppressed=self._notifications_suppressed)
        self.guild_settings_repo = SimpleNamespace(
            get=self._get_settings,
            list_guild_ids=self._list_guild_ids,
        )
        self._maintenance_notifications = False

    async def _get_settings(self, _guild_id: int):
        return SimpleNamespace(mod_role_id=42)

    async def _list_guild_ids(self):
        return [1]

    async def _notifications_suppressed(self):
        return self._maintenance_notifications


def _message_text(payload: dict) -> str:
    view = payload["view"]

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


def _button_labels(payload: dict) -> list[str]:
    labels: list[str] = []
    view = payload["view"]
    for child in view.children:
        for nested in getattr(child, "children", []):
            label = getattr(nested, "label", None)
            if label is not None:
                labels.append(str(label))
    return labels


def test_achievements_command_defaults_to_me_and_is_ephemeral():
    bot = _FakeBot(unlocked_keys={"count_10"})
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, scope=None, user=None))

    payload = interaction.response.messages[0]
    assert payload["ephemeral"] is True
    assert "Your achievement cabinet" in _message_text(payload)
    assert "Share publicly" in _button_labels(payload)
    assert ("first_achievement_view", 10) in bot.achievements_service.unlock_calls


def test_achievements_command_viewing_other_user_unlocks_nosy_achievement():
    bot = _FakeBot(unlocked_keys={"count_10"})
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    viewer = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    target = _FakeMember(user_id=20, display_name="Alex", role_ids=[], manage_guild=False)
    interaction = _FakeInteraction(user=viewer, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, scope=None, user=target))

    payload = interaction.response.messages[0]
    assert payload["ephemeral"] is True
    assert "Viewing Alex in this server" in _message_text(payload)
    assert ("viewed_other_achievements", 10) in bot.achievements_service.unlock_calls


def test_achievements_command_server_scope_uses_current_guild_and_is_public():
    bot = _FakeBot()
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    viewer = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=viewer, guild=_FakeGuild(99), channel=_FakeChannel())

    asyncio.run(
        AchievementsCog.achievements.callback(
            cog,
            interaction,
            scope=app_commands.Choice(name="Server", value="server"),
            user=None,
        )
    )

    payload = interaction.response.messages[0]
    assert "ephemeral" not in payload
    assert "VIB achievements" in _message_text(payload)
    assert bot.achievements_service.server_stats_calls == [99]


def test_achievements_command_rejects_server_scope_in_dm():
    bot = _FakeBot()
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    viewer = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=viewer, guild=None, channel=_FakeChannel())

    asyncio.run(
        AchievementsCog.achievements.callback(
            cog,
            interaction,
            scope=app_commands.Choice(name="Server", value="server"),
            user=None,
        )
    )

    payload = interaction.response.messages[0]
    assert payload["ephemeral"] is True
    assert "Use `/achievements` in the server." in _message_text(payload)


def test_achievements_command_announces_meta_achievement_with_v2_payload(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.achievements.discord.Member", _FakeMember)
    bot = _FakeBot(unlocked_keys={"count_10"}, unlock_returns=True)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    channel = _FakeChannel()
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=channel)

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, scope=None, user=None))

    assert channel.messages
    assert "content" not in channel.messages[0]
    assert "Trophy Cabinet" in _message_text(channel.messages[0])


def test_secret_prefix_command_dms_user_and_deletes_trigger():
    bot = _FakeBot(unlock_returns=True)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    ctx = _FakeContext(author=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.secret_prefix.callback(cog, ctx))

    assert ctx.deleted is True
    assert member.dm_messages
    assert "Shhhh..." in _message_text(member.dm_messages[0])


def test_secret_prefix_reports_when_achievements_are_disabled():
    bot = _FakeBot(unlocked_keys=set(), unlock_returns=False, achievements_enabled=False)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    ctx = _FakeContext(author=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.secret_prefix.callback(cog, ctx))

    assert ctx.deleted is True
    assert member.dm_messages
    assert member.dm_messages[0]["content"] == "Achievements are switched off right now, but your existing ones are still there."


def test_secret_slash_command_has_been_removed():
    command_names = [command.name for command in AchievementsCog.__cog_app_commands__]
    assert "secret" not in command_names
