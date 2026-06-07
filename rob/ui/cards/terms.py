from __future__ import annotations

import logging
from typing import Any

import discord

from rob.ui.render import RenderedMessage
from rob.ui.theme import COLOR_DANGER, COLOR_INFO, COLOR_SUCCESS
from rob.ui.emojis import ROBNO as _ROBNO, ROBNO_EMOJI, ROBYES as _ROBYES, ROBYES_EMOJI

log = logging.getLogger(__name__)

ROBNO = _ROBNO
ROBYES = _ROBYES

TERMS_PREFIX = "rob:terms:"
ID_TERMS_ACCEPT = f"{TERMS_PREFIX}accept"
ID_TERMS_DECLINE = f"{TERMS_PREFIX}decline"
_UNAVAILABLE_MESSAGE = (
    "These Terms are not available right now. Run any Rob command in the test "
    "server and I'll send a fresh copy."
)


async def _unavailable(interaction: discord.Interaction) -> None:
    data = getattr(interaction, "data", None) or {}
    if isinstance(data, dict):
        custom_id = data.get("custom_id")
    else:
        custom_id = getattr(data, "custom_id", None)
    log.warning(
        "Terms interaction received with no bound cog custom_id=%s user_id=%s channel_id=%s guild_id=%s",
        custom_id,
        getattr(interaction.user, "id", None),
        getattr(interaction, "channel_id", None),
        getattr(interaction, "guild_id", None),
    )
    await interaction.response.send_message(_UNAVAILABLE_MESSAGE, ephemeral=True)


class _BoundButton(discord.ui.Button):
    _HANDLER_NAME: str = ""

    def __init__(
        self,
        cog: Any | None,
        *,
        style: discord.ButtonStyle,
        label: str,
        custom_id: str,
        disabled: bool = False,
        emoji: discord.PartialEmoji | None = None,
    ) -> None:
        super().__init__(
            style=style,
            label=label,
            custom_id=custom_id,
            disabled=disabled,
            emoji=emoji,
        )
        self._cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = self._cog
        if cog is None or not self._HANDLER_NAME:
            await _unavailable(interaction)
            return
        handler = getattr(cog, self._HANDLER_NAME, None)
        if handler is None:
            await _unavailable(interaction)
            return
        await handler(interaction)


class AcceptButton(_BoundButton):
    _HANDLER_NAME = "handle_accept"

    def __init__(
        self,
        cog: Any | None = None,
        *,
        label: str = "Accept",
        disabled: bool = False,
    ) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.success,
            label=label,
            custom_id=ID_TERMS_ACCEPT,
            disabled=disabled,
            emoji=ROBYES_EMOJI,
        )


class DeclineButton(_BoundButton):
    _HANDLER_NAME = "handle_decline"

    def __init__(
        self,
        cog: Any | None = None,
        *,
        label: str = "Decline",
        disabled: bool = False,
    ) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.danger,
            label=label,
            custom_id=ID_TERMS_DECLINE,
            disabled=disabled,
            emoji=ROBNO_EMOJI,
        )


def _document_link_button(*, label: str, url: str) -> discord.ui.Button:
    return discord.ui.Button(
        style=discord.ButtonStyle.link,
        label=label,
        url=url,
    )


class _TermsPromptLayout(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        terms_url: str,
        privacy_url: str,
        cog: Any | None,
    ) -> None:
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=COLOR_INFO)
        container.add_item(
            discord.ui.TextDisplay("### Rob's Terms of Use and Privacy Notice")
        )
        container.add_item(
            discord.ui.TextDisplay(
                "To continue using Rob's awesome features, you'll need to accept "
                "the Terms of Use and Privacy Notice."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Please open and review both documents below before choosing "
                "whether to accept or decline."
            )
        )
        container.add_item(
            discord.ui.ActionRow(
                _document_link_button(label="Terms of Use", url=terms_url),
                _document_link_button(label="Privacy Notice", url=privacy_url),
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Once you've reviewed both documents, you can accept or decline below."
            )
        )
        container.add_item(
            discord.ui.ActionRow(AcceptButton(cog), DeclineButton(cog))
        )
        self.add_item(container)


def terms_prompt_card(
    *,
    terms_url: str,
    privacy_url: str,
    cog: Any | None = None,
) -> RenderedMessage:
    return RenderedMessage(
        view=_TermsPromptLayout(
            terms_url=terms_url,
            privacy_url=privacy_url,
            cog=cog,
        )
    )


class _TermsOutcomeLayout(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        title: str,
        body: str,
        color: discord.Colour,
        button: discord.ui.Button,
    ) -> None:
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=color)
        container.add_item(discord.ui.TextDisplay(f"### {title}"))
        container.add_item(discord.ui.TextDisplay(body))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(button))
        self.add_item(container)


def terms_accepted_card() -> RenderedMessage:
    return RenderedMessage(
        view=_TermsOutcomeLayout(
            title="Thanks! ❤️",
            body=(
                "Thanks for accepting Rob's Terms of Use and Privacy Notice.\n\n"
                "You're now able to use Rob's features."
            ),
            color=COLOR_SUCCESS,
            button=AcceptButton(label="Accepted", disabled=True),
        )
    )


def terms_declined_card() -> RenderedMessage:
    return RenderedMessage(
        view=_TermsOutcomeLayout(
            title="No worries!",
            body=(
                "Not a problem.\n\n"
                "If you ever change your mind, run any Rob command in the server "
                "and I'll send these through again."
            ),
            color=COLOR_DANGER,
            button=DeclineButton(label="Declined", disabled=True),
        )
    )


class _SimpleTermsLayout(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        title: str,
        body: str,
        color: discord.Colour,
        button_label: str | None = None,
        button_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=color)
        container.add_item(discord.ui.TextDisplay(f"## {title}"))
        container.add_item(discord.ui.TextDisplay(body))
        if button_label and button_url:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.ActionRow(
                    _document_link_button(label=button_label, url=button_url)
                )
            )
        self.add_item(container)


def terms_dm_blocked_card(*, name: str) -> RenderedMessage:
    return RenderedMessage(
        view=_SimpleTermsLayout(
            title="I couldn't send you a DM",
            body=(
                f"Hey {name}! I need you to agree to Rob's Terms of Use and "
                "Privacy Notice before you can use Rob, but I couldn't send you a DM.\n\n"
                "Please allow DMs from this server, then try again."
            ),
            color=COLOR_DANGER,
        )
    )
