from __future__ import annotations

import asyncio

from rob.discord.cogs.privacy import PrivacyCog


class _FakeResponse:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)


class _FakeInteraction:
    def __init__(self):
        self.response = _FakeResponse()


def test_privacy_command_returns_multi_container_notice():
    interaction = _FakeInteraction()
    cog = PrivacyCog(bot=object())  # type: ignore[arg-type]

    asyncio.run(PrivacyCog.privacy.callback(cog, interaction))

    payload = interaction.response.messages[0]
    assert payload["ephemeral"] is False
    view = payload["view"]
    assert len(view.children) >= 4
    all_text = "\n".join(
        str(getattr(item, "content", ""))
        for container in view.children
        for item in getattr(container, "children", [])
    )
    assert "Rob Privacy Notice" in all_text
    assert "What Data Rob Collects" in all_text
    assert "How That Data Is Used" in all_text
    assert "Data Minimization Commitment" in all_text
