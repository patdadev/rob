"""Components V2 cards for the DM-based Dom/me onboarding flow.

All cards here are test-guild-only. Gating to ``is_test_guild`` is the
caller's responsibility. The interaction handlers live on
:class:`rob.discord.cogs.dm_onboarding.DMOnboardingCog` and the
orchestration on :class:`rob.services.dm_onboarding_service.DMOnboardingService`.

Each card returns a :class:`~rob.ui.render.RenderedMessage` whose ``view``
is a :class:`~discord.ui.LayoutView` ready to be sent or edited into the
ongoing DM message.

Interaction model
-----------------

Every interactive button used in the flow lives inside a
:class:`discord.ui.ActionRow` *inside* a :class:`discord.ui.Container` (so
it visually sits in the bottom-left of the card) and is implemented by a
small :class:`discord.ui.Button` subclass with a ``callback`` bound to the
cog. The card builders accept an optional ``cog`` keyword and pass it
through to the buttons. When no cog is supplied (e.g. tests, or a stale
DM rebuilt without a runtime cog reference) the button responds with a
clear ephemeral notice instead of timing out — that prevents the
"This interaction failed" message Discord shows when no response is sent
within ~3 seconds.
"""

from __future__ import annotations

import logging
from typing import Any

import discord

from rob.ui.render import RenderedMessage
from rob.ui.theme import COLOR_INFO, COLOR_SUCCESS, COLOR_WARNING

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stable custom IDs — kept stable so persistent views can re-bind callbacks
# after a restart.
# ---------------------------------------------------------------------------
ONBOARDING_PREFIX = "rob:dm_onboarding:"
ID_INTRO_OPEN_MODAL = f"{ONBOARDING_PREFIX}intro:open_modal"
ID_INTRO_MODAL = f"{ONBOARDING_PREFIX}intro:modal"
ID_INTRO_MODAL_FIELD = f"{ONBOARDING_PREFIX}intro:modal:throne_input"
ID_IDENTITY_YES = f"{ONBOARDING_PREFIX}identity:yes"
ID_IDENTITY_NO = f"{ONBOARDING_PREFIX}identity:no"
ID_WEBHOOK_RETRY = f"{ONBOARDING_PREFIX}webhook:retry"
ID_PREFS_LEADERBOARD = f"{ONBOARDING_PREFIX}prefs:leaderboard"
ID_PREFS_LEADERBOARD_ACCESS = f"{ONBOARDING_PREFIX}prefs:leaderboard_access"
ID_PREFS_SAVE = f"{ONBOARDING_PREFIX}prefs:save"

MIGRATION_PREFIX = "rob:dm_migration:"
ID_MIGRATION_OPEN_PREFS = f"{MIGRATION_PREFIX}open_prefs"
ID_MIGRATION_DEFER = f"{MIGRATION_PREFIX}defer_7d"
ID_MIGRATION_LEADERBOARD = f"{MIGRATION_PREFIX}leaderboard"
ID_MIGRATION_LEADERBOARD_ACCESS = f"{MIGRATION_PREFIX}leaderboard_access"
ID_MIGRATION_SAVE = f"{MIGRATION_PREFIX}save"

# Preference option values stored on each ``SelectOption``.
LEADERBOARD_SHOW_VALUE = "leaderboard_show"
LEADERBOARD_HIDE_VALUE = "leaderboard_hide"
LEADERBOARD_ACCESS_ON_VALUE = "leaderboard_access_on"
LEADERBOARD_ACCESS_OFF_VALUE = "leaderboard_access_off"


# ---------------------------------------------------------------------------
# Small presentation helpers
# ---------------------------------------------------------------------------


def _progress(step: int, total: int = 5) -> str:
    """Return a subtle one-line progress indicator, e.g.

    ``-# Step 2 of 5  ▰▰▱▱▱``

    Rendered as Discord small text so it sits quietly above the heading and
    helps the Dom/me see how far through setup they are.
    """

    step = max(0, min(step, total))
    filled = "▰" * step
    empty = "▱" * (total - step)
    if step >= total:
        return f"-# ✅ All done  {filled}"
    return f"-# Step {step} of {total}  {filled}{empty}"


_UNAVAILABLE_MESSAGE = (
    "This setup isn't available right now. Run /register domme again in the "
    "test server to start fresh."
)


# ---------------------------------------------------------------------------
# Bound button + select primitives
# ---------------------------------------------------------------------------


