from __future__ import annotations

import argparse
import asyncio
import os
import re
import secrets
from dataclasses import dataclass

from rob.config.settings import configure_logging, load_base_settings
from rob.database.connection import Database
from rob.database.repositories import (
    BlacklistRepository,
    BotStateRepository,
    CountingRepository,
    DommesRepository,
    GuildSettingsRepository,
    LeaderboardsRepository,
    SendsRepository,
    SubsRepository,
    ThroneCreatorsRepository,
)
from rob.services.maintenance_service import MaintenanceService
from rob.services.registration_service import RegistrationService
from rob.services.send_service import SendService
from rob.services.throne_service import ThroneService
from rob.throne.security import hash_webhook_secret
from rob.utils.money import dollars_to_cents


_USER_REF_RE = re.compile(r"<@!?(\d+)>")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rob backend operations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show database, maintenance, and queue status.")

    maintenance = subparsers.add_parser("maintenance", help="Manage maintenance mode.")
    maintenance_subparsers = maintenance.add_subparsers(dest="maintenance_command", required=True)
    maintenance_subparsers.add_parser("status", help="Show maintenance mode state.")
    maintenance_on = maintenance_subparsers.add_parser("on", help="Enable maintenance mode.")
    maintenance_on.add_argument("reason", nargs="?", default="", help="Optional maintenance reason.")
    maintenance_subparsers.add_parser("off", help="Disable maintenance mode.")

    queue = subparsers.add_parser("queue", help="Inspect or release queued sends.")
    queue_subparsers = queue.add_subparsers(dest="queue_command", required=True)
    queue_subparsers.add_parser("status", help="Show queue counts.")
    queue_subparsers.add_parser("flush", help="Release queued maintenance sends to pending.")

    leaderboard = subparsers.add_parser("leaderboard", help="Leaderboard operations.")
    leaderboard_subparsers = leaderboard.add_subparsers(dest="leaderboard_command", required=True)
    leaderboard_subparsers.add_parser("refresh", help="Request a leaderboard refresh from the bot.")
    leaderboard_adopt = leaderboard_subparsers.add_parser(
        "adopt",
        help="Adopt existing Discord leaderboard messages into DB refs.",
    )
    leaderboard_adopt.add_argument("--guild-id", type=int, required=True)
    leaderboard_adopt.add_argument("--leaderboard-channel-id", type=int, required=True)
    leaderboard_adopt.add_argument("--leaderboard-message-id", type=int, required=True)
    leaderboard_adopt.add_argument("--stats-message-id", type=int, required=True)
    leaderboard_status = leaderboard_subparsers.add_parser("status", help="Show leaderboard status summary.")
    leaderboard_status.add_argument("--guild-id", type=int, default=None)
    leaderboard_preview = leaderboard_subparsers.add_parser("preview", help="Preview top leaderboard rows.")
    leaderboard_preview.add_argument("--guild-id", type=int, default=None)
    diagnose = leaderboard_subparsers.add_parser("diagnose", help="Diagnose leaderboard send matching.")
    diagnose.add_argument("--guild-id", type=int, default=None)
    repair = leaderboard_subparsers.add_parser(
        "repair-send-dommes",
        help="Repair sends.domme_user_id from dommes.id matches.",
    )
    repair.add_argument("--guild-id", type=int, default=None)
    repair.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")

    throne = subparsers.add_parser("throne", help="Throne send operations.")
    throne_subparsers = throne.add_subparsers(dest="throne_command", required=True)
    throne_subparsers.add_parser(
        "refresh",
        help="Show current webhook-only tracking mode guidance (legacy alias).",
    )
    throne_status = throne_subparsers.add_parser("status", help="Show Throne creator status.")
    throne_status.add_argument("--guild-id", type=int, default=None)
    throne_status.add_argument("--handle", type=str, default=None)
    throne_dommes = throne_subparsers.add_parser("dommes", help="List registered Throne creators.")
    throne_dommes.add_argument("--guild-id", type=int, default=None)
    throne_list = throne_subparsers.add_parser(
        "list",
        help="List registered Throne creators (legacy alias for dommes).",
    )
    throne_list.add_argument("--guild-id", type=int, default=None)
    throne_search = throne_subparsers.add_parser(
        "search",
        help="Show one Throne creator record by Discord user ref.",
    )
    throne_search.add_argument("user_ref", type=str)
    throne_search.add_argument("--guild-id", type=int, default=None)

    throne_webhook = throne_subparsers.add_parser("webhook", help="Webhook secret operations.")
    throne_webhook_subparsers = throne_webhook.add_subparsers(
        dest="throne_webhook_command",
        required=True,
    )
    throne_webhook_refresh = throne_webhook_subparsers.add_parser(
        "refresh",
        help="Rotate webhook secret for one registered creator.",
    )
    throne_webhook_refresh.add_argument("user_ref", type=str)
    throne_webhook_refresh.add_argument("--guild-id", type=int, default=None)

    throne_addsend = throne_subparsers.add_parser(
        "addsend",
        help="Insert a manual send for a Dom/me (legacy compatibility command).",
    )
    throne_addsend.add_argument("user_ref", type=str)
    throne_addsend.add_argument("amount", type=float)
    throne_addsend.add_argument("--guild-id", type=int, default=None)
    throne_addsend.add_argument("--sub-name", type=str, default=None)
    throne_addsend.add_argument("--method", type=str, default="manual")
    throne_addsend.add_argument("--currency", type=str, default="USD")
    throne_addsend.add_argument("--note", type=str, default=None)

    throne_addsub = throne_subparsers.add_parser(
        "addsub",
        help="Register/update a Sub sending name for a Discord user.",
    )
    throne_addsub.add_argument("user_ref", type=str)
    throne_addsub.add_argument("name", type=str)
    throne_addsub.add_argument("--guild-id", type=int, default=None)

    throne_adddomme = throne_subparsers.add_parser(
        "adddomme",
        help="Register/update a Dom/me from a Throne URL/handle.",
    )
    throne_adddomme.add_argument("user_ref", type=str)
    throne_adddomme.add_argument("throne_input", type=str)
    throne_adddomme.add_argument("--guild-id", type=int, default=None)

    throne_subs = throne_subparsers.add_parser("subs", help="List registered subs.")
    throne_subs.add_argument("--guild-id", type=int, default=None)
    throne_subparsers.add_parser(
        "invalidate-test-sends",
        help="Mark known Throne test-user sends so leaderboards can exclude them.",
    )

    inactivity = subparsers.add_parser("inactivity", help="Inactivity system operations.")
    inactivity_subparsers = inactivity.add_subparsers(dest="inactivity_command", required=True)
    inactivity_status = inactivity_subparsers.add_parser("status", help="Show inactivity status.")
    inactivity_status.add_argument("--guild-id", type=int, default=None)
    inactivity_on = inactivity_subparsers.add_parser("on", help="Enable inactivity processing.")
    inactivity_on.add_argument("--guild-id", type=int, default=None)
    inactivity_off = inactivity_subparsers.add_parser("off", help="Disable inactivity processing.")
    inactivity_off.add_argument("--guild-id", type=int, default=None)

    blacklist = subparsers.add_parser("blacklist", help="Manage Rob global blacklist.")
    blacklist_subparsers = blacklist.add_subparsers(dest="blacklist_command", required=True)
    blacklist_add = blacklist_subparsers.add_parser("add", help="Add a user to blacklist.")
    blacklist_add.add_argument("discord_user_id", type=int)
    blacklist_add.add_argument("--reason", type=str, default="manual")
    blacklist_add.add_argument("--created-by", type=int, default=None)
    blacklist_remove = blacklist_subparsers.add_parser("remove", help="Remove a user from blacklist.")
    blacklist_remove.add_argument("discord_user_id", type=int)
    blacklist_list = blacklist_subparsers.add_parser("list", help="List blacklist entries.")
    blacklist_list.add_argument("--limit", type=int, default=100)

    sends = subparsers.add_parser("sends", help="Send record operations.")
    sends_subparsers = sends.add_subparsers(dest="sends_command", required=True)
    sends_list = sends_subparsers.add_parser("list", help="List recent sends.")
    sends_list.add_argument(
        "--status",
        choices=["pending", "posted", "failed", "queued_maintenance", "ignored", "all"],
        default="all",
    )
    sends_list.add_argument("--guild-id", type=int, default=None)
    sends_list.add_argument("--limit", type=int, default=25)
    sends_subparsers.add_parser(
        "backfill-public-ids",
        help="Generate and store missing public send IDs.",
    )
    sends_mark_posted = sends_subparsers.add_parser(
        "mark-posted",
        help="Force mark a send as posted.",
    )
    sends_mark_posted.add_argument("send_id", type=int)

    count = subparsers.add_parser("count", help="Counting operations.")
    count_subparsers = count.add_subparsers(dest="count_command", required=True)
    count_status = count_subparsers.add_parser("status", help="Show counting state.")
    count_status.add_argument("--guild-id", type=int, default=None)
    count_set = count_subparsers.add_parser("set", help="Set the current counting number.")
    count_set.add_argument("number", type=int)
    count_set.add_argument("--guild-id", type=int, default=None)

    return parser


