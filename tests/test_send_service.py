from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from rob.database.repositories.models import NewSend, SendRecord, ThroneCreator
from rob.services.send_service import SendService
from rob.throne.payloads import ThroneSendPayload


@dataclass
class _FakeMaintenance:
    enabled: bool = False

    async def is_enabled(self) -> bool:
        return self.enabled


class _FakeSendsRepo:
    def __init__(self) -> None:
        self.inserted: NewSend | None = None

    async def insert(self, send: NewSend) -> SendRecord:
        self.inserted = send
        now = datetime.now(timezone.utc)
        return SendRecord(
            1,
            send.guild_id,
            send.domme_id,
            send.domme_user_id,
            send.sub_id,
            send.sub_user_id,
            send.sub_name,
            send.amount_cents,
            send.currency,
            send.method,
            send.source,
            send.item_name,
            send.item_image_url,
            send.external_id,
            send.event_id,
            send.fallback_event_hash,
            send.is_private,
            send.seeded,
            send.sent_at,
            now,
            send.discord_post_status,
            None,
            None,
            None,
            now,
            send.is_test_send,
        )


class _FakeSubsRepo:
    def __init__(self, *, returned_sub=None):
        self.returned_sub = returned_sub
        self.lookup_calls: list[tuple[int, str]] = []

    async def get_by_send_name(self, guild_id: int, send_name: str):
        self.lookup_calls.append((guild_id, send_name))
        return self.returned_sub

    async def get_by_name(self, guild_id: int, send_name: str):
        return await self.get_by_send_name(guild_id, send_name)


def _creator() -> ThroneCreator:
    now = datetime.now(timezone.utc)
    return ThroneCreator(
        1,
        1,
        1,
        10,
        "pat",
        "creator-id",
        False,
        "webhook",
        None,
        None,
        None,
        False,
        None,
        None,
        None,
        None,
        now,
        now,
    )


def _payload(gifter_username: str | None) -> ThroneSendPayload:
    now = datetime.now(timezone.utc)
    return ThroneSendPayload(
        event_id="evt_1",
        event_type="gift_purchased",
        order_id="order_1",
        gifter_username=gifter_username,
        item_name="Flowers",
        item_image_url="https://example.com/item.png",
        amount_cents=1099,
        currency="USD",
        is_private=False,
        purchased_at=now,
        fallback_event_hash="hash_1",
    )


def test_known_test_sender_is_stored_as_test_send():
    sends = _FakeSendsRepo()
    subs = _FakeSubsRepo()
    service = SendService(
        sends=sends,
        subs=subs,
        maintenance=_FakeMaintenance(),
        throne_test_gifter_usernames=("marie_123",),
    )

    asyncio.run(service.record_throne_send(creator=_creator(), payload=_payload("marie_123")))

    assert sends.inserted is not None
    assert sends.inserted.is_test_send is True
    assert sends.inserted.item_image_url == "https://example.com/item.png"


def test_real_sender_is_not_stored_as_test_send():
    sends = _FakeSendsRepo()
    subs = _FakeSubsRepo()
    service = SendService(
        sends=sends,
        subs=subs,
        maintenance=_FakeMaintenance(),
        throne_test_gifter_usernames=("marie_123",),
    )

    asyncio.run(service.record_throne_send(creator=_creator(), payload=_payload("real_sender")))

    assert sends.inserted is not None
    assert sends.inserted.is_test_send is False


def test_sub_alias_lookup_sets_sub_user_id():
    sends = _FakeSendsRepo()
    sub = type("Sub", (), {"id": 7, "discord_user_id": 99, "send_name": "alias"})
    subs = _FakeSubsRepo(returned_sub=sub)
    service = SendService(
        sends=sends,
        subs=subs,
        maintenance=_FakeMaintenance(),
        throne_test_gifter_usernames=("marie_123",),
    )

    asyncio.run(service.record_throne_send(creator=_creator(), payload=_payload("alias")))

    assert sends.inserted is not None
    assert sends.inserted.sub_id == 7
    assert sends.inserted.sub_user_id == 99
    assert subs.lookup_calls == [(1, "alias")]


def test_anonymous_sender_does_not_attempt_sub_alias_lookup():
    sends = _FakeSendsRepo()
    subs = _FakeSubsRepo()
    service = SendService(
        sends=sends,
        subs=subs,
        maintenance=_FakeMaintenance(),
        throne_test_gifter_usernames=("marie_123",),
    )

    asyncio.run(service.record_throne_send(creator=_creator(), payload=_payload("anonymous")))

    assert sends.inserted is not None
    assert sends.inserted.sub_id is None
    assert sends.inserted.sub_user_id is None
    assert subs.lookup_calls == []