async def _unavailable(interaction: discord.Interaction) -> None:
    """Fallback handler for buttons rendered without a live cog binding.

    We must respond to the interaction before Discord's 3s timeout, otherwise
    the user sees "This interaction failed". Logging makes it diagnosable.
    """

    data = getattr(interaction, "data", None) or {}
    if isinstance(data, dict):
        custom_id = data.get("custom_id")
    else:
        custom_id = getattr(data, "custom_id", None)
    log.warning(
        "Onboarding interaction received with no bound cog "
        "custom_id=%s user_id=%s channel_id=%s guild_id=%s",
        custom_id,
        getattr(interaction.user, "id", None),
        getattr(interaction, "channel_id", None),
        getattr(interaction, "guild_id", None),
    )
    try:
        await interaction.response.send_message(
            _UNAVAILABLE_MESSAGE, ephemeral=True
        )
    except discord.HTTPException:  # pragma: no cover - best effort
        log.exception("Failed to send unavailable response for onboarding click")


class _BoundButton(discord.ui.Button):
    """Persistent button whose callback delegates to a named cog method.

    ``cog`` is intentionally duck-typed (``Any``) so this module stays free
    of cog-side imports. The cog method receives the raw ``interaction``.
    """

    _HANDLER_NAME: str = ""

    def __init__(
        self,
        cog: Any | None,
        *,
        style: discord.ButtonStyle,
        label: str,
        custom_id: str,
    ) -> None:
        super().__init__(style=style, label=label, custom_id=custom_id)
        self._cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = self._cog
        if cog is None or not self._HANDLER_NAME:
            await _unavailable(interaction)
            return
        handler = getattr(cog, self._HANDLER_NAME, None)
        if handler is None:
            log.error(
                "Onboarding cog missing handler %s for custom_id=%s",
                self._HANDLER_NAME,
                self.custom_id,
            )
            await _unavailable(interaction)
            return
        log.info(
            "Onboarding button click custom_id=%s user_id=%s channel_id=%s guild_id=%s",
            self.custom_id,
            getattr(interaction.user, "id", None),
            getattr(interaction, "channel_id", None),
            getattr(interaction, "guild_id", None),
        )
        await handler(interaction)


class OpenModalButton(_BoundButton):
    _HANDLER_NAME = "handle_open_modal"

    def __init__(self, cog: Any | None = None) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.primary,
            label="Enter Throne details",
            custom_id=ID_INTRO_OPEN_MODAL,
        )


class IdentityYesButton(_BoundButton):
    _HANDLER_NAME = "handle_identity_yes"

    def __init__(self, cog: Any | None = None) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.success,
            label="Sure does!",
            custom_id=ID_IDENTITY_YES,
        )


class IdentityNoButton(_BoundButton):
    _HANDLER_NAME = "handle_identity_no"

    def __init__(self, cog: Any | None = None) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.danger,
            label="Not quite!",
            custom_id=ID_IDENTITY_NO,
        )


class WebhookRetryButton(_BoundButton):
    _HANDLER_NAME = "handle_webhook_retry"

    def __init__(self, cog: Any | None = None) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.secondary,
            label="Doesn’t look to have worked!",
            custom_id=ID_WEBHOOK_RETRY,
        )


class SavePrefsButton(_BoundButton):
    _HANDLER_NAME = "handle_save_preferences"

    def __init__(self, cog: Any | None = None) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.success,
            label="Save preferences",
            custom_id=ID_PREFS_SAVE,
        )


class MigrationSaveButton(_BoundButton):
    _HANDLER_NAME = "handle_migration_save"

    def __init__(self, cog: Any | None = None) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.success,
            label="Save preferences",
            custom_id=ID_MIGRATION_SAVE,
        )


class MigrationDeferButton(_BoundButton):
    _HANDLER_NAME = "handle_migration_defer"

    def __init__(self, cog: Any | None = None) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.secondary,
            label="Defer for 7 days",
            custom_id=ID_MIGRATION_DEFER,
        )


class MigrationOpenPrefsButton(_BoundButton):
    """Legacy custom_id kept registered so any pre-existing card in the wild
    can still be clicked without surfacing "This interaction failed"."""

    _HANDLER_NAME = "handle_migration_open_prefs"

    def __init__(self, cog: Any | None = None) -> None:
        super().__init__(
            cog,
            style=discord.ButtonStyle.primary,
            label="Open preferences",
            custom_id=ID_MIGRATION_OPEN_PREFS,
        )