@dataclass(frozen=True)
class OperationsContext:
    settings: object
    database: Database
    bot_state: BotStateRepository
    maintenance: MaintenanceService
    sends: SendsRepository
    dommes: DommesRepository
    subs: SubsRepository
    throne_creators: ThroneCreatorsRepository
    blacklist: BlacklistRepository
    leaderboards: LeaderboardsRepository
    guild_settings: GuildSettingsRepository
    counting: CountingRepository
    throne_service: ThroneService
    registration_service: RegistrationService
    send_service: SendService


async def create_context() -> OperationsContext:
    settings = load_base_settings()
    configure_logging(settings.log_level)
    database = Database(settings.database_url)
    await database.connect()
    bot_state = BotStateRepository(database)
    maintenance = MaintenanceService(bot_state)
    throne_service = ThroneService()
    guild_settings = GuildSettingsRepository(database)
    dommes = DommesRepository(database)
    subs = SubsRepository(database)
    throne_creators = ThroneCreatorsRepository(database)
    registration_service = RegistrationService(
        guild_settings=guild_settings,
        dommes=dommes,
        subs=subs,
        throne_creators=throne_creators,
        blacklist=BlacklistRepository(database),
        throne=throne_service,
        webhook_base_url=os.getenv("THRONE_WEBHOOK_BASE_URL") or None,
    )
    send_service = SendService(
        sends=SendsRepository(database),
        subs=subs,
        maintenance=maintenance,
        throne=throne_service,
        throne_test_gifter_usernames=settings.throne_test_gifter_usernames,
    )
    return OperationsContext(
        settings=settings,
        database=database,
        bot_state=bot_state,
        maintenance=maintenance,
        sends=send_service.sends,
        dommes=dommes,
        subs=subs,
        throne_creators=throne_creators,
        blacklist=registration_service.blacklist,
        leaderboards=LeaderboardsRepository(database),
        guild_settings=guild_settings,
        counting=CountingRepository(database),
        throne_service=throne_service,
        registration_service=registration_service,
        send_service=send_service,
    )


