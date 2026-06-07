from __future__ import annotations

import hmac
import json
import logging
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from aiohttp import web

from rob.config.guilds import is_test_guild
from rob.config.settings import WebhookSettings
from rob.database.repositories.age_verification import STATUS_NOT_STARTED, AgeVerificationRepository
from rob.database.connection import Database
from rob.database.repositories.bot_state import BotStateRepository
from rob.database.repositories.dommes import DommesRepository
from rob.database.repositories.sends import SendsRepository
from rob.services.age_verification_service import (
    AgeVerificationConfigError,
    AgeVerificationError,
    AgeVerificationService,
    AgeVerificationUnavailableError,
)
from rob.services.maintenance_service import MaintenanceService
from rob.services.bot_notify_client import (
    notify_bot_age_verification_sync,
    notify_bot_onboarding_webhook_verified,
    notify_bot_send,
)
from rob.services.send_service import SendService
from rob.services.throne_service import ThroneService
from rob.services.yoti_age_provider import YotiAgeProvider
from rob.throne.payloads import is_explicit_test_webhook_payload, is_known_test_sender, is_supported_event_type, parse_throne_send_payload
from rob.throne.security import build_signed_message, secret_matches, validate_timestamp_header, verify_ed25519_signature

log = logging.getLogger(__name__)


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


def _serialize_datetime(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _age_status_payload(
    *,
    service: AgeVerificationService,
    guild_id: int,
    discord_user_id: int,
    record,
    verification_url: str | None = None,
) -> dict[str, Any]:
    status = record.status if record is not None else STATUS_NOT_STARTED
    expires_at = record.expires_at if record is not None else None
    return {
        "status": status,
        "guild_id": guild_id,
        "discord_user_id": discord_user_id,
        "provider": record.provider if record is not None else "yoti",
        "age_threshold": record.age_threshold if record is not None else service.age_threshold,
        "verification_url": verification_url,
        "yoti_session_id": record.yoti_session_id if record is not None else None,
        "yoti_reference_id": record.yoti_reference_id if record is not None else None,
        "yoti_method": record.yoti_method if record is not None else None,
        "yoti_result_summary": record.yoti_result_summary if record is not None else None,
        "manual_review_reason": record.manual_review_reason if record is not None else None,
        "verified_at": _serialize_datetime(record.verified_at) if record is not None else None,
        "expires_at": _serialize_datetime(expires_at),
        "revoked_at": _serialize_datetime(record.revoked_at) if record is not None else None,
        "created_at": _serialize_datetime(record.created_at) if record is not None else None,
        "updated_at": _serialize_datetime(record.updated_at) if record is not None else None,
    }


def _backend_secret_error() -> web.Response:
    return web.json_response(
        {"error": "backend_secret_not_configured"},
        status=503,
    )


def _is_authorized_backend_request(request: web.Request) -> bool:
    settings: WebhookSettings = request.app["settings"]
    configured_secret = getattr(settings, "rob_backend_secret", None)
    if not configured_secret:
        return False
    provided = request.headers.get("Authorization", "")
    expected = f"Bearer {configured_secret}"
    return hmac.compare_digest(provided, expected)


def _redirect_with_query(url: str, **params: str | None) -> str:
    parts = urlsplit(url)
    query: dict[str, str] = {}
    if parts.query:
        from urllib.parse import parse_qsl

        query.update(dict(parse_qsl(parts.query, keep_blank_values=True)))
    query.update(
        dict((key, value) for key, value in (params or {}).items() if value is not None)
    )
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


async def handle_age_verification_start(request: web.Request) -> web.Response:
    settings: WebhookSettings = request.app["settings"]
    if not getattr(settings, "rob_backend_secret", None):
        return _backend_secret_error()
    if not _is_authorized_backend_request(request):
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_payload"}, status=400)
    try:
        guild_id = int(payload.get("guild_id"))
        discord_user_id = int(payload.get("discord_user_id"))
    except (AttributeError, TypeError, ValueError):
        return web.json_response({"error": "invalid_payload"}, status=400)

    service: AgeVerificationService = request.app["age_verification_service"]
    repository: AgeVerificationRepository = request.app["age_verification_repository"]
    try:
        start = await service.start_verification(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )
    except AgeVerificationUnavailableError as exc:
        return web.json_response({"error": str(exc)}, status=403)
    except AgeVerificationConfigError as exc:
        return web.json_response({"error": str(exc)}, status=503)
    except AgeVerificationError as exc:
        return web.json_response({"error": str(exc)}, status=502)

    record = await repository.get(
        guild_id=guild_id,
        discord_user_id=discord_user_id,
    )
    status_payload = _age_status_payload(
        service=service,
        guild_id=guild_id,
        discord_user_id=discord_user_id,
        record=record,
        verification_url=start.verification_url,
    )
    status_payload["status"] = start.status
    status_payload["expires_at"] = _serialize_datetime(start.expires_at)
    status_payload["yoti_session_id"] = start.session_id
    return web.json_response(status_payload)


async def handle_age_verification_status(request: web.Request) -> web.Response:
    settings: WebhookSettings = request.app["settings"]
    if not getattr(settings, "rob_backend_secret", None):
        return _backend_secret_error()
    if not _is_authorized_backend_request(request):
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        guild_id = int(request.query["guild_id"])
        discord_user_id = int(request.query["discord_user_id"])
    except (KeyError, TypeError, ValueError):
        return web.json_response({"error": "invalid_query"}, status=400)

    service: AgeVerificationService = request.app["age_verification_service"]
    try:
        service.ensure_enabled_for(guild_id)
    except AgeVerificationUnavailableError as exc:
        return web.json_response({"error": str(exc)}, status=403)

    record = await service.get_status_record(
        guild_id=guild_id,
        discord_user_id=discord_user_id,
    )
    verification_url: str | None = None
    provider = getattr(service, "provider", None)
    if (
        record is not None
        and record.status == "pending"
        and record.yoti_session_id
        and provider is not None
    ):
        verification_url = provider.build_verification_url(record.yoti_session_id)
    return web.json_response(
        _age_status_payload(
            service=service,
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            record=record,
            verification_url=verification_url,
        )
    )


async def handle_yoti_notification(request: web.Request) -> web.Response:
    service: AgeVerificationService = request.app["age_verification_service"]
    settings: WebhookSettings = request.app["settings"]
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
    if not isinstance(payload, dict):
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    try:
        record = await service.handle_notification(payload)
    except AgeVerificationConfigError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=503)
    except AgeVerificationError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    if record is not None:
        await notify_bot_age_verification_sync(
            notify_base_url=settings.rob_bot_notify_url,
            secret=settings.rob_ops_secret,
            guild_id=record.guild_id,
            discord_user_id=record.discord_user_id,
        )
        log.info(
            "Processed Yoti notification session_id=%s guild_id=%s discord_user_id=%s status=%s",
            record.yoti_session_id,
            record.guild_id,
            record.discord_user_id,
            record.status,
        )
        return web.json_response({"ok": True, "status": record.status})

    return web.json_response({"ok": True, "ignored": True})