class _AckSelect(discord.ui.Select):
    """Select that just acknowledges the click so Discord doesn't show a
    "This interaction failed" toast when the user changes a preference. The
    actual value read happens later, when the user clicks Save."""

    async def callback(self, interaction: discord.Interaction) -> None:
        log.debug(
            "Onboarding select change custom_id=%s user_id=%s values=%s",
            self.custom_id,
            getattr(interaction.user, "id", None),
            list(self.values or []),
        )
        try:
            await interaction.response.defer()
        except discord.InteractionResponded:  # pragma: no cover - defensive
            pass
        except discord.HTTPException:  # pragma: no cover - defensive
            log.exception("Failed to defer onboarding select interaction")


# ---------------------------------------------------------------------------
# Card layouts
# ---------------------------------------------------------------------------


class _IntroLayout(discord.ui.LayoutView):
    def __init__(self, *, name: str | None, cog: Any | None) -> None:
        super().__init__(timeout=None)
        display = (name or "there").strip() or "there"

        container = discord.ui.Container(accent_color=COLOR_INFO)
        container.add_item(discord.ui.TextDisplay(_progress(1)))
        container.add_item(discord.ui.TextDisplay(f"## 👋 Hey {display}, Rob here!"))
        container.add_item(
            discord.ui.TextDisplay(
                "Thanks for signing up for **Throne tracking**! It only takes a "
                "minute — I'll walk you through it one step at a time."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "**First up:** what's your Throne username or profile link?"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(OpenModalButton(cog)))
        self.add_item(container)


def intro_card(name: str | None = None, *, cog: Any | None = None) -> RenderedMessage:
    """Step 1: greet the Dom/me and ask for their Throne username or link."""

    return RenderedMessage(view=_IntroLayout(name=name, cog=cog))


def build_intro_modal(*, cog: Any | None = None, guild_id: int | None = None) -> discord.ui.Modal:
    """Throne input modal. ``on_submit`` delegates to ``cog.handle_modal_submit``."""

    class _ThroneInputModal(discord.ui.Modal, title="Your Throne profile"):
        throne_input: discord.ui.TextInput = discord.ui.TextInput(
            label="Throne username or link",
            placeholder="e.g. yourname  or  https://throne.com/yourname",
            required=True,
            max_length=200,
            custom_id=ID_INTRO_MODAL_FIELD,
        )

        def __init__(self) -> None:
            super().__init__(custom_id=ID_INTRO_MODAL)
            self._cog = cog
            self._guild_id = guild_id

        async def on_submit(self, interaction: discord.Interaction) -> None:
            log.info(
                "Onboarding modal submit user_id=%s guild_id=%s",
                getattr(interaction.user, "id", None),
                self._guild_id,
            )
            if self._cog is None:
                await _unavailable(interaction)
                return
            await self._cog.handle_modal_submit(
                interaction,
                guild_id=int(self._guild_id) if self._guild_id is not None else 0,
                throne_input=str(self.throne_input.value),
            )

    return _ThroneInputModal()


class _IdentityConfirmLayout(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        throne_handle: str,
        throne_display_name: str | None,
        cog: Any | None,
    ) -> None:
        super().__init__(timeout=None)
        display = (throne_display_name or throne_handle or "").strip() or throne_handle

        container = discord.ui.Container(accent_color=COLOR_INFO)
        container.add_item(discord.ui.TextDisplay(_progress(2)))
        container.add_item(discord.ui.TextDisplay("## 🔎 Quick check"))
        container.add_item(
            discord.ui.TextDisplay(
                "Nice one! I found a Throne profile — does this look right to you?"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(f"**Throne username:** {throne_handle}")
        )
        container.add_item(
            discord.ui.TextDisplay(f"**Name on Throne:** {display}")
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.ActionRow(IdentityYesButton(cog), IdentityNoButton(cog))
        )
        self.add_item(container)


def identity_confirm_card(
    *,
    throne_handle: str,
    throne_display_name: str | None,
    cog: Any | None = None,
) -> RenderedMessage:
    """Step 3: confirm the Throne identity Rob resolved."""

    return RenderedMessage(
        view=_IdentityConfirmLayout(
            throne_handle=throne_handle,
            throne_display_name=throne_display_name,
            cog=cog,
        )
    )


class _WebhookSetupLayout(discord.ui.LayoutView):
    def __init__(self, *, webhook_url: str, cog: Any | None) -> None:
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=COLOR_WARNING)
        container.add_item(discord.ui.TextDisplay(_progress(3)))
        container.add_item(discord.ui.TextDisplay("## 🔗 Connect Throne to Rob"))
        container.add_item(
            discord.ui.TextDisplay(
                "This is the one fiddly bit — it lets Rob hear about your sends "
                "the moment they happen. Follow along:"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "**1.** Open Throne → **Settings** → **Integrations**\n"
                "**2.** Scroll to **Webhooks** and click **Enable Webhooks**\n"
                "**3.** Under **Subscriber URLs**, click **Add URL**\n"
                "**4.** Paste Rob’s URL (below), then click **Save Settings**\n"
                "**5.** Click **Test Webhook** and wait for the success message"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay("**📋 Rob’s webhook URL** (tap to copy):")
        )
        container.add_item(discord.ui.TextDisplay(f"```\n{webhook_url}\n```"))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Once you’ve hit **Test Webhook**, hang tight here — I’ll update "
                "this message automatically the second your test send lands. 🎉"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay("**Status:** ⏳ Waiting for Throne…")
        )
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(WebhookRetryButton(cog)))
        self.add_item(container)


