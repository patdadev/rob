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
ID_PREFS_NOTIFICATIONS = f"{ONBOARDING_PREFIX}prefs:notifications"
ID_PREFS_LEADERBOARD = f"{ONBOARDING_PREFIX}prefs:leaderboard"
ID_PREFS_SAVE = f"{ONBOARDING_PREFIX}prefs:save"

MIGRATION_PREFIX = "rob:dm_migration:"
ID_MIGRATION_OPEN_PREFS = f"{MIGRATION_PREFIX}open_prefs"
ID_MIGRATION_DEFER = f"{MIGRATION_PREFIX}defer_7d"
ID_MIGRATION_NOTIFICATIONS = f"{MIGRATION_PREFIX}notifications"
ID_MIGRATION_LEADERBOARD = f"{MIGRATION_PREFIX}leaderboard"
ID_MIGRATION_SAVE = f"{MIGRATION_PREFIX}save"

# Preference option values stored on each ``SelectOption``.
NOTIFY_ON_VALUE = "notify_on"
NOTIFY_OFF_VALUE = "notify_off"
LEADERBOARD_SHOW_VALUE = "leaderboard_show"
LEADERBOARD_HIDE_VALUE = "leaderboard_hide"


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
        container.add_item(discord.ui.TextDisplay(f"## Hey {display}, Rob here!"))
        container.add_item(
            discord.ui.TextDisplay(
                "Thanks for wanting to sign up to Throne tracking. Before we "
                "can start tracking your notifications, we need to do some "
                "initial setup first."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Firstly, what was your Throne username or link?"
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
        container.add_item(
            discord.ui.TextDisplay(
                "Thanks! Just to make sure I’ve got the right details does "
                "this look right?"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(f"**Throne Username:** {throne_handle}")
        )
        container.add_item(
            discord.ui.TextDisplay(f"**Name as appears on Throne:** {display}")
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
        container.add_item(
            discord.ui.TextDisplay(
                "## Awesome, now here comes the bit with the most steps."
            )
        )
        container.add_item(
            discord.ui.TextDisplay(
                "To help Rob get your sends the second they are sent, we "
                "need to setup “Webhooks” inside of Throne. Here’s how:"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "**1.** Open Throne\n"
                "**2.** Go to your webhook settings / integrations area\n"
                "**3.** Add Rob’s webhook URL (below)\n"
                "**4.** Save the settings\n"
                "**5.** Click Test Webhook in Throne"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("**Rob’s webhook URL:**"))
        container.add_item(discord.ui.TextDisplay(f"```\n{webhook_url}\n```"))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Once you’ve clicked “Test Webhook” come back here to see if "
                "Rob picked up your Test Send!"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay("**Status:** Nothing from Throne just yet…")
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
    """Stage 6: notification + leaderboard preferences via Components V2.

    Two selects live inside the container, with a Save button as the final
    action row inside the same container so it sits in the bottom-left of
    the card.
    """

    def __init__(
        self,
        *,
        default_notifications_enabled: bool = True,
        default_leaderboard_visible: bool = True,
        notifications_custom_id: str = ID_PREFS_NOTIFICATIONS,
        leaderboard_custom_id: str = ID_PREFS_LEADERBOARD,
        save_custom_id: str = ID_PREFS_SAVE,
        intro_lines: tuple[str, ...] = (
            "## And just like that, the hard bit is done.",
            "Now just tell Rob how you want things handled from here.",
        ),
        cog: Any | None = None,
    ) -> None:
        super().__init__(timeout=None)

        container = discord.ui.Container(accent_color=COLOR_INFO)
        for line in intro_lines:
            container.add_item(discord.ui.TextDisplay(line))
        container.add_item(discord.ui.Separator())

        # ---- Section 1: Notifications ----
        container.add_item(discord.ui.TextDisplay("### 📬 Send notifications"))
        container.add_item(
            discord.ui.TextDisplay(
                "How should Rob notify you when a send comes in?"
            )
        )
        self.notifications_select = _AckSelect(
            custom_id=notifications_custom_id,
            placeholder="📬 Send notifications",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="📬 DM me when a send comes in",
                    value=NOTIFY_ON_VALUE,
                    default=default_notifications_enabled,
                ),
                discord.SelectOption(
                    label="🔕 Do not DM me about sends",
                    value=NOTIFY_OFF_VALUE,
                    default=not default_notifications_enabled,
                ),
            ],
        )
        container.add_item(self.notifications_select)
        container.add_item(discord.ui.Separator())

        # ---- Section 2: Leaderboard ----
        container.add_item(discord.ui.TextDisplay("### 📊 Leaderboard visibility"))
        container.add_item(
            discord.ui.TextDisplay(
                "Should Rob show you on the server leaderboard?"
            )
        )
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
                    label="🔒 Keep me off the leaderboard",
                    value=LEADERBOARD_HIDE_VALUE,
                    default=not default_leaderboard_visible,
                ),
            ],
        )
        container.add_item(self.leaderboard_select)
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "-# You can always change these settings later with `/settings` "
                "in your DMs or in the server."
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
    def chosen_notifications_enabled(self) -> bool:
        values = self.notifications_select.values
        if not values:
            return True
        return values[0] == NOTIFY_ON_VALUE

    @property
    def chosen_leaderboard_visible(self) -> bool:
        values = self.leaderboard_select.values
        if not values:
            return True
        return values[0] == LEADERBOARD_SHOW_VALUE