async def handle_yoti_callback(request: web.Request) -> web.Response:
    settings: WebhookSettings = request.app["settings"]
    service: AgeVerificationService = request.app["age_verification_service"]
    session_id = str(request.query.get("sessionId") or "").strip()
    status_text = None
    if session_id:
        try:
            record = await service.refresh_session(session_id=session_id)
        except AgeVerificationError:
            record = None
        if record is not None:
            status_text = record.status
            await notify_bot_age_verification_sync(
                notify_base_url=settings.rob_bot_notify_url,
                secret=settings.rob_ops_secret,
                guild_id=record.guild_id,
                discord_user_id=record.discord_user_id,
            )
    success_url = getattr(settings, "yoti_success_url", None)
    if success_url:
        raise web.HTTPFound(
            _redirect_with_query(
                success_url,
                sessionId=session_id or None,
                status=status_text,
            )
        )
    return web.Response(
        text=(
            "<html><body><p>Thanks - your age verification has been submitted. "
            "You can return to Discord and run /age-status.</p></body></html>"
        ),
        content_type="text/html",
    )


async def handle_throne_webhook(request: web.Request) -> web.Response:
    database: Database = request.app["database"]
    settings: WebhookSettings = request.app["settings"]
    throne: ThroneService = request.app["throne_service"]

    creator_id = request.match_info["creator_id"]
    provided_secret = request.match_info["secret"]

    raw_body = await request.read()

    timestamp_header = request.headers.get(settings.throne_webhook_timestamp_header)
    signature_header = request.headers.get(settings.throne_webhook_signature_header, "").strip()

    if settings.throne_webhook_require_signature:
        if not validate_timestamp_header(
            timestamp_header,
            max_skew_seconds=settings.throne_webhook_max_timestamp_skew_seconds,
        ):
            return web.json_response({"ok": False, "error": "invalid_timestamp"}, status=401)
        if not settings.throne_public_key_pem:
            return web.json_response({"ok": False, "error": "signature_not_configured"}, status=401)
        message = build_signed_message(
            timestamp=timestamp_header or "",
            raw_body=raw_body,
            signed_message_format=settings.throne_webhook_signed_message_format,
        )
        if not verify_ed25519_signature(
            public_key_pem=settings.throne_public_key_pem,
            signature_hex=signature_header,
            message=message,
        ):
            return web.json_response({"ok": False, "error": "invalid_signature"}, status=401)

    try:
        payload: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    if settings.throne_webhook_debug_log_payload:
        log.info("Throne webhook payload for %s: %s", creator_id, payload)

    dommes = DommesRepository(database)
    matching_creators = await dommes.get_by_creator_id(creator_id)

    matched_creator = None
    for creator in matching_creators:
        if secret_matches(
            provided_secret=provided_secret,
            stored_secret=creator.webhook_secret,
            stored_secret_hash=creator.webhook_secret_hash,
        ):
            matched_creator = creator
            break

    if matched_creator is None:
        return web.json_response(
            {"ok": False, "error": "creator_not_found_or_secret_invalid"},
            status=403,
        )

    parsed = parse_throne_send_payload(creator_id=creator_id, payload=payload)
    explicit_test = is_explicit_test_webhook_payload(payload, parsed)
    known_test_sender = is_known_test_sender(parsed.gifter_username, test_gifter_usernames=set(settings.throne_test_gifter_usernames))
    in_test_guild = is_test_guild(matched_creator.guild_id)
    log.info(
        "Throne webhook received creator_id=%s guild_id=%s discord_user_id=%s "
        "event_type=%s gifter=%s explicit_test=%s known_test_sender=%s "
        "parse_test_as_real=%s test_guild=%s",
        creator_id,
        matched_creator.guild_id,
        matched_creator.discord_user_id,
        parsed.event_type,
        parsed.gifter_username,
        explicit_test,
        known_test_sender,
        settings.throne_parse_test_sends_as_real_sends,
        in_test_guild,
    )

    notify_state: dict[str, bool] = {"sent": False}

    async def _maybe_auto_advance(reason: str) -> None:
        """Best-effort auto-advance of the DM onboarding flow.

        Always safe to call multiple times: the bot-side cog gates on the
        current onboarding stage and is a no-op for completed / unknown
        users. Failures here must never break the webhook response.

        We additionally guard against multiple notifications per webhook
        delivery so the bot ops endpoint sees one POST per inbound event.
        """

        if not in_test_guild:
            log.info(
                "Onboarding auto-advance skipped (not test guild) "
                "guild_id=%s discord_user_id=%s reason=%s",
                matched_creator.guild_id,
                matched_creator.discord_user_id,
                reason,
            )
            return
        if notify_state["sent"]:
            log.info(
                "Onboarding auto-advance already notified for this webhook "
                "guild_id=%s discord_user_id=%s skipped_reason=%s",
                matched_creator.guild_id,
                matched_creator.discord_user_id,
                reason,
            )
            return
        notify_state["sent"] = True
        log.info(
            "Onboarding auto-advance notifying bot guild_id=%s "
            "discord_user_id=%s reason=%s",
            matched_creator.guild_id,
            matched_creator.discord_user_id,
            reason,
        )
        try:
            delivered = await notify_bot_onboarding_webhook_verified(
                notify_base_url=settings.rob_bot_notify_url,
                secret=settings.rob_ops_secret,
                guild_id=int(matched_creator.guild_id),
                discord_user_id=int(matched_creator.discord_user_id),
            )
        except Exception:
            log.exception(
                "Onboarding auto-advance notification raised for guild_id=%s "
                "discord_user_id=%s reason=%s",
                matched_creator.guild_id,
                matched_creator.discord_user_id,
                reason,
            )
            return
        log.info(
            "Onboarding auto-advance notification result delivered=%s "
            "guild_id=%s discord_user_id=%s reason=%s",
            delivered,
            matched_creator.guild_id,
            matched_creator.discord_user_id,
            reason,
        )

    if explicit_test:
        log.info(
            "Throne webhook classified as explicit test creator_id=%s",
            creator_id,
        )
        await dommes.mark_setup_verified(matched_creator.id)
        await _maybe_auto_advance("explicit_test")
        return web.json_response(
            {
                "ok": True,
                "setup_verified": True,
            }
        )
    if known_test_sender and not settings.throne_parse_test_sends_as_real_sends:
        log.info(
            "Throne webhook classified as known test sender (setup-only) "
            "creator_id=%s gifter=%s",
            creator_id,
            parsed.gifter_username,
        )
        await dommes.mark_setup_verified(matched_creator.id)
        await _maybe_auto_advance("known_test_sender")
        # Intentionally fall through: known_test_sender rows are still
        # inserted via ``record_throne_send`` below so the public send
        # tracker flow can render them (they're stored with
        # ``is_test_send=true`` and filtered out of leaderboards).
    if known_test_sender and settings.throne_parse_test_sends_as_real_sends:
        log.warning("Known Throne test sender accepted as real send due to THRONE_PARSE_TEST_SENDS_AS_REAL_SENDS=true. creator_id=%s gifter_username=%s", creator_id, parsed.gifter_username)
        # Still mark setup and auto-advance: this is the same Throne test
        # webhook click, just stored as a real send for visual flow testing.
        # Intentionally fall through to ``record_throne_send`` below.
        await dommes.mark_setup_verified(matched_creator.id)
        await _maybe_auto_advance("known_test_sender_parsed_as_real")

    if not is_supported_event_type(parsed.event_type):
        await dommes.touch_successful_event(matched_creator.id)
        return web.json_response(
            {
                "ok": True,
                "ignored": True,
                "event_type": parsed.event_type,
            }
        )

    maintenance = MaintenanceService(BotStateRepository(database))
    send_service = SendService(
        sends=SendsRepository(database),
        subs=request.app["subs_repository"],
        maintenance=maintenance,
        throne=throne,
        throne_test_gifter_usernames=settings.throne_test_gifter_usernames,
    )
    send = await send_service.record_throne_send(
        creator=matched_creator,
        payload=parsed,
    )
    await dommes.touch_successful_event(matched_creator.id)

    if send is None:
        # Duplicate event — still attempt auto-advance because the user's
        # onboarding may be waiting on this same successful webhook arrival.
        await _maybe_auto_advance("duplicate_send")
        return web.json_response({"ok": True, "duplicate": True})

    bot_notified = await notify_bot_send(
        notify_url=settings.rob_bot_notify_url,
        secret=settings.rob_ops_secret,
        send_id=send.id,
        guild_id=send.guild_id,
    )

    # A successful send for a Dom/me who is still mid-onboarding is the
    # same "Throne test webhook arrived" signal the user is waiting for.
    # The bot-side cog is a safe no-op if onboarding is already complete.
    await _maybe_auto_advance("real_send_recorded")

    response: dict[str, Any] = {
        "ok": True,
        "inserted": True,
        "send_id": send.id,
        "bot_notified": bot_notified,
    }
    if known_test_sender and not settings.throne_parse_test_sends_as_real_sends:
        response["setup_verified"] = True
    return web.json_response(response)