def webhook_setup_card(
    *, webhook_url: str, cog: Any | None = None
) -> RenderedMessage:
    """Step 4: ask the user to plug Rob's webhook URL into Throne."""

    return RenderedMessage(view=_WebhookSetupLayout(webhook_url=webhook_url, cog=cog))


def webhook_waiting_card(*, cog: Any | None = None) -> RenderedMessage:
    """Backwards-compat shim used by older tests."""

    return webhook_setup_card(webhook_url="(your webhook URL above)", cog=cog)


# ---------------------------------------------------------------------------
# Step 6 — Preferences selection card
# ---------------------------------------------------------------------------


class PreferencesView(discord.ui.LayoutView):
    """Leaderboard preferences via Components V2.

    Two selects can live inside the container with a Save button as the final
    action row. ``show_domme_controls`` toggles the Dom/me-only "appear on
    leaderboard" select (turned off for non-Dom/mes using ``/preferences``).
    ``show_leaderboard_access`` toggles the universal "leaderboard access"
    select that, on save, has Rob grant/remove the access role (which opens the
    #leaderboard channel and the /leaderboard command).

    The select objects are always created so the ``chosen_*`` properties stay
    safe to read; only the requested ones are rendered.
    """

    def __init__(
        self,
        *,
        default_leaderboard_visible: bool = True,
        default_leaderboard_access: bool = False,
        leaderboard_custom_id: str = ID_PREFS_LEADERBOARD,
        leaderboard_access_custom_id: str = ID_PREFS_LEADERBOARD_ACCESS,
        save_custom_id: str = ID_PREFS_SAVE,
        show_domme_controls: bool = True,
        show_leaderboard_access: bool = True,
        intro_lines: tuple[str, ...] = (
            "## 🎉 Almost there — the hard part’s done!",
            "Now just tell Rob how you’d like things handled from here.",
        ),
        cog: Any | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self._default_leaderboard_visible = default_leaderboard_visible
        self._default_leaderboard_access = default_leaderboard_access

        self.leaderboard_select = _AckSelect(
            custom_id=leaderboard_custom_id,
            placeholder="📊 Leaderboard visibility",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="👑 Show me on the leaderboard",
                    value=LEADERBOARD_SHOW_VALUE,
                    default=default_leaderboard_visible,
                ),
                discord.SelectOption(
                    label="🙈 Keep me off the leaderboard",
                    value=LEADERBOARD_HIDE_VALUE,
                    default=not default_leaderboard_visible,
                ),
            ],
        )
        self.leaderboard_access_select = _AckSelect(
            custom_id=leaderboard_access_custom_id,
            placeholder="🔑 Leaderboard access",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="🔑 Give me leaderboard access",
                    value=LEADERBOARD_ACCESS_ON_VALUE,
                    description="Unlocks #leaderboard and /leaderboard",
                    default=default_leaderboard_access,
                ),
                discord.SelectOption(
                    label="🚫 No leaderboard access",
                    value=LEADERBOARD_ACCESS_OFF_VALUE,
                    description="Keep the leaderboard hidden from me",
                    default=not default_leaderboard_access,
                ),
            ],
        )

        container = discord.ui.Container(accent_color=COLOR_INFO)
        for line in intro_lines:
            container.add_item(discord.ui.TextDisplay(line))
        container.add_item(discord.ui.Separator())

        if show_domme_controls:
            container.add_item(discord.ui.TextDisplay("### 📊 Leaderboard visibility"))
            container.add_item(
                discord.ui.TextDisplay(
                    "Should your totals appear **on** the leaderboard for others to see?"
                )
            )
            container.add_item(discord.ui.ActionRow(self.leaderboard_select))
            container.add_item(discord.ui.Separator())

        if show_leaderboard_access:
            container.add_item(discord.ui.TextDisplay("### 🔑 Leaderboard access"))
            container.add_item(
                discord.ui.TextDisplay(
                    "Want to **see** the leaderboard? Rob will give you the access "
                    "role so the #leaderboard channel and `/leaderboard` open up."
                )
            )
            container.add_item(discord.ui.ActionRow(self.leaderboard_access_select))
            container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                "-# You can change these any time with `/preferences` in the server."
            )
        )
        container.add_item(discord.ui.Separator())

        save = SavePrefsButton(cog)
        # Allow ``save_custom_id`` overrides used by older callers (settings cog).
        if save_custom_id != ID_PREFS_SAVE:
            save.custom_id = save_custom_id
        self.save_button = save
        container.add_item(discord.ui.ActionRow(save))
        self.add_item(container)

    @property
    def chosen_leaderboard_visible(self) -> bool:
        values = self.leaderboard_select.values
        if not values:
            return self._default_leaderboard_visible
        return values[0] == LEADERBOARD_SHOW_VALUE

    @property
    def chosen_leaderboard_access(self) -> bool:
        values = self.leaderboard_access_select.values
        if not values:
            return self._default_leaderboard_access
        return values[0] == LEADERBOARD_ACCESS_ON_VALUE