async def resolve_guild_id(ctx: OperationsContext, guild_id: int | None) -> int:
    if guild_id is not None:
        return guild_id
    guild_ids = await ctx.guild_settings.list_guild_ids()
    if len(guild_ids) == 1:
        return guild_ids[0]
    if not guild_ids:
        raise RuntimeError("No guild_settings rows exist yet. Add one first or pass --guild-id.")
    raise RuntimeError("Multiple guilds exist. Pass --guild-id explicitly.")


def parse_user_ref(value: str) -> int | None:
    raw = value.strip()
    if raw.isdigit():
        return int(raw)
    match = _USER_REF_RE.fullmatch(raw)
    if match:
        return int(match.group(1))
    return None


async def handle_status(ctx: OperationsContext) -> None:
    healthy = await ctx.database.health_check()
    maintenance = await ctx.maintenance.get_state()
    queue = await ctx.sends.count_statuses()
    print(f"database_ok={healthy}")
    print(f"maintenance_mode={'on' if maintenance.enabled else 'off'}")
    print(f"maintenance_reason={maintenance.reason or ''}")
    print(
        "queue_counts="
        f"pending:{queue.pending},"
        f"queued_maintenance:{queue.queued_maintenance},"
        f"posted:{queue.posted},"
        f"failed:{queue.failed},"
        f"ignored:{queue.ignored}"
    )


