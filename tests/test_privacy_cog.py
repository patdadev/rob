from __future__ import annotations

import asyncio

import discord

from rob.discord.cogs.privacy import PrivacyCog
from rob.ui.cards.privacy import PRIVACY_NOTICE_FOOTER, privacy_notice_message

EXPECTED_DESCRIPTION = (
    "View Rob's privacy notice, including what information may be collected, stored, and used."
)

EXPECTED_SECTIONS = [
    "Rob Privacy Notice",
    "Information Collected or Received",
    "Purpose of Processing",
    "Data Minimisation and Third-Party Services",
    "Public Display of Information",
    "User Control and Data Removal",
    "Changes to This Notice",
]

FORBIDDEN_PHRASES = [
    "little privacy thing",
    "Rob Promise",
    "If you have concerns...",
    "lol",
    "jokes",
    "informal commentary",
]


class _FakeResponse:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


class _FakeInteraction:
    def __init__(self):
        self.response = _FakeResponse()


def _rendered_text_from_view(view: discord.ui.LayoutView) -> str:
    return "\n".join(
        str(getattr(item, "content", ""))
        for container in view.children
        for item in getattr(container, "children", [])
    )


def test_privacy_command_metadata_matches_expected():
    command = PrivacyCog.privacy
    assert command.name == "privacy"
    assert command.description == EXPECTED_DESCRIPTION


def test_privacy_command_responds_ephemeral_with_components_v2_message():
    interaction = _FakeInteraction()
    cog = PrivacyCog(bot=object())  # type: ignore[arg-type]

    asyncio.run(PrivacyCog.privacy.callback(cog, interaction))

    payload = interaction.response.messages[0]
    assert payload["ephemeral"] is True
    assert "view" in payload
    assert "embed" not in payload
    assert "embeds" not in payload


def test_privacy_notice_message_has_seven_containers_with_required_footer_and_sections():
    message = privacy_notice_message()
    payload = message.send_kwargs()
    view = payload["view"]

    assert len(view.children) == 7
    assert all(isinstance(container, discord.ui.Container) for container in view.children)

    all_text = _rendered_text_from_view(view)
    for section in EXPECTED_SECTIONS:
        assert section in all_text

    for container in view.children:
        container_text = "\n".join(
            str(getattr(item, "content", "")) for item in getattr(container, "children", [])
        )
        assert PRIVACY_NOTICE_FOOTER in container_text
        assert any(
            isinstance(item, discord.ui.Separator) for item in getattr(container, "children", [])
        )


def test_privacy_notice_wording_avoids_casual_phrases():
    all_text = _rendered_text_from_view(privacy_notice_message().send_kwargs()["view"])
    for forbidden in FORBIDDEN_PHRASES:
        assert forbidden not in all_text


def test_privacy_command_not_role_restricted():
    checks = getattr(PrivacyCog.privacy.callback, "__discord_app_commands_checks__", [])
    assert checks == []