def preferences_card(
    *,
    default_leaderboard_visible: bool = True,
    default_leaderboard_access: bool = False,
    show_domme_controls: bool = True,
    show_leaderboard_access: bool = True,
    cog: Any | None = None,
) -> RenderedMessage:
    view = PreferencesView(
        default_leaderboard_visible=default_leaderboard_visible,
        default_leaderboard_access=default_leaderboard_access,
        show_domme_controls=show_domme_controls,
        show_leaderboard_access=show_leaderboard_access,
        cog=cog,
    )
    return RenderedMessage(view=view)


# ---------------------------------------------------------------------------
# Step 7 — Final success card
# ---------------------------------------------------------------------------


class _SuccessLayout(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        leaderboard_visible: bool,
        leaderboard_access: bool | None = None,
    ) -> None:
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=COLOR_SUCCESS)
        container.add_item(discord.ui.TextDisplay(_progress(5)))
        container.add_item(
            discord.ui.TextDisplay(
                "## 🎉 You’re all set — Rob’s now tracking your Throne sends!"
            )
        )
        container.add_item(
            discord.ui.TextDisplay(
                "Your sends will show up in the send-tracking channel. I’ll always "
                "respect your leaderboard choices, and you can tweak them any time "
                "with `/preferences` in the server."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "If anything ever looks off, give me a shout with `/report`."
            )
        )
        lb_line = (
            "👑 Shown on the leaderboard"
            if leaderboard_visible
            else "🙈 Hidden from the leaderboard"
        )
        summary = lb_line
        if leaderboard_access is not None:
            access_line = (
                "🔑 Leaderboard access on"
                if leaderboard_access
                else "🚫 Leaderboard access off"
            )
            summary = f"{summary}  •  {access_line}"
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {summary}"))
        self.add_item(container)


def success_card(
    *,
    leaderboard_visible: bool = True,
    leaderboard_access: bool | None = None,
) -> RenderedMessage:
    return RenderedMessage(
        view=_SuccessLayout(
            leaderboard_visible=leaderboard_visible,
            leaderboard_access=leaderboard_access,
        )
    )


# ---------------------------------------------------------------------------
# Migration prompt (already-registered Dom/mes in the test guild)
# ---------------------------------------------------------------------------