async def handle_maintenance(ctx: OperationsContext, args: argparse.Namespace) -> None:
    if args.maintenance_command == "status":
        state = await ctx.maintenance.get_state()
        print(f"maintenance_mode={'on' if state.enabled else 'off'}")
        print(f"maintenance_reason={state.reason or ''}")
        return
    if args.maintenance_command == "on":
        await ctx.maintenance.enable(reason=args.reason or "")
        print("maintenance_mode=on")
        if args.reason:
            print(f"maintenance_reason={args.reason}")
        print("leaderboard_refresh=requested")
        return
    if args.maintenance_command == "off":
        await ctx.maintenance.disable()
        released = await ctx.sends.release_queued_maintenance()
        print("maintenance_mode=off")
        print(f"released={released}")
        print("leaderboard_refresh=requested")
        return
    raise RuntimeError(f"Unsupported maintenance command: {args.maintenance_command}")


async def handle_queue(ctx: OperationsContext, args: argparse.Namespace) -> None:
    if args.queue_command == "status":
        queue = await ctx.sends.count_statuses()
        print(f"pending={queue.pending}")
        print(f"queued_maintenance={queue.queued_maintenance}")
        print(f"posted={queue.posted}")
        print(f"failed={queue.failed}")
        print(f"ignored={queue.ignored}")
        return
    if args.queue_command == "flush":
        if await ctx.maintenance.is_enabled():
            raise RuntimeError("Maintenance mode is still on. Disable it before flushing the queue.")
        released = await ctx.sends.release_queued_maintenance()
        print(f"released={released}")
        return
    raise RuntimeError(f"Unsupported queue command: {args.queue_command}")