def preferences_card(
    *,
    default_notifications_enabled: bool = True,
    default_leaderboard_visible: bool = True,
    cog: Any | None = None,
) -> RenderedMessage:
    view = PreferencesView(
        default_notifications_enabled=default_notifications_enabled,
        default_leaderboard_visible=default_leaderboard_visible,
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
        notifications_enabled: bool,
        leaderboard_visible: bool,
    ) -> None:
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=COLOR_SUCCESS)
        container.add_item(
            discord.ui.TextDisplay(
                "## And just like that, you’ve now got me tracking your "
                "throne sends!"
            )
        )
        container.add_item(
            discord.ui.TextDisplay(
                "Keep in mind I’ll always respect your wishes when it comes "
                "to being notified about a send or being shown on the "
                "leaderboard. And you can always change these settings in "
                "future by running `/settings` in these DM’s or in the "
                "server!"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "If something stops working or doesn’t appear to be working "
                "correctly, then report it via `/report`!"
            )
        )
        notify_line = (
            "📬 DM notifications on"
            if notifications_enabled
            else "🔕 DM notifications off"
        )
        lb_line = (
            "👑 Shown on the leaderboard"
            if leaderboard_visible
            else "🔒 Hidden from the leaderboard"
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(f"-# {notify_line}  •  {lb_line}")
        )
        self.add_item(container)


def success_card(
    *,
    notifications_enabled: bool = True,
    leaderboard_visible: bool = True,
) -> RenderedMessage:
    return RenderedMessage(
        view=_SuccessLayout(
            notifications_enabled=notifications_enabled,
            leaderboard_visible=leaderboard_visible,
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
        default_notifications_enabled: bool = True,
        default_leaderboard_visible: bool = True,
        cog: Any | None = None,
    ) -> None:
        super().__init__(timeout=None)
        display = (name or "there").strip() or "there"

        container = discord.ui.Container(accent_color=COLOR_INFO)
        container.add_item(discord.ui.TextDisplay(f"## Hey {display}, Rob here!"))
        container.add_item(
            discord.ui.TextDisplay(
                "As announced by Pat earlier this week, I’ll be changing how "
                "I send you notifications about sends made to you through "
                "automatic tracking."
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                "Rob can now DM you directly when a send comes in, and you "
                "can also choose whether you appear on the leaderboard or "
                "keep things private."
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(discord.ui.TextDisplay("### 📬 Send notifications"))
        self.notifications_select = _AckSelect(
            custom_id=ID_MIGRATION_NOTIFICATIONS,
            placeholder="📬 Send notifications",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="📬 DM me when a send comes in",
                    value=NOTIFY_ON_VALUE,
                    default=default_notifications_enabled,
                ),
                discord.SelectOption(
                    label="🔕 Do not DM me about sends",
                    value=NOTIFY_OFF_VALUE,
                    default=not default_notifications_enabled,
                ),
            ],
        )
        container.add_item(self.notifications_select)
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
        container.add_item(self.leaderboard_select)
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
    def chosen_notifications_enabled(self) -> bool:
        values = self.notifications_select.values
        if not values:
            return True
        return values[0] == NOTIFY_ON_VALUE

    @property
    def chosen_leaderboard_visible(self) -> bool:
        values = self.leaderboard_select.values
        if not values:
            return True
        return values[0] == LEADERBOARD_SHOW_VALUE


def migration_prompt_card(
    *,
    name: str | None = None,
    default_notifications_enabled: bool = True,
    default_leaderboard_visible: bool = True,
    cog: Any | None = None,
) -> RenderedMessage:
    view = MigrationPromptView(
        name=name,
        default_notifications_enabled=default_notifications_enabled,
        default_leaderboard_visible=default_leaderboard_visible,
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