class MigrationPromptView(discord.ui.LayoutView):
    """Migration prompt that shows the same preference menus alongside a
    Defer for 7 days button. Both action buttons live inside the container.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        default_leaderboard_visible: bool = True,
        default_leaderboard_access: bool = False,
        cog: Any | None = None,
    ) -> None:
        super().__init__(timeout=None)
        display = (name or "there").strip() or "there"
        self._default_leaderboard_visible = default_leaderboard_visible
        self._default_leaderboard_access = default_leaderboard_access

        container = discord.ui.Container(accent_color=COLOR_INFO)
        container.add_item(discord.ui.TextDisplay(f"## 👋 Hey {display}, Rob here!"))
        container.add_item(
            discord.ui.TextDisplay(
                "As announced by Pat earlier this week, I’m tidying up how Rob "
                "handles the leaderboard for your automatically-tracked sends."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Your sends still post in the send-tracking channel. You can choose "
                "whether you appear on the leaderboard and whether you can see it."
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(discord.ui.TextDisplay("### 📊 Leaderboard visibility"))
        self.leaderboard_select = _AckSelect(
            custom_id=ID_MIGRATION_LEADERBOARD,
            placeholder="📊 Leaderboard visibility",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="👑 Show me on the leaderboard",
                    value=LEADERBOARD_SHOW_VALUE,
                    default=default_leaderboard_visible,
                ),
                discord.SelectOption(
                    label="🔒 Keep me off the leaderboard",
                    value=LEADERBOARD_HIDE_VALUE,
                    default=not default_leaderboard_visible,
                ),
            ],
        )
        container.add_item(discord.ui.ActionRow(self.leaderboard_select))
        container.add_item(discord.ui.Separator())

        container.add_item(discord.ui.TextDisplay("### 🔑 Leaderboard access"))
        self.leaderboard_access_select = _AckSelect(
            custom_id=ID_MIGRATION_LEADERBOARD_ACCESS,
            placeholder="🔑 Leaderboard access",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="🔑 Give me leaderboard access",
                    value=LEADERBOARD_ACCESS_ON_VALUE,
                    description="Unlocks #leaderboard and /leaderboard",
                    default=default_leaderboard_access,
                ),
                discord.SelectOption(
                    label="🚫 No leaderboard access",
                    value=LEADERBOARD_ACCESS_OFF_VALUE,
                    description="Keep the leaderboard hidden from me",
                    default=not default_leaderboard_access,
                ),
            ],
        )
        container.add_item(discord.ui.ActionRow(self.leaderboard_access_select))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "-# Please note you can defer for 7 days and we’ll revisit "
                "these settings then."
            )
        )
        container.add_item(discord.ui.Separator())

        self.save_button = MigrationSaveButton(cog)
        self.defer_button = MigrationDeferButton(cog)
        # Legacy custom_id kept registered (hidden) so any stale DMs in the
        # wild still respond when clicked instead of timing out.
        self.open_prefs_button = MigrationOpenPrefsButton(cog)
        container.add_item(
            discord.ui.ActionRow(self.save_button, self.defer_button)
        )
        self.add_item(container)
        # The legacy button is intentionally not added to a rendered ActionRow.
        # Putting it on the LayoutView via a flag won't show, but we still want
        # the persistent-view registration to know about it — so the cog adds
        # it to its persistent View at startup, separately. We just expose the
        # attribute here for back-compat.

    @property
    def chosen_leaderboard_visible(self) -> bool:
        values = self.leaderboard_select.values
        if not values:
            return self._default_leaderboard_visible
        return values[0] == LEADERBOARD_SHOW_VALUE

    @property
    def chosen_leaderboard_access(self) -> bool:
        values = self.leaderboard_access_select.values
        if not values:
            return self._default_leaderboard_access
        return values[0] == LEADERBOARD_ACCESS_ON_VALUE


def migration_prompt_card(
    *,
    name: str | None = None,
    default_leaderboard_visible: bool = True,
    default_leaderboard_access: bool = False,
    cog: Any | None = None,
) -> RenderedMessage:
    view = MigrationPromptView(
        name=name,
        default_leaderboard_visible=default_leaderboard_visible,
        default_leaderboard_access=default_leaderboard_access,
        cog=cog,
    )
    return RenderedMessage(view=view)


# ---------------------------------------------------------------------------
# Generic small DM error card (used when identity resolution fails, etc.)
# ---------------------------------------------------------------------------


class _OnboardingErrorLayout(discord.ui.LayoutView):
    def __init__(self, *, message: str, cog: Any | None) -> None:
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=COLOR_WARNING)
        container.add_item(discord.ui.TextDisplay("## Hmm, that didn’t work"))
        container.add_item(discord.ui.TextDisplay(message))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Tap **Enter Throne details** below to try again with your "
                "Throne username or link."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(OpenModalButton(cog)))
        self.add_item(container)


def onboarding_error_card(message: str, *, cog: Any | None = None) -> RenderedMessage:
    """Small recoverable error card that keeps the intro modal button live."""

    return RenderedMessage(view=_OnboardingErrorLayout(message=message, cog=cog))