async def handle_leaderboard(ctx: OperationsContext, args: argparse.Namespace) -> None:
    if args.leaderboard_command == "refresh":
        await ctx.maintenance.request_leaderboard_refresh()
        print("leaderboard_refresh=requested")
        return
    if args.leaderboard_command == "adopt":
        await ctx.leaderboards.upsert_message(
            guild_id=args.guild_id,
            message_key="leaderboard",
            leaderboard_type="leaderboard",
            channel_id=args.leaderboard_channel_id,
            message_id=args.leaderboard_message_id,
        )
        await ctx.leaderboards.upsert_message(
            guild_id=args.guild_id,
            message_key="leaderboard_stats",
            leaderboard_type="leaderboard_stats",
            channel_id=args.leaderboard_channel_id,
            message_id=args.stats_message_id,
        )
        print("leaderboard_adopted=true")
        print(f"guild_id={args.guild_id}")
        print(f"channel_id={args.leaderboard_channel_id}")
        print(f"leaderboard_message_id={args.leaderboard_message_id}")
        print(f"stats_message_id={args.stats_message_id}")
        return
    if args.leaderboard_command == "status":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        summary = await ctx.leaderboards.get_summary(
            guild_id,
            include_test_sends=ctx.settings.throne_parse_test_sends_as_real_sends,
            test_gifter_usernames=ctx.settings.throne_test_gifter_usernames,
            owner_test_user_id=ctx.settings.throne_test_send_leaderboard_owner_user_id,
        )
        print(f"guild_id={guild_id}")
        print(f"registered_dommes={summary.domme_count}")
        print(f"tracked_sends={summary.send_count}")
        print(f"tracked_total_cents={summary.total_cents}")
        return
    if args.leaderboard_command == "preview":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        rows = await ctx.leaderboards.get_top_dommes(
            guild_id,
            limit=ctx.settings.leaderboard_limit,
            include_test_sends=ctx.settings.throne_parse_test_sends_as_real_sends,
            test_gifter_usernames=ctx.settings.throne_test_gifter_usernames,
            owner_test_user_id=ctx.settings.throne_test_send_leaderboard_owner_user_id,
        )
        print(f"guild_id={guild_id}")
        print("preview=top_dommes")
        if not rows:
            print("rows=none")
            return
        for index, row in enumerate(rows, 1):
            print(
                f"{index}. user_id={row.user_id or 0} amount_cents={row.total_cents} send_count={row.send_count}"
            )
        return
    if args.leaderboard_command == "diagnose":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        report = await ctx.leaderboards.diagnose(
            guild_id,
            include_test_sends=ctx.settings.throne_parse_test_sends_as_real_sends,
            test_gifter_usernames=ctx.settings.throne_test_gifter_usernames,
            owner_test_user_id=ctx.settings.throne_test_send_leaderboard_owner_user_id,
            limit=ctx.settings.leaderboard_limit,
        )
        print("Leaderboard Diagnose")
        print(f"Guild ID: {report.guild_id}")
        print(f"Registered Dom/mes: {report.registered_dommes}")
        print(f"Counted sends: {report.counted_sends}")
        print(f"Excluded sends: {report.excluded_sends}")
        print("Excluded reasons:")
        print(f"- not posted: {report.excluded_not_posted}")
        print(f"- private: {report.excluded_private}")
        print(f"- test send excluded: {report.excluded_test_send}")
        print(f"- domme_user_id missing/mismatch: {report.excluded_domme_mismatch}")
        print(f"- guild mismatch: {report.excluded_guild_mismatch}")
        print("Dom/me Rows:")
        if not report.domme_rows:
            print("(none)")
        for row in report.domme_rows:
            print(f"{row.label} total={row.total_cents} sends={row.send_count}")
        print("Sends with no matching Dom/me:")
        if not report.unmatched_sends:
            print("(none)")
        for send_id, domme_user_id, send_guild_id in report.unmatched_sends:
            print(f"id={send_id} domme_user_id={domme_user_id} guild_id={send_guild_id}")
        return
    if args.leaderboard_command == "repair-send-dommes":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        candidates, updated = await ctx.sends.repair_send_domme_user_ids(
            guild_id=guild_id,
            dry_run=bool(args.dry_run),
        )
        print(f"guild_id={guild_id}")
        print(f"dry_run={bool(args.dry_run)}")
        print(f"candidates={candidates}")
        print(f"updated={updated}")
        return
    raise RuntimeError(f"Unsupported leaderboard command: {args.leaderboard_command}")


async def handle_count(ctx: OperationsContext, args: argparse.Namespace) -> None:
    guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
    if args.count_command == "status":
        state = await ctx.counting.get(guild_id)
        if state is None:
            print(f"guild_id={guild_id}")
            print("counting_state=missing")
            return
        print(f"guild_id={guild_id}")
        print(f"enabled={state.is_enabled}")
        print(f"channel_id={state.channel_id or 0}")
        print(f"current_number={state.current_number}")
        print(f"last_user_id={state.last_user_id or 0}")
        return
    if args.count_command == "set":
        existing = await ctx.counting.get(guild_id)
        channel_id = existing.channel_id if existing is not None else None
        is_enabled = existing.is_enabled if existing is not None else channel_id is not None
        await ctx.counting.upsert(
            guild_id=guild_id,
            channel_id=channel_id,
            current_number=max(0, int(args.number)),
            last_user_id=None,
            is_enabled=is_enabled,
            pending_restore=False,
        )
        print(f"guild_id={guild_id}")
        print(f"current_number={max(0, int(args.number))}")
        return
    raise RuntimeError(f"Unsupported count command: {args.count_command}")


