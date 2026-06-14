"""Send-queue posting goes to the send-tracking channel in every guild.

The test guild used to DM the Dom/me instead of posting publicly; that DM path
has been removed, so test-guild sends now post to the configured send-tracking
channel exactly like the main guild.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from rob.config.guilds import MAIN_GUILD_ID, TEST_GUILD_ID
from rob.services.send_queue_service import SendQueueService


class _FakeMaintenance:
    async def is_enabled(self) -> bool:
        return False


class _SettingsRepo:
    def __init__(self, send_track_channel_id):
        self._channel_id = send_track_channel_id

    async def get(self, _guild_id):
        return SimpleNamespace(send_track_channel_id=self._channel_id)


class _FakeSends:
    def __init__(self):
        self.mark_posted_calls: list[tuple[int, int | None]] = []
        self.mark_failed_calls: list[tuple[int, str]] = []

    async def mark_posted(self, send_id, *, message_id):
        self.mark_posted_calls.append((send_id, message_id))

    async def mark_failed(self, send_id, *, error):
        self.mark_failed_calls.append((send_id, error))


class _FakeGuild:
    def __init__(self, channel):
        self._channel = channel

    def get_channel(self, _channel_id):
        return self._channel


class _FakeBot:
    def __init__(self, guild):
        self._guild = guild

    def get_guild(self, _guild_id):
        return self._guild


def _channel():
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 12345
    channel.send = AsyncMock(return_value=SimpleNamespace(id=999))
    return channel


def _send(guild_id=TEST_GUILD_ID):
    return SimpleNamespace(
        id=42,
        guild_id=guild_id,
        domme_id=1,
        domme_user_id=10,
        sub_name="someone",
        sub_id=None,
        sub_user_id=None,
        amount_cents=500,
        currency="USD",
        method="throne",
        source="throne",
        item_name=None,
        item_image_url=None,
        external_id=None,
        event_id=None,
        fallback_event_hash=None,
        is_private=False,
        seeded=False,
        sent_at=None,
        received_at=None,
        status="pending",
        discord_posted_at=None,
        discord_message_id=None,
        discord_post_error=None,
        created_at=None,
        is_test_send=False,
        stored_public_send_id=None,
        original_amount_cents=None,
        original_currency=None,
    )


def _service(*, bot, leaderboard=None, send_track_channel_id=12345):
    return SendQueueService(
        bot=bot,
        sends=_FakeSends(),
        guild_settings=_SettingsRepo(send_track_channel_id),
        maintenance=_FakeMaintenance(),
        leaderboard_service=leaderboard
        or SimpleNamespace(
            get_current_leader=AsyncMock(return_value=None),
            maybe_post_leader_alert=AsyncMock(),
        ),
        counting_service=SimpleNamespace(),
        dommes=None,
    )


@pytest.mark.parametrize("guild_id", [TEST_GUILD_ID, MAIN_GUILD_ID])
def test_send_posts_to_tracking_channel(guild_id):
    channel = _channel()
    leaderboard = SimpleNamespace(
        get_current_leader=AsyncMock(return_value=None),
        maybe_post_leader_alert=AsyncMock(),
    )
    service = _service(bot=_FakeBot(_FakeGuild(channel)), leaderboard=leaderboard)

    result = asyncio.run(service._post_send(_send(guild_id=guild_id)))

    assert result is True
    channel.send.assert_awaited_once()
    assert service.sends.mark_posted_calls == [(42, 999)]
    # The standard posting path runs the leader-alert hook in every guild.
    leaderboard.maybe_post_leader_alert.assert_awaited_once()


def test_send_marks_failed_when_guild_unavailable():
    service = _service(bot=_FakeBot(None))

    result = asyncio.run(service._post_send(_send()))

    assert result is False
    assert service.sends.mark_failed_calls
    assert service.sends.mark_failed_calls[0][0] == 42


def test_send_marks_failed_when_no_channel_configured():
    service = _service(
        bot=_FakeBot(_FakeGuild(_channel())),
        send_track_channel_id=None,
    )

    result = asyncio.run(service._post_send(_send()))

    assert result is False
    assert service.sends.mark_failed_calls
    assert service.sends.mark_failed_calls[0][0] == 42