def create_webhook_app(
    *,
    settings: WebhookSettings,
    database: Database,
) -> web.Application:
    from rob.database.repositories.subs import SubsRepository

    app = web.Application()
    yoti_provider = YotiAgeProvider.from_settings(settings)
    if getattr(settings, "rob_age_verification_enabled", False):
        yoti_provider.validate_startup_configuration()
    age_repository = AgeVerificationRepository(database)
    age_service = AgeVerificationService(
        age_verifications=age_repository,
        enabled=getattr(settings, "rob_age_verification_enabled", False),
        test_only=getattr(settings, "rob_age_verification_test_only", True),
        age_threshold=getattr(settings, "yoti_age_threshold", 18),
        provider=yoti_provider,
    )
    app["settings"] = settings
    app["database"] = database
    app["throne_service"] = ThroneService()
    app["subs_repository"] = SubsRepository(database)
    app["age_verification_repository"] = age_repository
    app["age_verification_service"] = age_service
    app["yoti_age_provider"] = yoti_provider
    app.router.add_get("/health", handle_health)
    app.router.add_post("/age-verification/start", handle_age_verification_start)
    app.router.add_get("/age-verification/status", handle_age_verification_status)
    app.router.add_post("/yoti/notification", handle_yoti_notification)
    app.router.add_get("/yoti/callback", handle_yoti_callback)
    app.router.add_post("/throne/webhook/{creator_id}/{secret}", handle_throne_webhook)
    app.router.add_post("/webhook/{creator_id}/{secret}", handle_throne_webhook)

    async def close_throne_service(_app: web.Application) -> None:
        await _app["throne_service"].close()

    async def close_yoti_provider(_app: web.Application) -> None:
        await _app["yoti_age_provider"].close()

    app.on_cleanup.append(close_throne_service)
    app.on_cleanup.append(close_yoti_provider)
    return app
