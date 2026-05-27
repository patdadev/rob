from __future__ import annotations

import os
import secrets
from functools import wraps
from urllib.parse import urlencode, urlparse

import httpx
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count
from django.db.utils import DatabaseError, OperationalError, ProgrammingError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .bot_ops import BotOpsClient
from .forms import (
    GuildActionForm,
    MaintenanceToggleForm,
    PublicLeaderboardCreateForm,
    PublicLeaderboardUpdateForm,
    ServiceLogForm,
)
from .log_reader import read_service_logs
from .models import (
    Domme,
    GuildSettings,
    PublicLeaderboard,
    SchemaMigration,
    Send,
    SendRequest,
    Sub,
)
from .services import audit_action, get_service_status, redacted_env_pairs


def _discord_id_from_session(request: HttpRequest) -> int | None:
    raw = request.session.get("portal_discord_user_id")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _is_superadmin(discord_user_id: int | None) -> bool:
    if discord_user_id is None:
        return False
    return discord_user_id in set(settings.ROB_PORTAL_SUPERADMIN_USER_IDS)


def _safe_next_path(value: str | None) -> str:
    if not value:
        return "/portal/dashboard/"
    parsed = urlparse(value)
    if parsed.netloc:
        return "/portal/dashboard/"
    if not value.startswith("/portal/"):
        return "/portal/dashboard/"
    return value


def _portal_context(request: HttpRequest, *, title: str) -> dict:
    return {
        "title": title,
        "portal_user_display": request.session.get("portal_discord_display_name") or request.user.get_username(),
    }


def _oauth_configured() -> bool:
    return bool(settings.DISCORD_CLIENT_ID and settings.DISCORD_CLIENT_SECRET and settings.DISCORD_REDIRECT_URI)


def _build_discord_authorize_url(*, state: str) -> str:
    params = urlencode(
        {
            "client_id": settings.DISCORD_CLIENT_ID,
            "redirect_uri": settings.DISCORD_REDIRECT_URI,
            "response_type": "code",
            "scope": settings.DISCORD_OAUTH_SCOPES,
            "state": state,
        }
    )
    return f"{settings.DISCORD_API_BASE}/oauth2/authorize?{params}"


