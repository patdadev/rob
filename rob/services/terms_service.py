from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rob.config.guilds import is_test_guild
from rob.database.repositories.terms import (
    STATUS_ACCEPTED,
    STATUS_PENDING,
    TermsRepository,
)

FALLBACK_TERMS_URL = "https://example.com/rob/terms"
FALLBACK_PRIVACY_URL = "https://example.com/rob/privacy"

GateStatus = Literal["accepted", "pending", "prompt"]


class TermsError(Exception):
    """Raised when the Terms acceptance flow cannot proceed."""


@dataclass(frozen=True)
class TermsLinks:
    terms_url: str
    privacy_url: str


class TermsService:
    def __init__(
        self,
        *,
        terms: TermsRepository,
        terms_version: str,
        terms_url: str | None,
        privacy_url: str | None,
        owner_user_id: int | None,
    ) -> None:
        self.terms = terms
        self.terms_version = terms_version
        self.terms_url = terms_url or FALLBACK_TERMS_URL
        self.privacy_url = privacy_url or FALLBACK_PRIVACY_URL
        self.owner_user_id = owner_user_id

    @staticmethod
    def is_enabled_for(guild_id: int | None) -> bool:
        return is_test_guild(guild_id)

    @property
    def links(self) -> TermsLinks:
        return TermsLinks(
            terms_url=self.terms_url,
            privacy_url=self.privacy_url,
        )

    @property
    def owner_mention(self) -> str:
        if self.owner_user_id is None:
            return "the bot owner"
        return f"<@{self.owner_user_id}>"

    async def get_state(self, discord_user_id: int):
        return await self.terms.get(discord_user_id=discord_user_id)

    async def gate_status_for_user(self, discord_user_id: int) -> GateStatus:
        state = await self.get_state(discord_user_id)
        if (
            state is not None
            and state.status == STATUS_ACCEPTED
            and state.terms_version == self.terms_version
        ):
            return "accepted"
        if (
            state is not None
            and state.status == STATUS_PENDING
            and state.terms_version == self.terms_version
        ):
            return "pending"
        return "prompt"

    async def record_prompt(
        self,
        *,
        discord_user_id: int,
        dm_channel_id: int,
        dm_message_id: int,
    ):
        return await self.terms.upsert_pending(
            discord_user_id=discord_user_id,
            terms_version=self.terms_version,
            dm_channel_id=dm_channel_id,
            dm_message_id=dm_message_id,
        )

    async def accept(self, *, discord_user_id: int):
        state = await self.get_state(discord_user_id)
        if state is None:
            raise TermsError("These Terms are not active right now.")
        updated = await self.terms.mark_accepted(discord_user_id=discord_user_id)
        if updated is None:
            raise TermsError("These Terms are not active right now.")
        return updated

    async def decline(self, *, discord_user_id: int):
        state = await self.get_state(discord_user_id)
        if state is None:
            raise TermsError("These Terms are not active right now.")
        updated = await self.terms.mark_declined(discord_user_id=discord_user_id)
        if updated is None:
            raise TermsError("These Terms are not active right now.")
        return updated
