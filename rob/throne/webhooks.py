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
    tracked_profiles = len(entries)
    total_cents = sum(int(entry["total_cents"]) for entry in entries)
    total_sends = sum(int(entry["send_count"]) for entry in entries)
    total_amount = f"${(total_cents / 100):,.2f}"

    if entries:
        row_items = "\n".join(
            (
                f'<li class="public-leaderboard-row{" public-leaderboard-row--leader" if i == 1 else ""}" style="--row-index:{i};">'
                f'<div class="row-rank">#{i}</div>'
                '<div class="row-copy">'
                f'<div class="row-name">{escape(entry["name"])}</div>'
                '<div class="row-caption">Tracked send total</div>'
                '</div>'
                '<div class="row-values">'
                f'<div class="row-amount">{escape(entry["amount"])}</div>'
                f'<div class="row-sends">{escape(entry["count"])} sends</div>'
                "</div>"
                "</li>"
            )
            for i, entry in enumerate(entries, 1)
        )
        rows = f'<ol class="public-leaderboard-list">{row_items}</ol>'
    else:
        rows = (
            '<div class="public-leaderboard-empty">'
            "No tracked sends are available yet. As soon as sends are posted, this page updates automatically."
            "</div>"
        )

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --ink-950: #1f2230;
      --ink-700: #4b536b;
      --ink-500: #6f7a97;
      --paper-100: #fbfcff;
      --paper-200: #f3f6fc;
      --paper-300: #e8eef9;
      --line: #d8e1f0;
      --accent-700: #1c5fbe;
      --accent-500: #2b7df0;
      --accent-200: #d9e8ff;
      --leader-bg: #e7f1ff;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: var(--paper-200); color: var(--ink-950); }}
    body {{
      font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      min-height: 100vh;
      background:
        radial-gradient(1200px 560px at 10% -10%, rgba(43, 125, 240, 0.14), transparent 58%),
        radial-gradient(920px 620px at 100% 0%, rgba(28, 95, 190, 0.14), transparent 52%),
        linear-gradient(180deg, #f8fbff 0%, #f2f6fd 100%);
    }}
    .public-leaderboard-shell {{ min-height: 100vh; padding: 40px 20px; }}
    .public-leaderboard-card {{
      width: min(980px, 100%);
      margin: 0 auto;
      border: 1px solid var(--line);
      background: var(--paper-100);
      border-radius: 24px;
      box-shadow: 0 24px 60px rgba(25, 45, 86, 0.12);
      overflow: hidden;
    }}
    .public-leaderboard-hero {{
      padding: 34px 34px 24px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(130deg, #ffffff 0%, #f4f8ff 100%);
    }}
    .hero-kicker {{
      margin: 0;
      color: var(--accent-700);
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-weight: 700;
      font-size: 12px;
    }}
    .hero-title {{
      margin: 10px 0 0;
      font-family: "Georgia", "Times New Roman", serif;
      font-size: clamp(34px, 6vw, 52px);
      line-height: 1.05;
      letter-spacing: -0.02em;
      color: #1d2e53;
    }}
    .hero-subtitle {{
      margin: 12px 0 0;
      color: var(--ink-700);
      font-size: 16px;
      max-width: 70ch;
      line-height: 1.45;
    }}
    .public-leaderboard-metrics {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      padding: 20px 34px;
      border-bottom: 1px solid var(--line);
      background: var(--paper-200);
    }}
    .metric {{
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
    }}
    .metric-label {{
      display: block;
      color: var(--ink-500);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 8px;
      font-weight: 700;
    }}
    .metric-value {{
      display: block;
      color: var(--ink-950);
      font-size: 25px;
      line-height: 1;
      letter-spacing: -0.02em;
      font-weight: 700;
    }}
    .public-leaderboard-list-wrap {{ padding: 8px 26px 22px; }}
    .public-leaderboard-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 10px;
    }}
    .public-leaderboard-row {{
      display: grid;
      grid-template-columns: 74px 1fr auto;
      align-items: center;
      gap: 16px;
      padding: 16px 16px 16px 12px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: #ffffff;
      animation: rowReveal 380ms ease both;
      animation-delay: calc(var(--row-index, 1) * 45ms);
    }}
    .public-leaderboard-row--leader {{
      border-color: #b5d3ff;
      background: linear-gradient(180deg, #f8fbff 0%, var(--leader-bg) 100%);
    }}
    .row-rank {{
      width: 54px;
      height: 54px;
      display: grid;
      place-items: center;
      font-weight: 800;
      font-size: 20px;
      border-radius: 14px;
      color: #174a9a;
      background: var(--accent-200);
    }}
    .row-name {{
      font-size: 23px;
      color: var(--ink-950);
      font-weight: 700;
      line-height: 1.15;
      word-break: break-word;
    }}
    .row-caption {{
      margin-top: 6px;
      color: var(--ink-700);
      font-size: 14px;
    }}
    .row-values {{ text-align: right; white-space: nowrap; }}
    .row-amount {{
      font-size: 22px;
      color: #153569;
      font-weight: 700;
      line-height: 1.1;
      letter-spacing: -0.01em;
    }}
    .row-sends {{
      margin-top: 7px;
      font-size: 14px;
      color: var(--ink-700);
    }}
    .public-leaderboard-empty {{
      margin: 8px;
      padding: 20px 18px;
      border-radius: 14px;
      border: 1px dashed #bdd1ef;
      background: #f8fbff;
      color: #33466e;
      font-size: 16px;
      line-height: 1.5;
    }}
    .public-leaderboard-footer {{
      border-top: 1px solid var(--line);
      padding: 16px 34px 24px;
      color: var(--ink-700);
      font-size: 14px;
      line-height: 1.6;
      background: #fcfdff;
    }}
    @keyframes rowReveal {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @media (max-width: 760px) {{
      .public-leaderboard-shell {{ padding: 20px 12px; }}
      .public-leaderboard-hero {{ padding: 24px 18px 18px; }}
      .public-leaderboard-metrics {{
        grid-template-columns: 1fr;
        padding: 14px 18px;
      }}
      .public-leaderboard-list-wrap {{ padding: 8px 12px 16px; }}
      .public-leaderboard-row {{
        grid-template-columns: 54px 1fr;
        align-items: start;
      }}
      .row-values {{
        grid-column: 2;
        text-align: left;
        margin-top: 6px;
      }}
      .row-name {{ font-size: 20px; }}
      .public-leaderboard-footer {{ padding: 14px 18px 18px; }}
    }}
  </style>
</head>
<body>
  <main class="public-leaderboard-shell">
    <section class="public-leaderboard-card">
      <header class="public-leaderboard-hero">
        <p class="hero-kicker">Rob Public Leaderboard</p>
        <h1 class="hero-title">{escape(title)}</h1>
        <p class="hero-subtitle">Live send totals for registered Dom/mes. This board updates automatically as sends are posted.</p>
      </header>
      <section class="public-leaderboard-metrics">
        <article class="metric">
          <span class="metric-label">Tracked Profiles</span>
          <span class="metric-value">{tracked_profiles}</span>
        </article>
        <article class="metric">
          <span class="metric-label">Total Sends</span>
          <span class="metric-value">{total_sends}</span>
        </article>
        <article class="metric">
          <span class="metric-label">Total Amount</span>
          <span class="metric-value">{escape(total_amount)}</span>
        </article>
      </section>
      <section class="public-leaderboard-list-wrap">{rows}</section>
      <footer class="public-leaderboard-footer">
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
        {
            "name": (item.label or "Registered Dom/me"),
            "amount": f"${(item.total_cents / 100):,.2f}",
            "count": str(item.send_count),
            "total_cents": str(item.total_cents),
            "send_count": str(item.send_count),
        }
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
