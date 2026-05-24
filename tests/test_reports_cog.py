from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord

from rob.discord.cogs.reports import ReportsCog


class _FakeDestination:
    def __init__(self):
        self.messages: list[dict] = []

    async def send(self, **kwargs):
        self.messages.append(kwargs)


class _FakeResponse:
    def __init__(self):
        self.messages: list[dict] = []
        self.modal = None

    async def send_modal(self, modal):
        self.modal = modal

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


class _FakeInteraction:
    def __init__(self):
        self.guild = SimpleNamespace(id=1, name="GuildName")
        self.user = SimpleNamespace(id=10, mention="<@10>")
        self.response = _FakeResponse()


class _FakeBot:
    def __init__(self):
        self.guild_settings_repo = SimpleNamespace(get=self._get_settings)
        self.destination = _FakeDestination()

    async def _get_settings(self, _guild_id: int):
        return SimpleNamespace(report_channel_id=123)

    async def application_info(self):
        return SimpleNamespace(owner=self.destination)


def test_report_command_opens_modal():
    bot = _FakeBot()
    cog = ReportsCog(bot)
    interaction = _FakeInteraction()

    asyncio.run(ReportsCog.report.callback(cog, interaction))

    assert interaction.response.modal is not None
    assert len(interaction.response.modal.children) == 3
    assert any(type(child).__name__ == "Label" for child in interaction.response.modal.children)
    assert any(
        isinstance(getattr(child, "component", None), discord.ui.FileUpload)
        for child in interaction.response.modal.children
        if type(child).__name__ == "Label"
    )


def test_report_requires_yes_acknowledgement():
    bot = _FakeBot()
    cog = ReportsCog(bot)
    interaction = _FakeInteraction()

    async def _no_destination(_interaction):
        return bot.destination

    cog._resolve_destination = _no_destination  # type: ignore[method-assign]
    asyncio.run(
        cog.submit_report(
            interaction,
            issue_text="something broke",
            acknowledgement="NO",
            attachment=None,
        )
    )

    assert interaction.response.messages[0]["ephemeral"] is True


def test_report_posts_to_configured_destination_and_confirms_user():
    bot = _FakeBot()
    cog = ReportsCog(bot)
    interaction = _FakeInteraction()

    async def _destination(_interaction):
        return bot.destination

    cog._resolve_destination = _destination  # type: ignore[method-assign]
    asyncio.run(
        cog.submit_report(
            interaction,
            issue_text="send queue stalled",
            acknowledgement="YES",
            attachment=None,
        )
    )

    assert bot.destination.messages
    assert interaction.response.messages[0]["ephemeral"] is True


def test_report_modal_upload_is_forwarded_when_present():
    bot = _FakeBot()
    cog = ReportsCog(bot)
    interaction = _FakeInteraction()

    async def _destination(_interaction):
        return bot.destination

    cog._resolve_destination = _destination  # type: ignore[method-assign]

    class _FakeAttachment:
        url = "https://example.test/screenshot.png"

        async def to_file(self, **_kwargs):
        async def to_file(self):
            return object()

    asyncio.run(
        cog.submit_report(
            interaction,
            issue_text="counting issue",
            acknowledgement="YES",
            attachment=_FakeAttachment(),
        )
    )

    assert "files" in bot.destination.messages[0]


def test_report_modal_upload_falls_back_to_attachment_read():
    bot = _FakeBot()
    cog = ReportsCog(bot)
    interaction = _FakeInteraction()

    async def _destination(_interaction):
        return bot.destination

    cog._resolve_destination = _destination  # type: ignore[method-assign]

    class _FakeAttachment:
        filename = "screenshot.png"
        description = "Counting bug screenshot"
        url = "https://example.test/screenshot.png"

        async def to_file(self, **_kwargs):
            raise TypeError("older attachment path")

        async def read(self, **_kwargs):
            return b"image-bytes"

    asyncio.run(
        cog.submit_report(
            interaction,
            issue_text="counting issue",
            acknowledgement="YES",
            attachment=_FakeAttachment(),
        )
    )

    assert "files" in bot.destination.messages[0]
    assert bot.destination.messages[0]["files"][0].filename == "screenshot.png"