def _discord_exchange_code(code: str) -> str:
    response = httpx.post(
        f"{settings.DISCORD_API_BASE}/oauth2/token",
        data={
            "client_id": settings.DISCORD_CLIENT_ID,
            "client_secret": settings.DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.DISCORD_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Discord OAuth response did not include access_token.")
    return access_token


def _discord_fetch_identity(access_token: str) -> dict:
    response = httpx.get(
        f"{settings.DISCORD_API_BASE}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Discord OAuth identity response was invalid.")
    return payload


def _sync_django_user(discord_identity: dict):
    user_id = str(discord_identity.get("id", "")).strip()
    if not user_id.isdigit():
        raise RuntimeError("Discord user id was missing or invalid.")

    username = f"discord_{user_id}"
    display_name = (
        str(discord_identity.get("global_name") or "").strip()
        or str(discord_identity.get("username") or "").strip()
        or username
    )

    User = get_user_model()
    user, _created = User.objects.get_or_create(username=username)
    user.first_name = display_name
    user.is_staff = True
    user.is_active = True
    user.is_superuser = int(user_id) == settings.ROB_PORTAL_OWNER_USER_ID
    user.set_unusable_password()
    user.save(update_fields=["first_name", "is_staff", "is_active", "is_superuser", "password"])
    return user


def superadmin_required(view_func):
    @wraps(view_func)
    def wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('portal_login')}?next={request.get_full_path()}")
        discord_id = _discord_id_from_session(request)
        if not _is_superadmin(discord_id):
            return render(
                request,
                "rob_admin/forbidden.html",
                {
                    **_portal_context(request, title="Access denied"),
                    "message": "Your Discord account is not allowed to access this portal.",
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapped


@require_GET
def admin_login_redirect(request: HttpRequest) -> HttpResponse:
    next_url = _safe_next_path(request.GET.get("next"))
    return redirect(f"{reverse('portal_login')}?next={next_url}")


@require_GET
def portal_home(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("portal_dashboard")
    return redirect("portal_login")


@require_GET
def portal_login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(_safe_next_path(request.GET.get("next")))
    return render(
        request,
        "rob_admin/login.html",
        {
            "title": "Rob Portal Login",
            "oauth_configured": _oauth_configured(),
            "next": _safe_next_path(request.GET.get("next")),
        },
    )


@require_POST
def portal_logout(request: HttpRequest) -> HttpResponse:
    audit_action(request=request, action="portal_logout")
    auth_logout(request)
    return redirect("portal_login")


@require_GET
def discord_auth_start(request: HttpRequest) -> HttpResponse:
    if not _oauth_configured():
        return render(
            request,
            "rob_admin/error.html",
            {"title": "Portal OAuth Not Configured", "message": "Discord OAuth is not configured yet."},
            status=500,
        )
    next_path = _safe_next_path(request.GET.get("next"))
    state = secrets.token_urlsafe(24)
    request.session["portal_oauth_state"] = state
    request.session["portal_oauth_next"] = next_path
    return redirect(_build_discord_authorize_url(state=state))


@require_GET
def discord_auth_callback(request: HttpRequest) -> HttpResponse:
    expected_state = request.session.get("portal_oauth_state")
    received_state = request.GET.get("state")
    if not expected_state or expected_state != received_state:
        return render(
            request,
            "rob_admin/error.html",
            {"title": "OAuth Error", "message": "State verification failed. Please try signing in again."},
            status=400,
        )

    code = request.GET.get("code")
    if not code:
        return render(
            request,
            "rob_admin/error.html",
            {"title": "OAuth Error", "message": "Missing authorization code from Discord."},
            status=400,
        )

    try:
        access_token = _discord_exchange_code(code)
        identity = _discord_fetch_identity(access_token)
    except Exception:
        return render(
            request,
            "rob_admin/error.html",
            {"title": "OAuth Error", "message": "Discord login failed while fetching your identity."},
            status=502,
        )

    discord_id_raw = str(identity.get("id", "")).strip()
    discord_id = int(discord_id_raw) if discord_id_raw.isdigit() else None
    display_name = (
        str(identity.get("global_name") or "").strip()
        or str(identity.get("username") or "").strip()
        or "Unknown User"
    )
    if not _is_superadmin(discord_id):
        audit_action(
            request=None,
            action="portal_login_denied",
            target_type="discord_user",
            target_id=discord_id_raw or "unknown",
            metadata={"display_name": display_name},
        )
        return render(
            request,
            "rob_admin/forbidden.html",
            {"title": "Access denied", "message": "This portal is restricted to configured superadmin users only."},
            status=403,
        )

    user = _sync_django_user(identity)
    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["portal_discord_user_id"] = discord_id
    request.session["portal_discord_display_name"] = display_name
    audit_action(
        request=request,
        action="portal_login_success",
        target_type="discord_user",
        target_id=str(discord_id),
    )
    return redirect(_safe_next_path(request.session.pop("portal_oauth_next", "/portal/dashboard/")))


def _safe_count(model) -> int:
    try:
        return int(model.objects.count())
    except (DatabaseError, OperationalError, ProgrammingError):
        return 0


def _build_bot_ops_client() -> BotOpsClient:
    return BotOpsClient(
        host=settings.ROB_OPS_HOST,
        port=settings.ROB_OPS_PORT,
        secret=settings.ROB_OPS_SECRET,
    )


@login_required
@superadmin_required
@require_GET
def dashboard_view(request: HttpRequest) -> HttpResponse:
    status_rows = []
    for service_name in settings.ROB_PORTAL_ALLOWED_SERVICES:
        status_rows.append(get_service_status(service_name, allowed_services=settings.ROB_PORTAL_ALLOWED_SERVICES))

    bot_ops_health = {"health": "Unknown", "details": "Unavailable"}
    try:
        health = _build_bot_ops_client().health()
        if health.ok:
            bot_ops_health = {"health": "Healthy", "details": "Connected"}
        else:
            bot_ops_health = {"health": "Warning", "details": f"HTTP {health.status_code}"}
    except Exception:
        bot_ops_health = {"health": "Unknown", "details": "Connection failed"}

    try:
        send_status_rows = (
            Send.objects.values("discord_post_status").annotate(count=Count("id")).order_by("discord_post_status")
        )
        send_status = {row["discord_post_status"]: int(row["count"]) for row in send_status_rows}
    except (DatabaseError, OperationalError, ProgrammingError):
        send_status = {}
    try:
        latest_row = SchemaMigration.objects.order_by("-applied_at").first()
        latest_migration = latest_row.version if latest_row else "unknown"
    except (DatabaseError, OperationalError, ProgrammingError):
        latest_migration = "unknown"
    try:
        recent_failed = list(Send.objects.filter(discord_post_status="failed").order_by("-created_at")[:10])
    except (DatabaseError, OperationalError, ProgrammingError):
        recent_failed = []

    return render(
        request,
        "rob_admin/dashboard.html",
        {
            **_portal_context(request, title="Dashboard"),
            "status_rows": status_rows,
            "bot_ops_health": bot_ops_health,
            "metrics": {
                "dommes": _safe_count(Domme),
                "subs": _safe_count(Sub),
                "sends": _safe_count(Send),
                "send_requests": _safe_count(SendRequest),
                "public_leaderboards": _safe_count(PublicLeaderboard),
                "pending_sends": send_status.get("pending", 0),
                "failed_sends": send_status.get("failed", 0),
                "queued_maintenance_sends": send_status.get("queued_maintenance", 0),
            },
            "latest_migration": latest_migration,
            "recent_failed_sends": recent_failed,
        },
    )


@login_required
@superadmin_required
@require_GET
def services_view(request: HttpRequest) -> HttpResponse:
    statuses = [
        get_service_status(service_name, allowed_services=settings.ROB_PORTAL_ALLOWED_SERVICES)
        for service_name in settings.ROB_PORTAL_ALLOWED_SERVICES
    ]
    return render(
        request,
        "rob_admin/services.html",
        {
            **_portal_context(request, title="Services"),
            "statuses": statuses,
            "service_actions_enabled": settings.ROB_PORTAL_ENABLE_SERVICE_ACTIONS,
        },
    )


@login_required
@superadmin_required
@require_http_methods(["GET", "POST"])
def logs_view(request: HttpRequest) -> HttpResponse:
    logs = None
    if request.method == "POST":
        form = ServiceLogForm(request.POST, allowed_services=settings.ROB_PORTAL_ALLOWED_SERVICES)
        if form.is_valid():
            try:
                logs = read_service_logs(
                    form.cleaned_data["service"],
                    lines=form.cleaned_data["lines"],
                    allowed_services=settings.ROB_PORTAL_ALLOWED_SERVICES,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        form = ServiceLogForm(allowed_services=settings.ROB_PORTAL_ALLOWED_SERVICES)
    return render(
        request,
        "rob_admin/logs.html",
        {
            **_portal_context(request, title="Logs"),
            "form": form,
            "logs": logs,
        },
    )


def _fetch_single_value(sql: str, *params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return row[0]


@login_required
@superadmin_required
@require_GET
def database_view(request: HttpRequest) -> HttpResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            current_database, current_user = cursor.fetchone()
    except (DatabaseError, OperationalError, ProgrammingError):
        current_database = connection.settings_dict.get("NAME", "unknown")
        current_user = connection.settings_dict.get("USER", "unknown")

    table_counts: list[tuple[str, int | str]] = []
    for table_name in (
        "guild_settings",
        "dommes",
        "subs",
        "sends",
        "send_requests",
        "throne_creators",
        "public_leaderboards",
        "leaderboard_message",
        "bot_state",
        "counting_state",
        "blacklist",
        "schema_migrations",
        "portal_audit_log",
    ):
        try:
            count_value = _fetch_single_value(f"SELECT COUNT(*) FROM {table_name}")
            table_counts.append((table_name, int(count_value or 0)))
        except Exception:
            table_counts.append((table_name, "n/a"))

    try:
        legacy_leaderboard_exists = bool(
            _fetch_single_value("SELECT to_regclass('public.leaderboard_messages') IS NOT NULL")
        )
    except (DatabaseError, OperationalError, ProgrammingError):
        legacy_leaderboard_exists = False
    try:
        legacy_wishlist_exists = bool(
            _fetch_single_value("SELECT to_regclass('public.throne_wishlist_items') IS NOT NULL")
        )
    except (DatabaseError, OperationalError, ProgrammingError):
        legacy_wishlist_exists = False
    try:
        has_009 = SchemaMigration.objects.filter(version="009_domme_public_display_names").exists()
    except (DatabaseError, OperationalError, ProgrammingError):
        has_009 = False
    try:
        dommes_name_columns = int(
            _fetch_single_value(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'dommes'
                  AND column_name IN ('public_display_name', 'public_display_name_updated_at')
                """
            )
            or 0
        )
    except (DatabaseError, OperationalError, ProgrammingError):
        dommes_name_columns = 0
    migration_warning = (
        "Migration 009 is not recorded, but dommes public display-name columns already exist."
        if (not has_009 and dommes_name_columns == 2)
        else None
    )

    ownership_rows: list[tuple[str, str]] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tablename, tableowner
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
            ownership_rows = [(str(name), str(owner)) for name, owner in cursor.fetchall()]
    except Exception:
        ownership_rows = []

    try:
        migrations = list(SchemaMigration.objects.order_by("version"))
    except (DatabaseError, OperationalError, ProgrammingError):
        migrations = []
    return render(
        request,
        "rob_admin/database.html",
        {
            **_portal_context(request, title="Database"),
            "current_database": current_database,
            "current_user": current_user,
            "table_counts": table_counts,
            "migrations": migrations,
            "legacy_leaderboard_exists": legacy_leaderboard_exists,
            "legacy_wishlist_exists": legacy_wishlist_exists,
            "migration_warning": migration_warning,
            "ownership_rows": ownership_rows,
        },
    )


def _parse_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on", "y"}:
        return True
    if lowered in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _fetch_top_leaderboard_rows(limit: int = 10) -> list[dict]:
    include_test = _parse_bool_env("THRONE_PARSE_TEST_SENDS_AS_REAL_SENDS", False)
    where_test = "" if include_test else "AND s.is_test_send = false"
    query = f"""
        SELECT
            d.guild_id,
            d.discord_user_id,
            COALESCE(SUM(s.amount_cents), 0) AS total_cents,
            COUNT(s.id) AS send_count
        FROM dommes d
        LEFT JOIN sends s
            ON s.guild_id = d.guild_id
           AND s.domme_user_id = d.discord_user_id
           AND s.discord_post_status = 'posted'
           AND s.is_private = false
           {where_test}
        GROUP BY d.guild_id, d.discord_user_id
        ORDER BY total_cents DESC, send_count DESC, d.discord_user_id ASC
        LIMIT %s
    """
    with connection.cursor() as cursor:
        cursor.execute(query, [limit])
        rows = cursor.fetchall()
    output = []
    for guild_id, user_id, total_cents, send_count in rows:
        output.append(
            {
                "guild_id": int(guild_id),
                "user_id": int(user_id),
                "total_cents": int(total_cents or 0),
                "send_count": int(send_count or 0),
            }
        )
    return output


@login_required
@superadmin_required
@require_http_methods(["GET", "POST"])
def leaderboards_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        intent = request.POST.get("intent", "")
        if intent == "refresh_names":
            form = GuildActionForm(request.POST)
            if form.is_valid():
                guild_id = int(form.cleaned_data["guild_id"])
                response = _build_bot_ops_client().refresh_public_names(guild_id)
                if response.ok:
                    messages.success(request, f"Requested display-name refresh for guild {guild_id}.")
                    audit_action(
                        request=request,
                        action="refresh_public_names",
                        target_type="guild",
                        target_id=str(guild_id),
                        metadata={"status_code": response.status_code},
                    )
                else:
                    messages.error(request, f"Refresh failed: HTTP {response.status_code}")
            else:
                messages.error(request, "Invalid guild ID for refresh action.")

        elif intent == "refresh_leaderboard":
            form = GuildActionForm(request.POST)
            if form.is_valid():
                guild_id = int(form.cleaned_data["guild_id"])
                response = _build_bot_ops_client().refresh_leaderboard(guild_id)
                if response.ok:
                    messages.success(request, f"Requested leaderboard refresh for guild {guild_id}.")
                    audit_action(
                        request=request,
                        action="refresh_leaderboard",
                        target_type="guild",
                        target_id=str(guild_id),
                        metadata={"status_code": response.status_code},
                    )
                else:
                    messages.error(request, f"Refresh failed: HTTP {response.status_code}")
            else:
                messages.error(request, "Invalid guild ID for leaderboard refresh.")

        elif intent == "toggle_maintenance":
            form = MaintenanceToggleForm(request.POST)
            if form.is_valid():
                enabled = bool(form.cleaned_data.get("enabled"))
                reason = form.cleaned_data.get("reason") or ""
                response = _build_bot_ops_client().set_maintenance(enabled=enabled, reason=reason)
                if response.ok:
                    messages.success(request, f"Maintenance mode {'enabled' if enabled else 'disabled'}.")
                    audit_action(
                        request=request,
                        action="toggle_maintenance",
                        target_type="bot_state",
                        target_id="maintenance",
                        metadata={"enabled": enabled},
                    )
                else:
                    messages.error(request, f"Maintenance toggle failed: HTTP {response.status_code}")
            else:
                messages.error(request, "Invalid maintenance form payload.")

        elif intent == "create_public_leaderboard":
            form = PublicLeaderboardCreateForm(request.POST)
            if form.is_valid():
                token = secrets.token_urlsafe(32)
                PublicLeaderboard.objects.create(
                    guild_id=form.cleaned_data["guild_id"],
                    public_token=token,
                    title=form.cleaned_data["title"],
                    enabled=True,
                    theme=form.cleaned_data["theme"],
                    created_at=timezone.now(),
                    updated_at=timezone.now(),
                )
                messages.success(request, "Created public leaderboard URL.")
                audit_action(
                    request=request,
                    action="create_public_leaderboard",
                    target_type="guild",
                    target_id=str(form.cleaned_data["guild_id"]),
                    metadata={"theme": form.cleaned_data["theme"]},
                )
            else:
                messages.error(request, "Invalid create-public-leaderboard form.")

        elif intent == "update_public_leaderboard":
            form = PublicLeaderboardUpdateForm(request.POST)
            if form.is_valid():
                row_id = int(form.cleaned_data["row_id"])
                action_value = form.cleaned_data["action"]
                row = PublicLeaderboard.objects.filter(id=row_id).first()
                if row is None:
                    messages.error(request, "Public leaderboard row not found.")
                else:
                    if action_value == "enable":
                        row.enabled = True
                    elif action_value == "disable":
                        row.enabled = False
                    elif action_value == "rotate":
                        row.public_token = secrets.token_urlsafe(32)
                    row.updated_at = timezone.now()
                    row.save(update_fields=["enabled", "public_token", "updated_at"])
                    messages.success(request, f"Public leaderboard row updated via {action_value}.")
                    audit_action(
                        request=request,
                        action=f"public_leaderboard_{action_value}",
                        target_type="public_leaderboard",
                        target_id=str(row.id),
                        metadata={"guild_id": row.guild_id},
                    )
            else:
                messages.error(request, "Invalid public leaderboard update request.")

    rows = list(PublicLeaderboard.objects.order_by("-updated_at", "-created_at"))
    total_dommes = Domme.objects.count()
    with_name = Domme.objects.exclude(public_display_name__isnull=True).exclude(public_display_name="").count()
    without_name = max(0, total_dommes - with_name)
    top_rows = _fetch_top_leaderboard_rows(10)
    guild_ids = list(GuildSettings.objects.order_by("guild_id").values_list("guild_id", flat=True))
    return render(
        request,
        "rob_admin/leaderboards.html",
        {
            **_portal_context(request, title="Leaderboards"),
            "rows": rows,
            "guild_ids": guild_ids,
            "coverage": {
                "total_dommes": total_dommes,
                "with_public_display_name": with_name,
                "without_public_display_name": without_name,
            },
            "top_rows": top_rows,
        },
    )


@login_required
@superadmin_required
@require_GET
def sends_view(request: HttpRequest) -> HttpResponse:
    queryset = Send.objects.all().order_by("-created_at")
    guild_id = request.GET.get("guild_id", "").strip()
    status = request.GET.get("status", "").strip()
    source = request.GET.get("source", "").strip()
    is_test_send = request.GET.get("is_test_send", "").strip()
    is_private = request.GET.get("is_private", "").strip()

    if guild_id.isdigit():
        queryset = queryset.filter(guild_id=int(guild_id))
    if status:
        queryset = queryset.filter(discord_post_status=status)
    if source:
        queryset = queryset.filter(source=source)
    if is_test_send in {"true", "false"}:
        queryset = queryset.filter(is_test_send=(is_test_send == "true"))
    if is_private in {"true", "false"}:
        queryset = queryset.filter(is_private=(is_private == "true"))

    status_counts_rows = Send.objects.values("discord_post_status").annotate(count=Count("id")).order_by(
        "discord_post_status"
    )
    status_counts = {row["discord_post_status"]: int(row["count"]) for row in status_counts_rows}
    recent_sends = list(queryset[:100])
    failed_sends = list(Send.objects.filter(discord_post_status="failed").order_by("-created_at")[:25])
    pending_sends = list(Send.objects.filter(discord_post_status="pending").order_by("-created_at")[:25])
    queued_maintenance = list(
        Send.objects.filter(discord_post_status="queued_maintenance").order_by("-created_at")[:25]
    )

    return render(
        request,
        "rob_admin/sends.html",
        {
            **_portal_context(request, title="Sends"),
            "status_counts": status_counts,
            "recent_sends": recent_sends,
            "failed_sends": failed_sends,
            "pending_sends": pending_sends,
            "queued_maintenance_sends": queued_maintenance,
            "active_filters": {
                "guild_id": guild_id,
                "status": status,
                "source": source,
                "is_test_send": is_test_send,
                "is_private": is_private,
            },
        },
    )


@login_required
@superadmin_required
@require_GET
def settings_view(request: HttpRequest) -> HttpResponse:
    env_summary = redacted_env_pairs(
        {
            "APP_ENV": os.getenv("APP_ENV", ""),
            "ROB_PORTAL_ENV": settings.ROB_PORTAL_ENV,
            "ROB_PORTAL_ENABLED": str(settings.ROB_PORTAL_ENABLED),
            "ROB_PORTAL_BASE_URL": settings.ROB_PORTAL_BASE_URL,
            "ROB_OPS_HOST": settings.ROB_OPS_HOST,
            "ROB_OPS_PORT": str(settings.ROB_OPS_PORT),
            "ROB_OPS_SECRET": settings.ROB_OPS_SECRET,
            "PUBLIC_LEADERBOARD_CACHE_SECONDS": os.getenv("PUBLIC_LEADERBOARD_CACHE_SECONDS", ""),
            "SEND_QUEUE_LOOP_SECONDS": os.getenv("SEND_QUEUE_LOOP_SECONDS", ""),
            "THRONE_PARSE_TEST_SENDS_AS_REAL_SENDS": os.getenv("THRONE_PARSE_TEST_SENDS_AS_REAL_SENDS", ""),
            "PORTAL_DATABASE_URL": os.getenv("PORTAL_DATABASE_URL", ""),
            "DATABASE_URL": os.getenv("DATABASE_URL", ""),
            "DISCORD_CLIENT_ID": settings.DISCORD_CLIENT_ID,
            "DISCORD_CLIENT_SECRET": settings.DISCORD_CLIENT_SECRET,
            "DISCORD_REDIRECT_URI": settings.DISCORD_REDIRECT_URI,
        }
    )
    guild_settings = list(GuildSettings.objects.order_by("guild_id"))
    return render(
        request,
        "rob_admin/settings.html",
        {
            **_portal_context(request, title="Settings"),
            "env_summary": env_summary,
            "guild_settings_rows": guild_settings,
            "superadmin_user_ids": settings.ROB_PORTAL_SUPERADMIN_USER_IDS,
            "service_actions_enabled": settings.ROB_PORTAL_ENABLE_SERVICE_ACTIONS,
        },
    )
