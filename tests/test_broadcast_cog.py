from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from rob.discord.cogs.broadcast import BroadcastCog


class _FakeResponse:
    def __init__(self):
        self.messages: list[dict] = []
        self.modal = None

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)

    async def send_modal(self, modal):
        self.modal = modal


class _FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class _FakeInteraction:
    def __init__(self, *, user_id: int, guild=None):
        self.user = _FakeUser(user_id)
        self.guild = guild
        self.response = _FakeResponse()


class _FakeTextChannel:
    def __init__(self, channel_id: int, guild):
        self.id = channel_id
        self.guild = guild
        self.messages: list[dict] = []

    async def send(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(id=555)


class _FakeGuild:
    def __init__(self, guild_id: int, channel: _FakeTextChannel):
        self.id = guild_id
        self.name = "Rob Test Server"
        self._channel = channel

    def get_channel(self, channel_id: int):
        if channel_id == self._channel.id:
            return self._channel
        return None


class _FakeBot:
    def __init__(self):
        self.settings = SimpleNamespace(inactivity_owner_user_id=None)
        self._channel = _FakeTextChannel(20, None)
        self._guild = _FakeGuild(10, self._channel)
        self._channel.guild = self._guild

    async def application_info(self):
        return SimpleNamespace(owner=SimpleNamespace(id=1))

    def get_guild(self, guild_id: int):
        if guild_id == self._guild.id:
            return self._guild
        return None

    async def fetch_channel(self, channel_id: int):
        if channel_id == self._channel.id:
            return self._channel
        return None


def test_broadcast_command_requires_dm():
    bot = _FakeBot()
    cog = BroadcastCog(bot)
    interaction = _FakeInteraction(user_id=1, guild=SimpleNamespace(id=999))

    asyncio.run(
        BroadcastCog.broadcast.callback(
            cog,
            interaction,
            style=SimpleNamespace(value="purple"),
            ping=None,
            image_url=None,
        )
    )

    assert interaction.response.messages
    assert interaction.response.messages[0]["ephemeral"] is True


def test_broadcast_command_requires_owner_in_dm():
    bot = _FakeBot()
    cog = BroadcastCog(bot)
    interaction = _FakeInteraction(user_id=2, guild=None)

    asyncio.run(
        BroadcastCog.broadcast.callback(
            cog,
            interaction,
            style=SimpleNamespace(value="purple"),
            ping=None,
            image_url=None,
        )
    )

    assert interaction.response.modal is None
    assert interaction.response.messages


def test_broadcast_command_opens_modal_for_owner_in_dm():
    bot = _FakeBot()
    cog = BroadcastCog(bot)
    interaction = _FakeInteraction(user_id=1, guild=None)

    asyncio.run(
        BroadcastCog.broadcast.callback(
            cog,
            interaction,
            style=SimpleNamespace(value="purple"),
            ping=SimpleNamespace(value="none"),
            image_url=None,
        )
    )

    assert interaction.response.modal is not None
    assert len(interaction.response.modal.children) == 5


def test_submit_broadcast_sends_components_v2_card(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("rob.discord.cogs.broadcast.discord.TextChannel", _FakeTextChannel)
    bot = _FakeBot()
    cog = BroadcastCog(bot)
    interaction = _FakeInteraction(user_id=1, guild=None)

    asyncio.run(
        cog.submit_broadcast(
            interaction,
            guild_id_raw="10",
            channel_id_raw="20",
            title="Status Update",
            body="Rob deploy completed successfully.",
            helper="No action required.",
            style="success",
            ping="none",
            image_url=None,
        )
    )

    assert bot._channel.messages
    rendered = bot._channel.messages[0]
    assert rendered["view"] is not None
    assert interaction.response.messages
