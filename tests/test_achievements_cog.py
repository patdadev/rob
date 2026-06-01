from __future__ import annotations

import asyncio
from types import SimpleNamespace

from rob.achievements.definitions import ACHIEVEMENTS, ACHIEVEMENTS_BY_KEY
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


class _FakeGuild:
    def __init__(self, guild_id: int):
        self.id = guild_id

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

    async def send(self, *args, **kwargs):
        if args:
            kwargs["content"] = args[0]
        self.dm_messages.append(kwargs)


class _FakeInteraction:
    def __init__(self, *, user: _FakeMember, guild: _FakeGuild, channel: _FakeChannel):
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
        self.unlock_many_calls: list[dict] = []
        self.unlocked_keys = unlocked_keys or set()
        self.unlock_returns = unlock_returns
        self.enabled = enabled

    async def unlock_achievement(self, *, guild_id: int, discord_user_id: int, achievement_key: str, **kwargs):
        self.unlock_calls.append((achievement_key, discord_user_id))
        if self.unlock_returns:
            callback = kwargs.get("on_unlocked")
            definition = ACHIEVEMENTS_BY_KEY.get(achievement_key)
            if callback and definition is not None:
                await callback(definition)
        return self.unlock_returns

    async def unlock_many(self, **kwargs):
        self.unlock_many_calls.append(kwargs)
        return []

    async def get_user_achievement_keys(self, *, guild_id: int, discord_user_id: int):
        del guild_id, discord_user_id
        return self.unlocked_keys

    async def get_user_achievements(self, *, guild_id: int, discord_user_id: int):
        del guild_id, discord_user_id
        return [ACHIEVEMENTS_BY_KEY[key] for key in ACHIEVEMENTS_BY_KEY if key in self.unlocked_keys]

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
    embeds = payload.get("embeds") or []
    if embeds:
        embed = embeds[0]
        parts = [embed.title or "", embed.description or ""]
        parts.extend(field.name for field in embed.fields)
        parts.extend(field.value for field in embed.fields)
        parts.append(embed.footer.text if embed.footer else "")
        return "\n".join(part for part in parts if part)

    view = payload["view"]
    return "\n".join(
        str(getattr(item, "content", ""))
        for container in view.children
        for item in getattr(container, "children", [])
    )


def _button_labels(payload: dict) -> list[str]:
    view = payload["view"]
    labels: list[str] = []
    for child in view.children:
        for nested in getattr(child, "children", []):
            label = getattr(nested, "label", None)
            if label is not None:
                labels.append(str(label))
    return labels


def _buttons(payload: dict):
    view = payload["view"]
    buttons = []
    for child in view.children:
        buttons.extend(
            nested
            for nested in getattr(child, "children", [])
            if getattr(nested, "label", None) is not None
        )
    return buttons


def test_achievements_command_shows_only_unlocked_entries_publicly():
    bot = _FakeBot(unlocked_keys={"count_10"})
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=None))

    payload = interaction.response.messages[0]
    assert "ephemeral" not in payload
    text = _message_text(payload)
    assert "Your achievements" in text
    assert "Double Digits" in text
    assert "unlocked" in text
    assert "The 67 Incident" not in text
    assert "You said 67." not in text


def test_achievements_command_reports_when_temporarily_disabled():
    bot = _FakeBot(unlocked_keys={"count_10"}, achievements_enabled=False)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=None))

    assert interaction.response.messages == [
        {
            "content": "Hey, this is disabled! We'll bring it back soon.",
            "ephemeral": True,
        }
    ]
    assert bot.achievements_service.unlock_calls == []


def test_achievements_command_announces_new_meta_achievement_in_channel(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.achievements.discord.Member", _FakeMember)
    bot = _FakeBot(unlocked_keys={"count_10"}, unlock_returns=True)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    channel = _FakeChannel()
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=channel)

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=None))

    assert interaction.followup.messages == []
    assert len(channel.messages) == 1
    rendered = _message_text(channel.messages[0])
    assert "Trophy Cabinet" in rendered
    assert "Achievement Unlocked by Pat" in rendered