async def handle_throne(ctx: OperationsContext, args: argparse.Namespace) -> None:
    if args.throne_command == "refresh":
        print("tracking_mode=webhook_only")
        print("legacy_polling=disabled")
        print("action=Use Throne webhook integrations and run a test webhook.")
        return

    if args.throne_command == "status":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        handle = (getattr(args, "handle", None) or "").strip()
        if handle:
            creator = await ctx.throne_creators.get_by_handle(guild_id, handle)
            if creator is None:
                print(f"guild_id={guild_id}")
                print(f"handle=@{handle}")
                print("found=false")
                return
            print(f"guild_id={guild_id}")
            print(f"handle=@{creator.throne_handle}")
            print("found=true")
            print(f"creator_id={creator.throne_creator_id}")
            print(f"discord_user_id={creator.discord_user_id}")
            print(f"tracking_mode={creator.tracking_mode}")
            print(f"webhook_connected_at={creator.webhook_connected_at or ''}")
            print(f"last_successful_event_at={creator.last_successful_event_at or ''}")
            print(f"setup_verified_at={creator.setup_verified_at or ''}")
            return

        creators = await ctx.throne_creators.list_for_guild(guild_id)
        setup_verified = sum(1 for row in creators if row.setup_verified_at is not None)
        print(f"guild_id={guild_id}")
        print(f"registered_creators={len(creators)}")
        print(f"setup_verified={setup_verified}")
        return

    if args.throne_command in {"dommes", "list"}:
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        creators = await ctx.throne_creators.list_for_guild(guild_id)
        print(f"guild_id={guild_id}")
        print(f"rows={len(creators)}")
        for row in creators:
            print(
                f"handle=@{row.throne_handle} creator_id={row.throne_creator_id} "
                f"discord_user_id={row.discord_user_id} mode={row.tracking_mode} "
                f"last_successful_event_at={row.last_successful_event_at or ''}"
            )
        return

    if args.throne_command == "search":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        user_id = parse_user_ref(str(args.user_ref))
        if user_id is None:
            raise RuntimeError("Could not parse user ref. Use a mention like <@123> or raw Discord user ID.")
        creator = await ctx.throne_creators.get_by_user_id(guild_id, user_id)
        if creator is None:
            print(f"guild_id={guild_id}")
            print(f"user_id={user_id}")
            print("found=false")
            return
        latest_sends = await ctx.sends.list_sends_for_domme(guild_id, user_id, limit=1)
        latest = latest_sends[0] if latest_sends else None
        print(f"guild_id={guild_id}")
        print(f"user_id={user_id}")
        print("found=true")
        print(f"handle=@{creator.throne_handle}")
        print(f"creator_id={creator.throne_creator_id}")
        print(f"tracking_mode={creator.tracking_mode}")
        print(f"webhook_connected_at={creator.webhook_connected_at or ''}")
        print(f"last_successful_event_at={creator.last_successful_event_at or ''}")
        print(f"setup_verified_at={creator.setup_verified_at or ''}")
        if latest is not None:
            print(f"latest_send_id={latest.id}")
            print(f"latest_send_amount_cents={latest.amount_cents}")
            print(f"latest_send_sub_name={latest.sub_name or ''}")
            print(f"latest_send_at={latest.sent_at.isoformat()}")
        else:
            print("latest_send_id=0")
        return

    if args.throne_command == "webhook":
        command = getattr(args, "throne_webhook_command", None)
        if command != "refresh":
            raise RuntimeError(f"Unsupported throne webhook command: {command}")
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        user_id = parse_user_ref(str(args.user_ref))
        if user_id is None:
            raise RuntimeError("Could not parse user ref. Use a mention like <@123> or raw Discord user ID.")
        creator = await ctx.throne_creators.get_by_user_id(guild_id, user_id)
        if creator is None:
            print(f"guild_id={guild_id}")
            print(f"user_id={user_id}")
            print("found=false")
            return
        new_secret = secrets.token_urlsafe(32)
        updated = await ctx.throne_creators.upsert_for_user(
            guild_id=creator.guild_id,
            domme_id=creator.domme_id,
            discord_user_id=creator.discord_user_id,
            throne_handle=creator.throne_handle,
            throne_creator_id=creator.throne_creator_id,
            hide_own_purchases=creator.hide_own_purchases,
            tracking_mode=creator.tracking_mode,
            webhook_secret=new_secret,
            webhook_secret_hash=hash_webhook_secret(new_secret),
        )
        print(f"guild_id={guild_id}")
        print(f"user_id={user_id}")
        print("found=true")
        print("rotated=true")
        print(f"creator_id={updated.throne_creator_id}")
        base = (os.getenv("THRONE_WEBHOOK_BASE_URL") or "").strip().rstrip("/")
        if base:
            print(f"webhook_url={base}/throne/webhook/{updated.throne_creator_id}/{new_secret}")
        else:
            print("webhook_url=")
        return

    if args.throne_command == "addsend":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        user_id = parse_user_ref(str(args.user_ref))
        if user_id is None:
            raise RuntimeError("Could not parse user ref. Use a mention like <@123> or raw Discord user ID.")
        if float(args.amount) <= 0:
            raise RuntimeError("Amount must be greater than zero.")
        domme = await ctx.dommes.get_by_user_id(guild_id, user_id)
        send = await ctx.send_service.record_manual_send(
            guild_id=guild_id,
            domme_id=domme.id if domme is not None else None,
            domme_user_id=user_id,
            amount_cents=dollars_to_cents(float(args.amount)),
            currency=(args.currency or "USD").strip().upper(),
            method=(args.method or "manual").strip() or "manual",
            note=(args.note or "").strip() or None,
            sub_name=(args.sub_name or "").strip() or None,
            source="manual:robctl_throne_addsend",
        )
        if send is None:
            print("recorded=false")
            return
        print("recorded=true")
        print(f"send_id={send.id}")
        print(f"public_send_id={send.public_send_id}")
        print(f"status={send.discord_post_status}")
        return

    if args.throne_command == "addsub":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        user_id = parse_user_ref(str(args.user_ref))
        if user_id is None:
            raise RuntimeError("Could not parse user ref. Use a mention like <@123> or raw Discord user ID.")
        cleaned_name = " ".join(str(args.name).strip().split())
        if not cleaned_name:
            raise RuntimeError("A Sub sending name is required.")
        sub = await ctx.subs.upsert(
            guild_id=guild_id,
            discord_user_id=user_id,
            send_name=cleaned_name,
        )
        print(f"guild_id={guild_id}")
        print(f"user_id={sub.discord_user_id}")
        print(f"sub_id={sub.id}")
        print(f"send_name={sub.send_name}")
        return

    if args.throne_command == "adddomme":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        user_id = parse_user_ref(str(args.user_ref))
        if user_id is None:
            raise RuntimeError("Could not parse user ref. Use a mention like <@123> or raw Discord user ID.")
        result = await ctx.registration_service.register_domme(
            guild_id=guild_id,
            discord_user_id=user_id,
            throne_input=str(args.throne_input),
        )
        print(f"guild_id={guild_id}")
        print(f"user_id={user_id}")
        print(f"domme_id={result.domme.id}")
        print(f"throne_handle=@{result.creator.throne_handle}")
        print(f"creator_id={result.creator.throne_creator_id}")
        print(f"tracking_mode={result.creator.tracking_mode}")
        print(f"webhook_url={result.webhook_url or ''}")
        return

    if args.throne_command == "subs":
        guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
        subs = await ctx.subs.list_for_guild(guild_id)
        print(f"guild_id={guild_id}")
        print(f"rows={len(subs)}")
        for row in subs:
            print(
                f"discord_user_id={row.discord_user_id} send_name={row.send_name} "
                f"registered_at={row.registered_at.isoformat()}"
            )
        return
    if args.throne_command == "invalidate-test-sends":
        usernames = list(ctx.settings.throne_test_gifter_usernames)
        updated = await ctx.sends.mark_known_test_sends(test_gifter_usernames=usernames)
        print(f"updated={updated}")
        print(f"usernames={','.join(usernames)}")
        return
    raise RuntimeError(f"Unsupported throne command: {args.throne_command}")


