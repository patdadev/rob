from __future__ import annotations

import logging
import os

import discord
from discord.ext import commands

from rob.config.settings import BotSettings
from rob.database.connection import Database
from rob.database.repositories import (
    BlacklistRepository,
    BotSettingsRepository,
    CountingRepository,
    DommesRepository,
    LeaderboardsRepository,
    SendChangeRequestsRepository,
    SendsRepository,
    SubsRepository,
    TermsRepository,
    VibSettingsRepository,
)
from rob.database.repositories.domme_onboarding import DommeOnboardingRepository
from rob.discord.cogs.admin_tools import AdminToolsCog
from rob.discord.cogs.activity_tracker import ActivityTrackerCog
from rob.discord.cogs.counting import CountingCog
from rob.discord.cogs.dm_onboarding import DMOnboardingCog
from rob.discord.cogs.inactivity import InactivityCog
from rob.discord.cogs.leaderboards import LeaderboardsCog
from rob.discord.cogs.registration import RegistrationCog
from rob.discord.cogs.reports import ReportsCog
from rob.discord.cogs.sends import SendsCog
from rob.discord.cogs.settings import SettingsCog
from rob.discord.cogs.terms import TermsCog
from rob.discord.cogs.warn_relay import WarnRelayCog
from rob.services.counting_service import CountingService
from rob.services.bot_ops_server import BotOpsServer
from rob.services.dm_onboarding_service import DMOnboardingService
from rob.services.inactivity_service import InactivityService
from rob.services.leaderboard_service import LeaderboardService
from rob.services.maintenance_service import MaintenanceService
from rob.services.registration_service import RegistrationService
from rob.services.send_change_request_service import SendChangeRequestService
from rob.services.send_queue_service import SendQueueService
from rob.services.send_service import SendService
from rob.services.throne_service import ThroneService
from rob.services.terms_service import TermsService
from rob.ui.cards.maintenance import rob_offline_embed

log = logging.getLogger(__name__)


