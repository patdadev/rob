from __future__ import annotations

import asyncio
from types import SimpleNamespace

from rob.achievements.definitions import ACHIEVEMENTS_BY_KEY
from rob.discord.cogs.achievements import AchievementsCog


class _FakeResponse:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_message(self, *args, **kwargs):
        if args:
            kwargs["content"] = args[0]
        self.messages.append(kwargs)


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
        self.roles = [SimpleNamespace(id=role_id) for role_id in role_ids]
        self.guild_permissions = SimpleNamespace(manage_guild=manage_guild)


class _FakeInteraction:
    def __init__(self, *, user: _FakeMember, guild: _FakeGuild, channel: _FakeChannel):
        self.user = user
        self.guild = guild
        self.channel = channel
        self.response = _FakeResponse()
        self.followup = _FakeFollowup()


class _FakeAchievementsService:
    def __init__(self):
        self.unlock_calls: list[tuple[str, int]] = []
        self.unlock_many_calls: list[dict] = []

    async def unlock_achievement(self, *, guild_id: int, discord_user_id: int, achievement_key: str, **_kwargs):
        self.unlock_calls.append((achievement_key, discord_user_id))
        return True

    async def unlock_many(self, **kwargs):
        self.unlock_many_calls.append(kwargs)
        return []

    async def get_user_achievement_keys(self, *, guild_id: int, discord_user_id: int):
        del guild_id, discord_user_id
        return {"count_10"}

    def all_definitions(self):
        return (
            ACHIEVEMENTS_BY_KEY["count_10"],
            ACHIEVEMENTS_BY_KEY["secret_command"],
        )


class _FakeBot:
    def __init__(self):
        self.achievements_service = _FakeAchievementsService()
        self.settings = SimpleNamespace(inactivity_owner_user_id=999)
        self.guild_settings_repo = SimpleNamespace(
            get=self._get_settings,
            list_guild_ids=self._list_guild_ids,
        )

    async def _get_settings(self, _guild_id: int):
        return SimpleNamespace(mod_role_id=42)

    async def _list_guild_ids(self):
        return [1]


def _message_text(payload: dict) -> str:
    view = payload["view"]
    return "\n".join(
        str(getattr(item, "content", ""))
        for container in view.children
        for item in getattr(container, "children", [])
    )


def test_achievements_command_shows_secret_placeholder_when_locked():
    bot = _FakeBot()
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=None))

    payload = interaction.response.messages[0]
    assert payload["ephemeral"] is False
    text = _message_text(payload)
    assert "Your Achievements" in text
    assert "|| Secret Achievement ||" in text


def test_achievements_viewing_other_user_unlocks_nosy_achievement():
    bot = _FakeBot()
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    viewer = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    target = _FakeMember(user_id=20, display_name="Alex", role_ids=[], manage_guild=False)
    interaction = _FakeInteraction(user=viewer, guild=_FakeGuild(1), channel=_FakeChannel())

    asyncio.run(AchievementsCog.achievements.callback(cog, interaction, user=target))

    assert ("viewed_other_achievements", 10) in bot.achievements_service.unlock_calls


def test_test_achievements_renders_all_configured_cards_for_admin(monkeypatch):
    monkeypatch.setattr("rob.discord.cogs.achievements.discord.Member", _FakeMember)
    bot = _FakeBot()
    cog = AchievementsCog(bot)  # type: ignore[arg-type]
    member = _FakeMember(user_id=10, display_name="Pat", role_ids=[42], manage_guild=True)
    channel = _FakeChannel()
    interaction = _FakeInteraction(user=member, guild=_FakeGuild(1), channel=channel)

    asyncio.run(AchievementsCog.test_achievements.callback(cog, interaction))

    assert interaction.response.messages[0]["ephemeral"] is True
    assert len(channel.messages) == len(bot.achievements_service.all_definitions())