async def handle_inactivity(ctx: OperationsContext, args: argparse.Namespace) -> None:
    guild_id = await resolve_guild_id(ctx, getattr(args, "guild_id", None))
    key = f"inactivity:{guild_id}:enabled"
    if args.inactivity_command == "status":
        enabled = await ctx.bot_state.get_bool(
            key,
            default=ctx.settings.inactivity_enabled_default,
        )
        print(f"guild_id={guild_id}")
        print(f"enabled={'true' if enabled else 'false'}")
        return
    if args.inactivity_command == "on":
        await ctx.bot_state.set_value(key, "true")
        print(f"guild_id={guild_id}")
        print("enabled=true")
        return
    if args.inactivity_command == "off":
        await ctx.bot_state.set_value(key, "false")
        print(f"guild_id={guild_id}")
        print("enabled=false")
        return
    raise RuntimeError(f"Unsupported inactivity command: {args.inactivity_command}")


async def handle_blacklist(ctx: OperationsContext, args: argparse.Namespace) -> None:
    if args.blacklist_command == "add":
        await ctx.blacklist.add(
            discord_user_id=int(args.discord_user_id),
            reason=(args.reason or "manual").strip() or "manual",
            created_by=args.created_by,
        )
        print(f"discord_user_id={int(args.discord_user_id)}")
        print("updated=1")
        return
    if args.blacklist_command == "remove":
        await ctx.blacklist.remove(int(args.discord_user_id))
        print(f"discord_user_id={int(args.discord_user_id)}")
        print("updated=1")
        return
    if args.blacklist_command == "list":
        rows = await ctx.blacklist.list_entries(limit=max(1, int(args.limit)))
        print(f"rows={len(rows)}")
        for user_id, reason, created_by, created_at in rows:
            print(
                f"discord_user_id={user_id} reason={reason or ''} "
                f"created_by={created_by or 0} created_at={created_at.isoformat()}"
            )
        return
    raise RuntimeError(f"Unsupported blacklist command: {args.blacklist_command}")