class RobBot(commands.Bot):
    def __init__(self, settings: BotSettings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=True,
                everyone=False,
            ),
        )
        self.settings = settings
        self.database = Database(settings.database_url)

    async def setup_hook(self) -> None:
        await self.database.connect()

        self.vib_settings_repo = VibSettingsRepository(self.database)
        self.guild_settings_repo = self.vib_settings_repo
        self.bot_settings_repo = BotSettingsRepository(self.database)
        self.bot_state_repo = self.bot_settings_repo
        self.blacklist_repo = BlacklistRepository(self.database)
        self.dommes_repo = DommesRepository(self.database)
        self.subs_repo = SubsRepository(self.database)
        self.sends_repo = SendsRepository(self.database)
        self.leaderboards_repo = LeaderboardsRepository(self.database)
        self.counting_repo = CountingRepository(self.database)
        self.send_change_requests_repo = SendChangeRequestsRepository(self.database)
        self.domme_onboarding_repo = DommeOnboardingRepository(self.database)
        self.terms_repo = TermsRepository(self.database)

        self.throne_service = ThroneService()
        self.maintenance_service = MaintenanceService(self.bot_settings_repo)
        self.leaderboard_service = LeaderboardService(
            bot=self,
            guild_settings=self.vib_settings_repo,
            leaderboards=self.leaderboards_repo,
            bot_state=self.bot_settings_repo,
            maintenance=self.maintenance_service,
            dommes=self.dommes_repo,
            leaderboard_limit=self.settings.leaderboard_limit,
            include_test_sends=self.settings.throne_parse_test_sends_as_real_sends,
            test_gifter_usernames=self.settings.throne_test_gifter_usernames,
            owner_test_user_id=self.settings.throne_test_send_leaderboard_owner_user_id,
        )
        self.counting_service = CountingService(
            bot=self,
            counting=self.counting_repo,
            guild_settings=self.vib_settings_repo,
            dommes=self.dommes_repo,
            bot_settings=self.bot_settings_repo,
            subs=self.subs_repo,
            parse_test_sends_as_real_sends=self.settings.throne_parse_test_sends_as_real_sends,
            test_gifter_usernames=self.settings.throne_test_gifter_usernames,
        )
        self.inactivity_service = InactivityService(
            bot_state=self.bot_settings_repo,
            guild_settings=self.vib_settings_repo,
            enabled_default=self.settings.inactivity_enabled_default,
            new_member_grace_days=self.settings.inactivity_new_member_grace_days,
            assignment_grace_days=self.settings.inactivity_assignment_grace_days,
            bootstrap_grace_days=self.settings.inactivity_bootstrap_grace_days,
            final_notice_days=self.settings.inactivity_final_notice_days,
            notice_channel_id=self.settings.inactivity_notice_channel_id,
            maintenance=self.maintenance_service,
        )
        self.registration_service = RegistrationService(
            guild_settings=self.vib_settings_repo,
            dommes=self.dommes_repo,
            subs=self.subs_repo,
            blacklist=self.blacklist_repo,
            throne=self.throne_service,
            webhook_base_url=os.getenv("THRONE_WEBHOOK_BASE_URL") or None,
        )
        self.dm_onboarding_service = DMOnboardingService(
            onboarding=self.domme_onboarding_repo,
            dommes=self.dommes_repo,
            throne=self.throne_service,
            registration=self.registration_service,
        )
        self.terms_service = TermsService(
            terms=self.terms_repo,
            terms_version=self.settings.rob_terms_version,
            terms_url=self.settings.rob_terms_url,
            privacy_url=self.settings.rob_privacy_url,
            owner_user_id=self.settings.rob_terms_owner_user_id,
        )
        self.send_service = SendService(
            sends=self.sends_repo,
            subs=self.subs_repo,
            maintenance=self.maintenance_service,
            leaderboards=self.leaderboards_repo,
            throne=self.throne_service,
            throne_test_gifter_usernames=self.settings.throne_test_gifter_usernames,
            include_test_sends=self.settings.throne_parse_test_sends_as_real_sends,
            test_gifter_usernames=self.settings.throne_test_gifter_usernames,
            owner_test_user_id=self.settings.throne_test_send_leaderboard_owner_user_id,
        )
        self.send_queue_service = SendQueueService(
            bot=self,
            sends=self.sends_repo,
            guild_settings=self.vib_settings_repo,
            maintenance=self.maintenance_service,
            leaderboard_service=self.leaderboard_service,
            counting_service=self.counting_service,
            leaderboards=self.leaderboards_repo,
            dommes=self.dommes_repo,
            include_test_sends=self.settings.throne_parse_test_sends_as_real_sends,
            owner_test_user_id=self.settings.throne_test_send_leaderboard_owner_user_id,
            test_gifter_usernames=self.settings.throne_test_gifter_usernames,
            poll_interval_seconds=self.settings.send_queue_loop_seconds,
        )
        self.send_change_request_service = SendChangeRequestService(
            bot=self,
            requests=self.send_change_requests_repo,
            dommes=self.dommes_repo,
            sends=self.sends_repo,
            send_service=self.send_service,
            send_queue_service=self.send_queue_service,
            leaderboard_service=self.leaderboard_service,
        )
        self.bot_ops_server = BotOpsServer(
            bot=self,
            host=self.settings.rob_ops_host,
            port=self.settings.rob_ops_port,
            secret=self.settings.rob_ops_secret,
        )

        await self.add_cog(RegistrationCog(self))
        await self.add_cog(DMOnboardingCog(self))
        await self.add_cog(TermsCog(self))
        await self.add_cog(SendsCog(self))
        await self.add_cog(LeaderboardsCog(self))
        await self.add_cog(ActivityTrackerCog(self))
        await self.add_cog(CountingCog(self))
        await self.add_cog(ReportsCog(self))
        await self.add_cog(InactivityCog(self))
        await self.add_cog(WarnRelayCog(self))
        await self.add_cog(AdminToolsCog(self))
        await self.add_cog(SettingsCog(self))

        self.tree.interaction_check = self._global_interaction_check
        await self.send_change_request_service.rebind_pending_views()

        dm_onboarding_cog = self.get_cog("DMOnboardingCog")
        if dm_onboarding_cog is not None:
            dm_onboarding_cog.register_persistent_views()
        terms_cog = self.get_cog("TermsCog")
        if terms_cog is not None:
            terms_cog.register_persistent_views()

        guild_ids = await self.vib_settings_repo.list_guild_ids()
        await self._sync_application_commands(guild_ids)

        await self.counting_service.start()
        await self.send_queue_service.start()
        await self.bot_ops_server.start()

    async def _global_interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user is None:
            return True
        if await self.blacklist_repo.contains(interaction.user.id):
            await interaction.response.send_message(
                "Rob can't help with that account right now.",
                ephemeral=True,
            )
            return False

        if interaction.guild is not None and await self.maintenance_service.is_rob_offline_for_guild(
            interaction.guild.id
        ):
            command_name = getattr(interaction.command, "qualified_name", "")
            if command_name != "add":
                await interaction.response.send_message(
                    **rob_offline_embed().send_kwargs(),
                    ephemeral=True,
                )
                return False

        terms_cog = self.get_cog("TermsCog")
        if terms_cog is None:
            return True

        if interaction.guild is None:
            return True

        if terms_cog.is_terms_interaction(interaction):
            return True

        return await terms_cog.ensure_terms_acceptance(interaction)

    async def _global_blacklist_interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        return await self._global_interaction_check(interaction)

    async def _sync_application_commands(self, guild_ids: list[int]) -> None:
        if len(guild_ids) == 1:
            guild = discord.Object(id=guild_ids[0])
            self.tree.clear_commands(guild=guild)
            cleared = await self.tree.sync(guild=guild)
            log.info(
                "Cleared %s stale guild command(s) before syncing global commands.",
                len(cleared),
            )

        synced = await self.tree.sync()
        log.info("Synced %s global command(s).", len(synced))

    async def on_ready(self) -> None:
        log.info("%s is online as %s.", self.settings.bot_name, self.user)

    async def close(self) -> None:
        if hasattr(self, "bot_ops_server"):
            await self.bot_ops_server.stop()
        if hasattr(self, "send_queue_service"):
            await self.send_queue_service.stop()
        if hasattr(self, "counting_service"):
            await self.counting_service.stop()
        if hasattr(self, "throne_service"):
            await self.throne_service.close()
        await self.database.close()
        await super().close()
