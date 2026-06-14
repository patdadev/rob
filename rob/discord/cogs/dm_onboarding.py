"""Runtime interactions for the DM-based Dom/me onboarding flow.

This cog is responsible for:

- handling all onboarding button + modal interactions
- opening / submitting the Throne input modal
- calling :class:`~rob.services.dm_onboarding_service.DMOnboardingService`
- editing the same DM message through each stage of the flow
- rotating the webhook URL when the user clicks "Doesn’t look to have worked!"
- handling the migration prompt (Save preferences / Defer for 7 days)
- being notified from the webhook handler when a Throne test webhook is
  received, and auto-advancing the DM to the preferences card

Interaction model
-----------------

Every interactive button used in the onboarding flow is a small bound
``discord.ui.Button`` subclass defined in :mod:`rob.ui.cards.dm_onboarding`
whose ``callback`` calls back into this cog by name. Cards are built with
``cog=self`` so the LIVE :class:`discord.ui.LayoutView` attached to the
DM message has buttons whose callbacks dispatch correctly — that's what
fixes the previous "This interaction failed" behaviour, which was caused
by sending plain custom-id-only buttons (whose default callback is a
no-op) inside the live LayoutView while a separate persistent ``View``
held the real callbacks. After a restart, the persistent view registered
in :meth:`DMOnboardingCog.register_persistent_views` acts as the
fallback route for the same custom IDs.

All onboarding behavior is gated to the test guild (see
:func:`rob.config.guilds.is_test_guild`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import logging

import discord
from discord.ext import commands

from rob.config.guilds import is_test_guild
from rob.discord.leaderboard_access import apply_leaderboard_access
from rob.services.dm_onboarding_service import (
    DMOnboardingService,
    OnboardingError,
)
from rob.ui.cards.dm_onboarding import (
    ID_MIGRATION_LEADERBOARD,
    ID_MIGRATION_LEADERBOARD_ACCESS,
    ID_PREFS_LEADERBOARD,
    ID_PREFS_LEADERBOARD_ACCESS,
    IdentityNoButton,
    IdentityYesButton,
    LEADERBOARD_ACCESS_ON_VALUE,
    LEADERBOARD_SHOW_VALUE,
    MigrationDeferButton,
    MigrationOpenPrefsButton,
    MigrationPromptView,
    MigrationSaveButton,
    OpenModalButton,
    PreferencesView,
    SavePrefsButton,
    WebhookRetryButton,
    build_intro_modal,
    identity_confirm_card,
    intro_card,
    migration_prompt_card,
    onboarding_error_card,
    preferences_card,
    success_card,
    webhook_setup_card,
)

if TYPE_CHECKING:
    from rob.discord.client import RobBot


log = logging.getLogger(__name__)


class _PersistentInteractionsView(discord.ui.View):
    """Plain :class:`discord.ui.View` registered at startup that owns every
    onboarding button custom_id. discord.py's ``ViewStore`` falls back to
    this view (keyed on ``custom_id`` only, no ``message_id``) when an
    interaction comes in for a DM whose live LayoutView is no longer in
    memory (typical after a bot restart).
    """

    def __init__(self, cog: "DMOnboardingCog") -> None:
        super().__init__(timeout=None)
        self.add_item(OpenModalButton(cog))
        self.add_item(IdentityYesButton(cog))
        self.add_item(IdentityNoButton(cog))
        self.add_item(WebhookRetryButton(cog))
        self.add_item(SavePrefsButton(cog))
        self.add_item(MigrationSaveButton(cog))
        self.add_item(MigrationDeferButton(cog))
        self.add_item(MigrationOpenPrefsButton(cog))


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class DMOnboardingCog(commands.Cog):
    """Runtime cog for the DM-based onboarding flow (test guild only)."""

    def __init__(self, bot: "RobBot") -> None:
        self.bot = bot

    # -- service helper ----------------------------------------------------

    @property
    def service(self) -> DMOnboardingService | None:
        return getattr(self.bot, "dm_onboarding_service", None)

    # -- view registration -------------------------------------------------

    def register_persistent_views(self) -> None:
        """Register the fallback persistent view so onboarding button custom
        IDs route to live callbacks across bot restarts."""

        try:
            self.bot.add_view(_PersistentInteractionsView(self))
        except Exception:
            log.warning(
                "Failed to register persistent DM onboarding view; "
                "post-restart interactions may not route.",
                exc_info=True,
            )
            return
        log.info("Registered persistent DM onboarding view")

    # -- onboarding entry points ------------------------------------------

    async def start_onboarding_dm(
        self,
        *,
        user: discord.abc.User,
        guild_id: int,
    ) -> tuple[bool, discord.Message | None, str | None]:
        """Start the DM-based onboarding flow for ``user``.

        Returns ``(ok, message, error_text)``. The caller is responsible for
        the ephemeral slash response.
        """

        service = self.service
        if service is None or not is_test_guild(guild_id):
            return False, None, "DM onboarding is not available here."

        log.info(
            "DM onboarding start user_id=%s guild_id=%s", user.id, guild_id
        )
        try:
            await service.start(guild_id=guild_id, discord_user_id=user.id)
        except OnboardingError as exc:
            log.warning(
                "DM onboarding start refused user_id=%s guild_id=%s: %s",
                user.id,
                guild_id,
                exc,
            )
            return False, None, str(exc)

        rendered = intro_card(
            name=getattr(user, "display_name", None) or user.name,
            cog=self,
        )
        try:
            message = await user.send(**rendered.send_kwargs())
        except discord.Forbidden:
            log.warning(
                "DM onboarding intro could not be sent (forbidden) user_id=%s guild_id=%s",
                user.id,
                guild_id,
            )
            return False, None, "Rob couldn’t DM you. Please allow DMs from this server and try again."
        except discord.HTTPException as exc:
            log.exception(
                "DM onboarding intro send failed user_id=%s guild_id=%s: %s",
                user.id,
                guild_id,
                exc,
            )
            return False, None, "Rob couldn’t send the setup DM right now."

        await self._persist_dm_message(
            guild_id=guild_id,
            discord_user_id=user.id,
            message=message,
        )
        return True, message, None

    async def send_migration_prompt(
        self,
        *,
        user: discord.abc.User,
        guild_id: int,
        default_leaderboard_visible: bool = True,
    ) -> discord.Message | None:
        """Send the migration prompt DM to an already-registered Dom/me in
        the test guild. Returns the message (or ``None`` on failure)."""

        if not is_test_guild(guild_id):
            return None
        rendered = migration_prompt_card(
            name=getattr(user, "display_name", None) or user.name,
            default_leaderboard_visible=default_leaderboard_visible,
            cog=self,
        )
        try:
            return await user.send(**rendered.send_kwargs())
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.warning(
                "Migration prompt DM failed user_id=%s guild_id=%s: %s",
                user.id,
                guild_id,
                exc,
            )
            return None

    # -- internal: persist + fetch the in-progress DM message --------------

    async def _persist_dm_message(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        message: discord.Message,
    ) -> None:
        repo = getattr(self.bot, "domme_onboarding_repo", None)
        if repo is None:
            return
        try:
            await repo.set_dm_message(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                dm_channel_id=int(message.channel.id),
                dm_message_id=int(message.id),
            )
        except Exception:
            log.exception(
                "Failed to persist DM onboarding message ids user_id=%s guild_id=%s",
                discord_user_id,
                guild_id,
            )

    async def _resolve_guild_id_for_user(self, user_id: int) -> int | None:
        """Look up the guild an in-progress onboarding belongs to.

        DM interactions have no ``interaction.guild`` set, so the cog can't
        otherwise tell which guild the flow was started from. The flow is
        test-guild only, so we look up the row by ``TEST_GUILD_ID``.
        """

        repo = getattr(self.bot, "domme_onboarding_repo", None)
        if repo is None:
            return None
        from rob.config.guilds import TEST_GUILD_ID

        try:
            state = await repo.get(
                guild_id=TEST_GUILD_ID,
                discord_user_id=user_id,
            )
        except Exception:
            log.exception("Onboarding state lookup failed user_id=%s", user_id)
            return None
        if state is None:
            return None
        return int(state.guild_id)

    async def _edit_stored_dm(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        rendered: Any,
    ) -> bool:
        """Edit the stored DM message in place; returns ``True`` on success."""

        repo = getattr(self.bot, "domme_onboarding_repo", None)
        if repo is None:
            return False
        try:
            state = await repo.get(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
            )
        except Exception:
            log.exception(
                "Onboarding state lookup failed during edit user_id=%s guild_id=%s",
                discord_user_id,
                guild_id,
            )
            return False
        if state is None or state.dm_channel_id is None or state.dm_message_id is None:
            log.warning(
                "No stored DM message for onboarding user_id=%s guild_id=%s",
                discord_user_id,
                guild_id,
            )
            return False

        try:
            user = self.bot.get_user(discord_user_id) or await self.bot.fetch_user(
                discord_user_id
            )
            dm_channel = user.dm_channel or await user.create_dm()
            message = dm_channel.get_partial_message(int(state.dm_message_id))
            await message.edit(**rendered.edit_kwargs())
            return True
        except discord.NotFound:
            log.warning(
                "Stored onboarding DM is gone user_id=%s guild_id=%s message_id=%s",
                discord_user_id,
                guild_id,
                state.dm_message_id,
            )
            return False
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.warning(
                "Could not edit stored onboarding DM user_id=%s guild_id=%s: %s",
                discord_user_id,
                guild_id,
                exc,
            )
            return False

    # -- button handlers --------------------------------------------------

    async def handle_open_modal(self, interaction: discord.Interaction) -> None:
        log.info(
            "handle_open_modal user_id=%s guild_id=%s channel_id=%s",
            interaction.user.id,
            interaction.guild_id,
            getattr(interaction, "channel_id", None),
        )
        guild_id = interaction.guild_id or await self._resolve_guild_id_for_user(
            interaction.user.id
        )
        if guild_id is None or not is_test_guild(guild_id):
            log.warning(
                "Onboarding open_modal rejected (no guild or wrong guild) "
                "user_id=%s guild_id=%s",
                interaction.user.id,
                guild_id,
            )
            await interaction.response.send_message(
                "This setup isn't available right now.", ephemeral=True
            )
            return
        try:
            await interaction.response.send_modal(
                build_intro_modal(cog=self, guild_id=int(guild_id))
            )
        except discord.HTTPException:
            log.exception(
                "Failed to open Throne input modal user_id=%s guild_id=%s",
                interaction.user.id,
                guild_id,
            )

    async def handle_modal_submit(
        self,
        interaction: discord.Interaction,
        *,
        guild_id: int,
        throne_input: str,
    ) -> None:
        log.info(
            "handle_modal_submit user_id=%s guild_id=%s",
            interaction.user.id,
            guild_id,
        )
        service = self.service
        if service is None or not is_test_guild(guild_id):
            await interaction.response.send_message(
                "This setup isn't available right now.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            identity = await service.submit_throne_input(
                guild_id=guild_id,
                discord_user_id=interaction.user.id,
                throne_input=throne_input,
            )
        except OnboardingError as exc:
            log.warning(
                "Throne resolution failed user_id=%s guild_id=%s: %s",
                interaction.user.id,
                guild_id,
                exc,
            )
            rendered = onboarding_error_card(str(exc), cog=self)
            edited = await self._edit_stored_dm(
                guild_id=guild_id,
                discord_user_id=interaction.user.id,
                rendered=rendered,
            )
            if not edited:
                await interaction.followup.send(str(exc), ephemeral=True)
            else:
                await interaction.followup.send(
                    "Couldn’t resolve that — check your DM and try again.",
                    ephemeral=True,
                )
            return

        rendered = identity_confirm_card(
            throne_handle=identity.throne_handle,
            throne_display_name=identity.throne_display_name,
            cog=self,
        )
        ok = await self._edit_stored_dm(
            guild_id=guild_id,
            discord_user_id=interaction.user.id,
            rendered=rendered,
        )
        if not ok:
            try:
                message = await interaction.user.send(**rendered.send_kwargs())
                await self._persist_dm_message(
                    guild_id=guild_id,
                    discord_user_id=interaction.user.id,
                    message=message,
                )
            except (discord.Forbidden, discord.HTTPException):
                log.exception(
                    "Fallback DM send after modal submit failed "
                    "user_id=%s guild_id=%s",
                    interaction.user.id,
                    guild_id,
                )
                await interaction.followup.send(
                    "Rob couldn’t update your DM. Please re-run /register domme.",
                    ephemeral=True,
                )
                return
        await interaction.followup.send(
            "Got it — check your DMs to confirm.", ephemeral=True
        )

    async def handle_identity_yes(self, interaction: discord.Interaction) -> None:
        log.info(
            "handle_identity_yes user_id=%s", interaction.user.id
        )
        guild_id = await self._resolve_guild_id_for_user(interaction.user.id)
        service = self.service
        if guild_id is None or service is None or not is_test_guild(guild_id):
            await interaction.response.send_message(
                "This setup isn't available right now.", ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            webhook_url = await service.confirm_identity(
                guild_id=guild_id,
                discord_user_id=interaction.user.id,
            )
        except OnboardingError as exc:
            log.warning(
                "confirm_identity failed user_id=%s guild_id=%s: %s",
                interaction.user.id,
                guild_id,
                exc,
            )
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except ValueError as exc:
            log.warning(
                "confirm_identity ValueError user_id=%s guild_id=%s: %s",
                interaction.user.id,
                guild_id,
                exc,
            )
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        if not webhook_url:
            log.error(
                "No webhook URL generated user_id=%s guild_id=%s",
                interaction.user.id,
                guild_id,
            )
            await interaction.followup.send(
                "Rob couldn’t generate your webhook URL. Ask staff to verify "
                "THRONE_WEBHOOK_BASE_URL on the bot server.",
                ephemeral=True,
            )
            return

        rendered = webhook_setup_card(webhook_url=webhook_url, cog=self)
        await self._edit_or_resend(
            interaction=interaction,
            guild_id=guild_id,
            rendered=rendered,
        )

    async def handle_identity_no(self, interaction: discord.Interaction) -> None:
        log.info("handle_identity_no user_id=%s", interaction.user.id)
        guild_id = await self._resolve_guild_id_for_user(interaction.user.id)
        service = self.service
        if guild_id is None or service is None or not is_test_guild(guild_id):
            await interaction.response.send_message(
                "This setup isn't available right now.", ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            await service.reject_identity(
                guild_id=guild_id,
                discord_user_id=interaction.user.id,
            )
        except OnboardingError as exc:
            log.warning(
                "reject_identity failed user_id=%s guild_id=%s: %s",
                interaction.user.id,
                guild_id,
                exc,
            )
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        name = getattr(interaction.user, "display_name", None) or interaction.user.name
        rendered = intro_card(name=name, cog=self)
        await self._edit_or_resend(
            interaction=interaction,
            guild_id=guild_id,
            rendered=rendered,
        )

    async def handle_webhook_retry(self, interaction: discord.Interaction) -> None:
        """User clicked "Doesn’t look to have worked!".

        We rotate the webhook URL (so any leaked/stale URL is invalidated)
        and re-render the same waiting card with the new URL.
        """

        log.info("handle_webhook_retry user_id=%s", interaction.user.id)
        guild_id = await self._resolve_guild_id_for_user(interaction.user.id)
        if guild_id is None or not is_test_guild(guild_id):
            await interaction.response.send_message(
                "This setup isn't available right now.", ephemeral=True
            )
            return

        await interaction.response.defer()
        webhook_url: str | None = None
        registration_service = getattr(self.bot, "registration_service", None)
        if registration_service is not None:
            try:
                result = await registration_service.reissue_domme_webhook(
                    guild_id=guild_id,
                    discord_user_id=interaction.user.id,
                )
                webhook_url = result.webhook_url
            except Exception:
                log.exception(
                    "Webhook reissue failed during onboarding retry "
                    "user_id=%s guild_id=%s",
                    interaction.user.id,
                    guild_id,
                )

        if not webhook_url:
            dommes = getattr(self.bot, "dommes_repo", None)
            if dommes is not None and registration_service is not None:
                try:
                    domme = await dommes.get_by_user_id(
                        guild_id, interaction.user.id
                    )
                    if (
                        domme is not None
                        and domme.webhook_secret
                        and domme.throne_creator_id
                    ):
                        webhook_url = registration_service.build_webhook_url(
                            creator_id=domme.throne_creator_id,
                            webhook_secret=domme.webhook_secret,
                        )
                except Exception:
                    log.exception(
                        "Webhook URL rebuild failed user_id=%s guild_id=%s",
                        interaction.user.id,
                        guild_id,
                    )

        if not webhook_url:
            await interaction.followup.send(
                "Rob couldn’t refresh your webhook URL. Please ask staff.",
                ephemeral=True,
            )
            return

        rendered = webhook_setup_card(webhook_url=webhook_url, cog=self)
        await self._edit_or_resend(
            interaction=interaction,
            guild_id=guild_id,
            rendered=rendered,
        )

    async def handle_save_preferences(self, interaction: discord.Interaction) -> None:
        log.info("handle_save_preferences user_id=%s", interaction.user.id)
        guild_id = await self._resolve_guild_id_for_user(interaction.user.id)
        service = self.service
        if guild_id is None or service is None or not is_test_guild(guild_id):
            await interaction.response.send_message(
                "This setup isn't available right now.", ephemeral=True
            )
            return

        leaderboard_visible, leaderboard_access = _read_prefs_from_interaction(
            interaction
        )

        await interaction.response.defer()
        try:
            await service.save_preferences(
                guild_id=guild_id,
                discord_user_id=interaction.user.id,
                leaderboard_visible=leaderboard_visible,
            )
        except OnboardingError as exc:
            log.warning(
                "save_preferences failed user_id=%s guild_id=%s: %s",
                interaction.user.id,
                guild_id,
                exc,
            )
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await apply_leaderboard_access(
            self.bot,
            guild_id=guild_id,
            user_id=interaction.user.id,
            enabled=leaderboard_access,
        )

        rendered = success_card(
            leaderboard_visible=leaderboard_visible,
            leaderboard_access=leaderboard_access,
        )
        await self._edit_or_resend(
            interaction=interaction,
            guild_id=guild_id,
            rendered=rendered,
        )

    # -- migration handlers ------------------------------------------------

    async def handle_migration_save(self, interaction: discord.Interaction) -> None:
        log.info("handle_migration_save user_id=%s", interaction.user.id)
        guild_id = await self._resolve_guild_id_for_user(interaction.user.id)
        if guild_id is None:
            from rob.config.guilds import TEST_GUILD_ID

            guild_id = TEST_GUILD_ID
        if not is_test_guild(guild_id):
            await interaction.response.send_message(
                "This setup isn't available here.", ephemeral=True
            )
            return

        dommes = getattr(self.bot, "dommes_repo", None)
        if dommes is None:
            await interaction.response.send_message(
                "Preferences aren't available right now.", ephemeral=True
            )
            return

        leaderboard_visible, leaderboard_access = _read_prefs_from_interaction(
            interaction
        )
        await interaction.response.defer()
        try:
            await dommes.set_preferences(
                guild_id=guild_id,
                discord_user_id=interaction.user.id,
                leaderboard_visible=leaderboard_visible,
                clear_defer=True,
                confirm=True,
            )
        except Exception:
            log.exception(
                "Migration save_preferences failed user_id=%s guild_id=%s",
                interaction.user.id,
                guild_id,
            )
            await interaction.followup.send(
                "Rob couldn’t save those preferences.", ephemeral=True
            )
            return

        await apply_leaderboard_access(
            self.bot,
            guild_id=guild_id,
            user_id=interaction.user.id,
            enabled=leaderboard_access,
        )

        rendered = success_card(
            leaderboard_visible=leaderboard_visible,
            leaderboard_access=leaderboard_access,
        )
        try:
            if interaction.message is not None:
                await interaction.message.edit(**rendered.edit_kwargs())
            else:
                await interaction.followup.send(**rendered.send_kwargs())
        except (discord.NotFound, discord.HTTPException):
            log.exception(
                "Migration success card edit failed user_id=%s guild_id=%s",
                interaction.user.id,
                guild_id,
            )

    async def handle_migration_defer(self, interaction: discord.Interaction) -> None:
        log.info("handle_migration_defer user_id=%s", interaction.user.id)
        guild_id = await self._resolve_guild_id_for_user(interaction.user.id)
        if guild_id is None:
            from rob.config.guilds import TEST_GUILD_ID

            guild_id = TEST_GUILD_ID
        if not is_test_guild(guild_id):
            await interaction.response.send_message(
                "This setup isn't available here.", ephemeral=True
            )
            return

        service = self.service
        if service is None:
            await interaction.response.send_message(
                "Defer isn't available right now.", ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            await service.defer_migration(
                guild_id=guild_id,
                discord_user_id=interaction.user.id,
                days=7,
            )
        except OnboardingError as exc:
            log.warning(
                "defer_migration failed user_id=%s guild_id=%s: %s",
                interaction.user.id,
                guild_id,
                exc,
            )
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        try:
            await interaction.followup.send(
                "No worries — Rob will check back in with you in 7 days.",
                ephemeral=True,
            )
        except discord.HTTPException:
            log.exception(
                "Failed to follow up after defer_migration user_id=%s",
                interaction.user.id,
            )

    async def handle_migration_open_prefs(
        self, interaction: discord.Interaction
    ) -> None:
        """Legacy path for the deprecated Open Preferences button on stale
        migration DMs. Just re-renders the migration card so the user can
        proceed."""

        log.info(
            "handle_migration_open_prefs (legacy) user_id=%s", interaction.user.id
        )
        name = getattr(interaction.user, "display_name", None) or interaction.user.name
        rendered = migration_prompt_card(name=name, cog=self)
        try:
            await interaction.response.edit_message(**rendered.edit_kwargs())
        except discord.HTTPException:
            try:
                await interaction.response.send_message(
                    **rendered.send_kwargs(), ephemeral=True
                )
            except discord.HTTPException:
                log.exception("Could not re-send migration prompt.")

    # -- webhook auto-advance hook (called from bot ops endpoint) ----------

    async def on_throne_test_webhook_received(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> bool:
        """Auto-advance the onboarding DM to the preferences card when a
        Throne test webhook arrives. Returns ``True`` if the DM was edited.
        """

        log.info(
            "on_throne_test_webhook_received user_id=%s guild_id=%s",
            discord_user_id,
            guild_id,
        )
        service = self.service
        if service is None or not is_test_guild(guild_id):
            log.info(
                "Webhook auto-advance skipped (service=%s test_guild=%s) "
                "user_id=%s guild_id=%s",
                service is not None,
                is_test_guild(guild_id),
                discord_user_id,
                guild_id,
            )
            return False

        repo = getattr(self.bot, "domme_onboarding_repo", None)
        if repo is None:
            return False
        try:
            state = await repo.get(
                guild_id=guild_id, discord_user_id=discord_user_id
            )
        except Exception:
            log.exception(
                "Auto-advance lookup failed user_id=%s guild_id=%s",
                discord_user_id,
                guild_id,
            )
            return False
        if state is None or state.stage == "completed":
            log.info(
                "Webhook auto-advance no-op user_id=%s guild_id=%s state=%s",
                discord_user_id,
                guild_id,
                getattr(state, "stage", None),
            )
            return False
        try:
            await service.mark_webhook_received(
                guild_id=guild_id, discord_user_id=discord_user_id
            )
        except OnboardingError as exc:
            log.warning(
                "mark_webhook_received refused user_id=%s guild_id=%s: %s",
                discord_user_id,
                guild_id,
                exc,
            )
            return False

        rendered = preferences_card(cog=self)
        edited = await self._edit_stored_dm(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            rendered=rendered,
        )
        if edited:
            log.info(
                "Webhook auto-advance edited stored DM user_id=%s guild_id=%s",
                discord_user_id,
                guild_id,
            )
        else:
            log.warning(
                "Webhook auto-advance could not edit stored DM "
                "user_id=%s guild_id=%s",
                discord_user_id,
                guild_id,
            )
        return edited

    # -- internal: edit or resend the DM ----------------------------------

    async def _edit_or_resend(
        self,
        *,
        interaction: discord.Interaction,
        guild_id: int,
        rendered: Any,
    ) -> None:
        """Edit the stored DM in place; if that fails, edit the triggering
        DM or send a fresh DM and update the stored ids."""

        if await self._edit_stored_dm(
            guild_id=guild_id,
            discord_user_id=interaction.user.id,
            rendered=rendered,
        ):
            return

        try:
            if interaction.message is not None and isinstance(
                interaction.channel, discord.DMChannel
            ):
                await interaction.message.edit(**rendered.edit_kwargs())
                await self._persist_dm_message(
                    guild_id=guild_id,
                    discord_user_id=interaction.user.id,
                    message=interaction.message,
                )
                return
        except discord.HTTPException:
            log.exception(
                "Could not edit triggering DM message user_id=%s guild_id=%s",
                interaction.user.id,
                guild_id,
            )

        try:
            message = await interaction.user.send(**rendered.send_kwargs())
            await self._persist_dm_message(
                guild_id=guild_id,
                discord_user_id=interaction.user.id,
                message=message,
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.warning(
                "Fallback DM send failed user_id=%s guild_id=%s: %s",
                interaction.user.id,
                guild_id,
                exc,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_prefs_from_interaction(
    interaction: discord.Interaction,
) -> tuple[bool, bool]:
    """Pull current preference selections off the interaction.

    Reads from the live :class:`PreferencesView` / :class:`MigrationPromptView`
    if the button belongs to one, falling back to scanning the message's
    component data for select state. Returns
    ``(leaderboard_visible, leaderboard_access)``, defaulting to ``(True, False)``.
    """

    leaderboard_visible = True
    leaderboard_access = False

    view = getattr(interaction, "view", None)
    if isinstance(view, (PreferencesView, MigrationPromptView)):
        return (
            view.chosen_leaderboard_visible,
            view.chosen_leaderboard_access,
        )

    message = getattr(interaction, "message", None)
    if message is None:
        return leaderboard_visible, leaderboard_access

    def _match_select(item: Any) -> None:
        nonlocal leaderboard_visible, leaderboard_access
        custom_id = getattr(item, "custom_id", None)
        if custom_id in (ID_PREFS_LEADERBOARD, ID_MIGRATION_LEADERBOARD):
            values = getattr(item, "values", []) or []
            if values:
                leaderboard_visible = values[0] == LEADERBOARD_SHOW_VALUE
        elif custom_id in (
            ID_PREFS_LEADERBOARD_ACCESS,
            ID_MIGRATION_LEADERBOARD_ACCESS,
        ):
            values = getattr(item, "values", []) or []
            if values:
                leaderboard_access = values[0] == LEADERBOARD_ACCESS_ON_VALUE

    for row in getattr(message, "components", []) or []:
        for child in getattr(row, "children", []) or []:
            # Check this child directly (legacy: select as direct container child).
            _match_select(child)
            # Check one level deeper (current: select inside ActionRow inside container).
            for grandchild in getattr(child, "children", []) or []:
                _match_select(grandchild)
    return leaderboard_visible, leaderboard_access


async def setup(bot: "RobBot") -> None:
    cog = DMOnboardingCog(bot)
    await bot.add_cog(cog)
    cog.register_persistent_views()
