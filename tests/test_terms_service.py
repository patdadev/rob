from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from rob.config.guilds import MAIN_GUILD_ID, TEST_GUILD_ID
from rob.database.repositories.terms import (
    STATUS_ACCEPTED,
    STATUS_DECLINED,
    STATUS_PENDING,
)
from rob.services.terms_service import (
    FALLBACK_PRIVACY_URL,
    FALLBACK_TERMS_URL,
    TermsError,
    TermsService,
)


class _FakeTermsRepo:
    def __init__(self, state=None):
        self.state = state
        self.pending_calls: list[dict] = []
        self.accept_calls: list[int] = []
        self.decline_calls: list[int] = []

    async def get(self, *, discord_user_id):
        return self.state

    async def upsert_pending(self, **kwargs):
        self.pending_calls.append(kwargs)
        self.state = SimpleNamespace(
            discord_user_id=kwargs["discord_user_id"],
            status=STATUS_PENDING,
            terms_version=kwargs["terms_version"],
            dm_channel_id=kwargs["dm_channel_id"],
            dm_message_id=kwargs["dm_message_id"],
        )
        return self.state

    async def mark_accepted(self, *, discord_user_id):
        self.accept_calls.append(discord_user_id)
        if self.state is None:
            return None
        state = dict(self.state.__dict__)
        state["status"] = STATUS_ACCEPTED
        self.state = SimpleNamespace(**state)
        return self.state

    async def mark_declined(self, *, discord_user_id):
        self.decline_calls.append(discord_user_id)
        if self.state is None:
            return None
        state = dict(self.state.__dict__)
        state["status"] = STATUS_DECLINED
        self.state = SimpleNamespace(**state)
        return self.state


def _service(*, repo=None, version="2026-06-05", terms_url=None, privacy_url=None, owner_user_id=None):
    return TermsService(
        terms=repo or _FakeTermsRepo(),
        terms_version=version,
        terms_url=terms_url,
        privacy_url=privacy_url,
        owner_user_id=owner_user_id,
    )


def test_terms_service_enabled_only_for_test_guild():
    assert TermsService.is_enabled_for(TEST_GUILD_ID) is True
    assert TermsService.is_enabled_for(MAIN_GUILD_ID) is False
    assert TermsService.is_enabled_for(None) is False


def test_terms_service_uses_fallback_urls_and_owner_text():
    service = _service()
    assert service.terms_url == FALLBACK_TERMS_URL
    assert service.privacy_url == FALLBACK_PRIVACY_URL
    assert service.owner_mention == "the bot owner"


def test_terms_service_owner_mention_uses_configured_id():
    service = _service(owner_user_id=42)
    assert service.owner_mention == "<@42>"


def test_gate_status_accepts_current_version():
    repo = _FakeTermsRepo(
        SimpleNamespace(status=STATUS_ACCEPTED, terms_version="2026-06-05")
    )
    service = _service(repo=repo)
    assert asyncio.run(service.gate_status_for_user(1)) == "accepted"


def test_gate_status_keeps_current_pending_state():
    repo = _FakeTermsRepo(
        SimpleNamespace(status=STATUS_PENDING, terms_version="2026-06-05")
    )
    service = _service(repo=repo)
    assert asyncio.run(service.gate_status_for_user(1)) == "pending"


def test_gate_status_reprompts_for_declined_or_old_version():
    declined_repo = _FakeTermsRepo(
        SimpleNamespace(status=STATUS_DECLINED, terms_version="2026-06-05")
    )
    old_repo = _FakeTermsRepo(
        SimpleNamespace(status=STATUS_ACCEPTED, terms_version="2026-01-01")
    )
    assert asyncio.run(_service(repo=declined_repo).gate_status_for_user(1)) == "prompt"
    assert asyncio.run(_service(repo=old_repo).gate_status_for_user(1)) == "prompt"


def test_record_prompt_uses_current_version_and_message_ids():
    repo = _FakeTermsRepo()
    service = _service(repo=repo)
    asyncio.run(
        service.record_prompt(
            discord_user_id=7,
            dm_channel_id=101,
            dm_message_id=202,
        )
    )
    assert repo.pending_calls == [
        {
            "discord_user_id": 7,
            "terms_version": "2026-06-05",
            "dm_channel_id": 101,
            "dm_message_id": 202,
        }
    ]


def test_accept_requires_existing_terms_state():
    service = _service(repo=_FakeTermsRepo())
    with pytest.raises(TermsError):
        asyncio.run(service.accept(discord_user_id=9))


def test_decline_requires_existing_terms_state():
    service = _service(repo=_FakeTermsRepo())
    with pytest.raises(TermsError):
        asyncio.run(service.decline(discord_user_id=9))


def test_accept_and_decline_delegate_to_repository():
    repo = _FakeTermsRepo(
        SimpleNamespace(
            discord_user_id=9,
            status=STATUS_PENDING,
            terms_version="2026-06-05",
            dm_channel_id=11,
            dm_message_id=12,
        )
    )
    service = _service(repo=repo)

    accepted = asyncio.run(service.accept(discord_user_id=9))
    declined = asyncio.run(service.decline(discord_user_id=9))

    assert accepted.status == STATUS_ACCEPTED
    assert declined.status == STATUS_DECLINED
    assert repo.accept_calls == [9]
    assert repo.decline_calls == [9]