async def handle_sends(ctx: OperationsContext, args: argparse.Namespace) -> None:
    if args.sends_command == "list":
        guild_id = getattr(args, "guild_id", None)
        if guild_id is None:
            try:
                guild_id = await resolve_guild_id(ctx, None)
            except RuntimeError:
                guild_id = None
        rows = await ctx.sends.list_sends(
            guild_id=guild_id,
            status=args.status,
            limit=max(1, int(args.limit)),
        )
        print(f"status={args.status}")
        print(f"guild_id={guild_id if guild_id is not None else 'all'}")
        print(f"rows={len(rows)}")
        for send in rows:
            print(
                f"id={send.id} guild_id={send.guild_id} domme_user_id={send.domme_user_id} "
                f"sub_user_id={send.sub_user_id or 0} amount_cents={send.amount_cents} "
                f"status={send.discord_post_status} is_private={send.is_private} is_test_send={send.is_test_send}"
            )
        return
    if args.sends_command == "backfill-public-ids":
        updated = await ctx.sends.backfill_public_send_ids()
        print(f"updated={updated}")
        return
    if args.sends_command == "mark-posted":
        updated = await ctx.sends.force_mark_posted(args.send_id)
        print(f"send_id={args.send_id}")
        print(f"updated={updated}")
        return
    raise RuntimeError(f"Unsupported sends command: {args.sends_command}")


async def main_async() -> None:
    parser = build_parser()
    args = parser.parse_args()
    ctx = await create_context()
    try:
        if args.command == "status":
            await handle_status(ctx)
        elif args.command == "maintenance":
            await handle_maintenance(ctx, args)
        elif args.command == "queue":
            await handle_queue(ctx, args)
        elif args.command == "leaderboard":
            await handle_leaderboard(ctx, args)
        elif args.command == "count":
            await handle_count(ctx, args)
        elif args.command == "throne":
            await handle_throne(ctx, args)
        elif args.command == "inactivity":
            await handle_inactivity(ctx, args)
        elif args.command == "blacklist":
            await handle_blacklist(ctx, args)
        elif args.command == "sends":
            await handle_sends(ctx, args)
        else:
            raise RuntimeError(f"Unsupported command: {args.command}")
    finally:
        await ctx.throne_service.close()
        await ctx.database.close()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
