from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from rob.config.guilds import TEST_GUILD_ID
from rob.discord.cogs.terms import TermsCog
from rob.ui.cards.terms import ID_TERMS_ACCEPT


class _FakeMessage:
    def __init__(self, message_id=777, channel_id=888):
        self.id = message_id
        self.channel = SimpleNamespace(id=channel_id)


class _FakeUser:
    def __init__(self, *, user_id=1, name="Tester", send_exception=None):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.send_exception = send_exception
        self.sent_messages: list[dict] = []

    async def send(self, **kwargs):
        if self.send_exception is not None:
            raise self.send_exception
        self.sent_messages.append(kwargs)
        return _FakeMessage()


class _FakeBot:
    def __init__(self, *, gate_status="prompt", state=None):
        self.terms_service = MagicMock()
        self.terms_service.is_enabled_for = MagicMock(return_value=True)
        self.terms_service.gate_status_for_user = AsyncMock(return_value=gate_status)
        self.terms_service.record_prompt = AsyncMock()
        self.terms_service.get_state = AsyncMock(return_value=state)
        self.terms_service.accept = AsyncMock(return_value=state)
        self.terms_service.decline = AsyncMock(return_value=state)
        self.terms_service.terms_url = "https://example.com/terms"
        self.terms_service.privacy_url = "https://example.com/privacy"
        self.terms_service.terms_version = "2026-06-05"
        self.terms_service.owner_mention = "<@55>"
        self.added_views: list[discord.ui.View] = []

    def add_view(self, view):
        self.added_views.append(view)


def _make_interaction(
    *,
    user=None,
    guild_id=TEST_GUILD_ID,
    message=None,
    command_name="leaderboard",
):
    response = MagicMock()
    response.send_message = AsyncMock()
    response.edit_message = AsyncMock()
    return SimpleNamespace(
        user=user or _FakeUser(),
        guild_id=guild_id,
        message=message,
        response=response,
        command=SimpleNamespace(qualified_name=command_name),
    )


def test_register_persistent_views_registers_terms_buttons():
    bot = _FakeBot()
    cog = TermsCog(bot)
    cog.register_persistent_views()
    assert len(bot.added_views) == 1


def test_first_time_user_gets_terms_dm_and_is_blocked():
    bot = _FakeBot(gate_status="prompt")
    cog = TermsCog(bot)
    user = _FakeUser(user_id=7, name="Aria")
    interaction = _make_interaction(user=user)

    allowed = asyncio.run(cog.ensure_terms_acceptance(interaction))

    assert allowed is False
    assert len(user.sent_messages) == 1
    bot.terms_service.record_prompt.assert_awaited_once_with(
        discord_user_id=7,
        dm_channel_id=888,
        dm_message_id=777,
    )
    interaction.response.send_message.assert_awaited_once()
    welcome_text = interaction.response.send_message.await_args.args[0]
    assert "Welcome to Rob" in welcome_text


def test_pending_user_gets_reminder_without_duplicate_dm():
    bot = _FakeBot(gate_status="pending")
    cog = TermsCog(bot)
    user = _FakeUser(name="Aria")
    interaction = _make_interaction(user=user)

    allowed = asyncio.run(cog.ensure_terms_acceptance(interaction))

    assert allowed is False
    assert user.sent_messages == []
    bot.terms_service.record_prompt.assert_not_awaited()
    reminder_text = interaction.response.send_message.await_args.args[0]
    assert "still yet to accept or decline" in reminder_text
    assert "<@55>" in reminder_text


def test_accepted_user_can_run_command():
    bot = _FakeBot(gate_status="accepted")
    cog = TermsCog(bot)
    interaction = _make_interaction()

    allowed = asyncio.run(cog.ensure_terms_acceptance(interaction))

    assert allowed is True
    interaction.response.send_message.assert_not_awaited()


def test_dm_blocked_user_gets_server_card():
    bot = _FakeBot(gate_status="prompt")
    cog = TermsCog(bot)
    user = _FakeUser(
        name="Aria",
        send_exception=discord.Forbidden(MagicMock(status=403), "blocked"),
    )
    interaction = _make_interaction(user=user)

    allowed = asyncio.run(cog.ensure_terms_acceptance(interaction))

    assert allowed is False
    kwargs = interaction.response.send_message.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["view"] is not None


def test_handle_accept_records_acceptance_and_edits_message():
    state = SimpleNamespace(dm_message_id=777)
    bot = _FakeBot(state=state)
    cog = TermsCog(bot)
    interaction = _make_interaction(message=SimpleNamespace(id=777))

    asyncio.run(cog.handle_accept(interaction))

    bot.terms_service.accept.assert_awaited_once_with(discord_user_id=1)
    interaction.response.edit_message.assert_awaited_once()


def test_handle_decline_records_decline_and_edits_message():
    state = SimpleNamespace(dm_message_id=777)
    bot = _FakeBot(state=state)
    cog = TermsCog(bot)
    interaction = _make_interaction(message=SimpleNamespace(id=777))

    asyncio.run(cog.handle_decline(interaction))

    bot.terms_service.decline.assert_awaited_once_with(discord_user_id=1)
    interaction.response.edit_message.assert_awaited_once()


def test_handle_accept_rejects_stale_message():
    state = SimpleNamespace(dm_message_id=999)
    bot = _FakeBot(state=state)
    cog = TermsCog(bot)
    interaction = _make_interaction(message=SimpleNamespace(id=777))

    asyncio.run(cog.handle_accept(interaction))

    bot.terms_service.accept.assert_not_awaited()
    stale_text = interaction.response.send_message.await_args.args[0]
    assert "no longer active" in stale_text


def test_terms_and_privacy_commands_send_cards():
    bot = _FakeBot()
    cog = TermsCog(bot)
    terms_interaction = _make_interaction(command_name="terms")
    privacy_interaction = _make_interaction(command_name="privacy")

    asyncio.run(TermsCog.terms.callback(cog, terms_interaction))
    asyncio.run(TermsCog.privacy.callback(cog, privacy_interaction))

    assert terms_interaction.response.send_message.await_args.kwargs["view"] is not None
    assert privacy_interaction.response.send_message.await_args.kwargs["view"] is not None


def test_terms_interaction_detection_supports_commands_and_buttons():
    command_interaction = _make_interaction(command_name="terms")
    button_interaction = _make_interaction(command_name="leaderboard")
    button_interaction.data = {"custom_id": ID_TERMS_ACCEPT}

    assert TermsCog.is_terms_interaction(command_interaction) is True
    assert TermsCog.is_terms_interaction(button_interaction) is True
