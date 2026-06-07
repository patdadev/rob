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
    return SimpleNamespace(
        guild_id=guild_id,
        guild=SimpleNamespace(id=guild_id) if guild_id is not None else None,
        user=SimpleNamespace(id=42, mention="<@42>", name="Pat", display_name="Pat"),
        response=response,
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
