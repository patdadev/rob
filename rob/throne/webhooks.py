from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from html import escape
from typing import Any

from aiohttp import web

from rob.config.settings import WebhookSettings
from rob.database.connection import Database
from rob.database.repositories.bot_state import BotStateRepository
from rob.database.repositories.leaderboards import LeaderboardsRepository
from rob.database.repositories.public_leaderboards import PublicLeaderboardsRepository
from rob.database.repositories.sends import SendsRepository
from rob.database.repositories.throne_creators import ThroneCreatorsRepository
from rob.services.maintenance_service import MaintenanceService
from rob.services.send_service import SendService
from rob.services.throne_service import ThroneService
from rob.throne.payloads import is_explicit_test_webhook_payload, is_known_test_sender, is_supported_event_type, parse_throne_send_payload
from rob.throne.security import build_signed_message, secret_matches, validate_timestamp_header, verify_ed25519_signature

log = logging.getLogger(__name__)


def _public_leaderboard_html(*, title: str, entries: list[dict[str, str]], data_updated_at: str, page_refreshed_at: str) -> str:
    if entries:
        rows = "\n".join(
            (
                '<article class="leaderboard-entry">'
                f'<div class="entry-rank">#{i}</div>'
                '<div>'
                f'<div class="entry-name">{escape(e["name"])}</div>'
                '<div class="entry-meta">Tracked send total</div>'
                '</div>'
                '<div>'
                f'<div class="entry-total">{escape(e["amount"])}</div>'
                f'<div class="entry-sends">{escape(e["count"])} sends</div>'
                '</div>'
                '</article>'
            )
            for i, e in enumerate(entries, 1)
        )
    else:
        rows = '<div class="empty-state">No tracked sends are available yet.</div>'
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{escape(title)}</title>
  <style>
    html, body {{ margin:0; padding:0; background:#000; color:#b40000; font-family:\"Times New Roman\", Times, serif; }}
    body {{ min-height:100vh; }}
    .leaderboard-page {{ box-sizing:border-box; min-height:100vh; padding:28px; background:radial-gradient(circle at top, rgba(120,0,0,0.18), transparent 34%), linear-gradient(180deg, #050000 0%, #000 58%, #050000 100%); }}
    .leaderboard-panel {{ box-sizing:border-box; width:min(900px,100%); margin:0 auto; padding:28px; border:1px solid #640000; background:linear-gradient(180deg, rgba(18,0,0,0.94), rgba(5,0,0,0.96)); box-shadow:0 0 36px rgba(120,0,0,0.22), inset 0 0 24px rgba(80,0,0,0.12); }}
    .leaderboard-header {{ padding-bottom:18px; border-bottom:1px solid #640000; }} .leaderboard-title {{ margin:0; color:#d00000; font-size:clamp(34px,5vw,52px); line-height:1; font-weight:bold; letter-spacing:0.045em; }} .leaderboard-subtitle {{ margin-top:10px; color:#9a0000; font-size:16px; letter-spacing:0.02em; }} .leaderboard-entries {{ margin-top:6px; }} .leaderboard-entry {{ display:grid; grid-template-columns:82px 1fr auto; gap:18px; align-items:baseline; padding:18px 0; border-bottom:1px solid #360000; }} .leaderboard-entry:last-child {{ border-bottom:none; }} .entry-rank {{ color:#d00000; font-size:28px; font-weight:bold; line-height:1; }} .entry-name {{ color:#c80000; font-size:28px; font-weight:bold; line-height:1.08; word-break:break-word; }} .entry-meta {{ margin-top:7px; color:#980000; font-size:17px; line-height:1.3; }} .entry-total {{ color:#c00000; font-size:20px; font-weight:bold; white-space:nowrap; text-align:right; }} .entry-sends {{ margin-top:7px; color:#870000; font-size:15px; text-align:right; }} .leaderboard-footer {{ margin-top:18px; padding-top:16px; border-top:1px solid #640000; color:#820000; font-size:14px; line-height:1.55; }} .empty-state {{ margin-top:18px; padding:20px 0; color:#980000; border-bottom:1px solid #360000; font-size:18px; }} @media (max-width:680px) {{ .leaderboard-page {{ padding:18px; }} .leaderboard-panel {{ padding:20px; }} .leaderboard-entry {{ grid-template-columns:58px 1fr; gap:12px; }} .entry-total {{ grid-column:2; text-align:left; margin-top:6px; }} .entry-sends {{ text-align:left; }} .entry-rank, .entry-name {{ font-size:24px; }} }}
  </style>
</head>
<body>
  <main class=\"leaderboard-page\">
    <section class=\"leaderboard-panel\">
      <header class=\"leaderboard-header\">
        <h1 class=\"leaderboard-title\">{escape(title)}</h1>
        <div class=\"leaderboard-subtitle\">Tracked send leaderboard</div>
      </header>
      <section class=\"leaderboard-entries\">{rows}</section>
      <footer class=\"leaderboard-footer\">
        <div>Leaderboard data updated: {escape(data_updated_at)}</div>
        <div>Page refreshed: {escape(page_refreshed_at)}</div>
      </footer>
    </section>
  </main>
</body>
</html>"""


def _dedupe_fallback_labels(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    seen = 0
    for e in entries:
        name = e["name"]
        if name == "Registered Dom/me":
            seen += 1
            if seen > 1:
                name = f"Registered Dom/me {seen}"
        out.append({**e, "name": name})
    return out


async def handle_public_leaderboard(request: web.Request) -> web.Response:
    token = request.match_info["public_token"]
    database: Database = request.app["database"]
    settings: WebhookSettings = request.app["settings"]
    public_repo = PublicLeaderboardsRepository(database)
    row = await public_repo.get_by_token(token)
    if row is None or not row.enabled:
        return web.Response(status=404, text="Not found", content_type="text/plain")
    leaderboards = LeaderboardsRepository(database)
    top = await leaderboards.get_top_dommes_public(
        row.guild_id,
        limit=settings.leaderboard_limit,
        include_test_sends=settings.throne_parse_test_sends_as_real_sends,
        test_gifter_usernames=settings.throne_test_gifter_usernames,
        owner_test_user_id=settings.throne_test_send_leaderboard_owner_user_id,
    )
    entries = [
        {"name": (item.label or "Registered Dom/me"), "amount": f"${(item.total_cents / 100):,.2f}", "count": str(item.send_count)}
        for item in top
    ]
    entries = _dedupe_fallback_labels(entries)
    latest = await leaderboards.get_public_data_freshness(
        row.guild_id,
        include_test_sends=settings.throne_parse_test_sends_as_real_sends,
        test_gifter_usernames=settings.throne_test_gifter_usernames,
        owner_test_user_id=settings.throne_test_send_leaderboard_owner_user_id,
    )
    page_refreshed = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data_updated = latest.strftime("%Y-%m-%d %H:%M UTC") if latest else "No tracked sends yet"
    html = _public_leaderboard_html(title=row.title, entries=entries, data_updated_at=data_updated, page_refreshed_at=page_refreshed)
    response = web.Response(text=html, content_type="text/html")
    response.headers["Cache-Control"] = f"public, max-age={settings.public_leaderboard_cache_seconds}"
    return response


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


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

    creators = ThroneCreatorsRepository(database)
    matching_creators = await creators.get_by_creator_id(creator_id)

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
    if explicit_test:
        await creators.mark_setup_verified(matched_creator.id)
        return web.json_response({"ok": True, "setup_verified": True})
    if known_test_sender and not settings.throne_parse_test_sends_as_real_sends:
        await creators.mark_setup_verified(matched_creator.id)
    if known_test_sender and settings.throne_parse_test_sends_as_real_sends:
        log.warning("Known Throne test sender accepted as real send due to THRONE_PARSE_TEST_SENDS_AS_REAL_SENDS=true. creator_id=%s gifter_username=%s", creator_id, parsed.gifter_username)

    if not is_supported_event_type(parsed.event_type):
        await creators.touch_successful_event(matched_creator.id)
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
    await creators.touch_successful_event(matched_creator.id)

    if send is None:
        return web.json_response({"ok": True, "duplicate": True})

    response: dict[str, Any] = {"ok": True, "inserted": True, "send_id": send.id}
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
    app["settings"] = settings
    app["database"] = database
    app["throne_service"] = ThroneService()
    app["subs_repository"] = SubsRepository(database)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/public/leaderboard/{public_token}", handle_public_leaderboard)
    app.router.add_post("/throne/webhook/{creator_id}/{secret}", handle_throne_webhook)

    async def close_throne_service(_app: web.Application) -> None:
        await _app["throne_service"].close()

    app.on_cleanup.append(close_throne_service)
    return app