def test_achievements_command_shows_empty_state_when_none_unlocked():
    bot = _FakeBot(unlocked_keys=set())
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=None))

    text = _message_text(interaction.response.messages[0])
    assert "**0/" in text
    assert "unlocked" in text
    assert "Your achievements" in text
    assert "haven't unlocked any achievements yet" in text
    assert "Double Digits" not in text


def test_achievements_viewing_other_user_unlocks_nosy_achievement():
    bot = _FakeBot()
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    viewer = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    target = _FakeMember(user_id=20, display_name="Alex", role_ids=[], manage_guild=False)
    interaction = _FakeInteraction(user=viewer, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=target))

    assert ("viewed_other_achievements", 10) in bot.achievements_service.unlock_calls


def test_achievements_viewing_other_user_announces_nosy_achievement(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.achievements.discord.Member", _FakeMember)
    bot = _FakeBot(unlocked_keys={"count_10"}, unlock_returns=True)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    viewer = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    target = _FakeMember(user_id=20, display_name="Alex", role_ids=[], manage_guild=False)
    channel = _FakeChannel()
    interaction = _FakeInteraction(user=viewer, guild=_FakeGuild(1), channel=channel)

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=target))

    assert len(channel.messages) == 2
    rendered = "\n".join(_message_text(message) for message in channel.messages)
    assert "Trophy Cabinet" in rendered
    assert "Nosy Little Thing" in rendered


def test_test_achievements_renders_all_configured_cards_for_admin(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.achievements.discord.Member", _FakeMember)
    bot = _FakeBot()
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    channel = _FakeChannel()
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=channel)

    asyncio.run(AchievementsCog.test_achievements.callback(cog, interaction, debug=False))

    assert interaction.response.messages[0]["ephemeral"] is True
    assert len(channel.messages) == len(bot.achievements_service.all_definitions())
    assert bot.achievements_service.unlock_calls == []
    rendered = _message_text(channel.messages[0])
    assert "Key:" not in rendered
    assert "Achievement Unlocked by Preview Mode" in rendered


def test_test_achievements_debug_mode_shows_metadata(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.achievements.discord.Member", _FakeMember)
    bot = _FakeBot()
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    channel = _FakeChannel()
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=channel)

    asyncio.run(AchievementsCog.test_achievements.callback(cog, interaction, debug=True))

    rendered = _message_text(channel.messages[0])
    assert "Key:" in rendered
    assert "Category:" in rendered


def test_achievements_command_adds_pagination_buttons_after_eight_entries():
    many_unlocked_keys = {achievement.key for achievement in ACHIEVEMENTS[:12]}
    bot = _FakeBot(unlocked_keys=many_unlocked_keys)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=None))

    payload = interaction.response.messages[0]
    buttons = _buttons(payload)
    assert _button_labels(payload) == ["◀ Previous", "Next ▶"]
    assert buttons[0].disabled is True
    assert buttons[1].disabled is False


def test_achievements_pagination_rejects_other_users():
    many_unlocked_keys = {achievement.key for achievement in ACHIEVEMENTS[:12]}
    bot = _FakeBot(unlocked_keys=many_unlocked_keys)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    owner = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=owner, guild=_FakeGuild(1), channel=_FakeChannel())
    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=None))

    payload = interaction.response.messages[0]
    next_button = _buttons(payload)[1]

    intruder = _FakeMember(user_id=99, display_name="Intruder", role_ids=[], manage_guild=False)
    intruder_interaction = _FakeInteraction(user=intruder, guild=_FakeGuild(1), channel=_FakeChannel())
    asyncio.run(next_button.callback(intruder_interaction))

    assert intruder_interaction.response.messages
    assert intruder_interaction.response.messages[0]["content"] == "This achievement list belongs to someone else."
    assert intruder_interaction.response.messages[0]["ephemeral"] is True


def test_secret_prefix_command_dms_user_and_deletes_trigger():
    bot = _FakeBot(unlocked_keys=set(), unlock_returns=True)
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    ctx = _FakeContext(author=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.secret_prefix.callback(cog, ctx))

    assert ctx.deleted is True
    assert member.dm_messages
    assert "Shhhh..." in _message_text(member.dm_messages[0])
    assert ctx.replies == []


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
