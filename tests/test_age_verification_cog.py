from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from rob.config.guilds import MAIN_GUILD_ID, TEST_GUILD_ID
from rob.discord.cogs.age_verification import AgeVerificationCog


class _FakeBot:
    def __init__(self, *, enabled: bool, test_only: bool = True):
        self.age_verification_service = SimpleNamespace(
            enabled=enabled,
            test_only=test_only,
            is_enabled_for=MagicMock(
                side_effect=lambda guild_id: enabled and (
                    not test_only or guild_id == TEST_GUILD_ID
                )
            ),
        )
        self.age_verification_backend_client = SimpleNamespace(
            start=AsyncMock(),
            status=AsyncMock(),
        )


def _make_interaction(*, guild_id: int | None):
    response = MagicMock()
    response.send_message = AsyncMock()
    response.defer = AsyncMock()
    response_done = {"value": False}

    def _is_done():
        return response_done["value"]

    response.is_done = _is_done
    original_defer = response.defer

    async def _defer(*args, **kwargs):
        response_done["value"] = True
        return await original_defer(*args, **kwargs)

    response.defer = AsyncMock(side_effect=_defer)
    followup = MagicMock()
    followup.send = AsyncMock()
    return SimpleNamespace(
        guild_id=guild_id,
        guild=SimpleNamespace(id=guild_id) if guild_id is not None else None,
        user=SimpleNamespace(id=42, mention="<@42>", name="Pat", display_name="Pat"),
        response=response,
        followup=followup,
    )


def _all_text_from_sent_view(interaction) -> str:
    kwargs = interaction.response.send_message.await_args.kwargs
    view = kwargs["view"]
    return " ".join(
        item.content for item in view.walk_children() if hasattr(item, "content")
    )


def test_verify_age_reports_disabled_in_test_guild():
    bot = _FakeBot(enabled=False)
    cog = AgeVerificationCog(bot)
    interaction = _make_interaction(guild_id=TEST_GUILD_ID)

    asyncio.run(AgeVerificationCog.verify_age.callback(cog, interaction))

    text = _all_text_from_sent_view(interaction)
    assert "currently disabled on this bot" in text
    assert "only available in the test guild" not in text


def test_verify_age_reports_test_guild_only_outside_test_guild():
    bot = _FakeBot(enabled=True, test_only=True)
    cog = AgeVerificationCog(bot)
    interaction = _make_interaction(guild_id=MAIN_GUILD_ID)

    asyncio.run(AgeVerificationCog.verify_age.callback(cog, interaction))

    text = _all_text_from_sent_view(interaction)
    assert "only available in the test guild" in text


def test_verify_age_defers_before_backend_request_and_uses_followup_for_pending():
    bot = _FakeBot(enabled=True)
    bot.age_verification_backend_client.start = AsyncMock(
        return_value={
            "status": "pending",
            "verification_url": "https://age.yoti.com?sessionId=sess-1&sdkId=sdk-123",
            "expires_at": None,
        }
    )
    cog = AgeVerificationCog(bot)
    interaction = _make_interaction(guild_id=TEST_GUILD_ID)

    asyncio.run(AgeVerificationCog.verify_age.callback(cog, interaction))

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    bot.age_verification_backend_client.start.assert_awaited_once_with(
        guild_id=TEST_GUILD_ID,
        discord_user_id=42,
    )
    interaction.followup.send.assert_awaited_once()
    interaction.response.send_message.assert_not_awaited()


def test_verify_age_backend_error_after_defer_uses_followup():
    from rob.services.age_verification_backend_client import (
        AgeVerificationBackendClientError,
    )

    bot = _FakeBot(enabled=True)
    bot.age_verification_backend_client.start = AsyncMock(
        side_effect=AgeVerificationBackendClientError(
            "Rob couldn't reach the age verification backend."
        )
    )
    cog = AgeVerificationCog(bot)
    interaction = _make_interaction(guild_id=TEST_GUILD_ID)

    asyncio.run(AgeVerificationCog.verify_age.callback(cog, interaction))

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.followup.send.assert_awaited_once()
    text = " ".join(
        item.content
        for item in interaction.followup.send.await_args.kwargs["view"].walk_children()
        if hasattr(item, "content")
    )
    assert "couldn't reach the age verification backend" in text
