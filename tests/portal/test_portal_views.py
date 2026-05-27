from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, override_settings

from rob_admin import views


def _attach_session(request) -> None:
    middleware = SessionMiddleware(lambda _req: None)
    middleware.process_request(request)
    request.session.save()


def _unwrap_view(func):
    current = func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


def test_portal_disabled_returns_404():
    client = Client()
    with override_settings(ROB_PORTAL_ENABLED=False):
        response = client.get("/portal/login/")
    assert response.status_code == 404
    assert b"disabled" in response.content.lower()


def test_django_admin_requires_authentication_redirects_to_portal_login():
    client = Client()
    response = client.get("/portal/admin/")
    assert response.status_code == 302
    assert "/portal/admin/login/" in response["Location"]


def test_discord_oauth_callback_allows_non_superadmin_as_user(monkeypatch):
    request = RequestFactory().get("/portal/auth/discord/callback/?code=abc&state=state-1")
    request.user = AnonymousUser()
    _attach_session(request)
    request.session["portal_oauth_state"] = "state-1"

    monkeypatch.setattr(views, "_discord_exchange_code", lambda _code: "token")
    monkeypatch.setattr(views, "_discord_fetch_identity", lambda _token: {"id": "999", "username": "nope"})
    monkeypatch.setattr(views, "_sync_django_user", lambda _identity: SimpleNamespace(get_username=lambda: "discord_999"))
    monkeypatch.setattr(views, "auth_login", lambda *_args, **_kwargs: None)

    response = views.discord_auth_callback(request)
    assert response.status_code == 302
    assert response["Location"] == "/portal/dashboard/"


def test_discord_oauth_callback_allows_superadmin(monkeypatch):
    request = RequestFactory().get("/portal/auth/discord/callback/?code=abc&state=state-2")
    request.user = AnonymousUser()
    _attach_session(request)
    request.session["portal_oauth_state"] = "state-2"
    request.session["portal_oauth_next"] = "/portal/admin/"

    monkeypatch.setattr(views, "_discord_exchange_code", lambda _code: "token")
    monkeypatch.setattr(
        views,
        "_discord_fetch_identity",
        lambda _token: {
            "id": "1299308718009356289",
            "username": "pat",
            "global_name": "Pat",
        },
    )
    monkeypatch.setattr(views, "_sync_django_user", lambda _identity: SimpleNamespace(get_username=lambda: "discord_1"))
    monkeypatch.setattr(views, "auth_login", lambda *_args, **_kwargs: None)

    response = views.discord_auth_callback(request)
    assert response.status_code == 302
    assert response["Location"] == "/portal/admin/"
    assert request.session["portal_discord_user_id"] == 1299308718009356289


def test_sync_django_user_sets_staff_and_superuser_flags(monkeypatch):
    class _FakeUser:
        def __init__(self):
            self.first_name = ""
            self.is_staff = False
            self.is_active = False
            self.is_superuser = False
            self.password = ""
            self.saved_update_fields = None

        def set_unusable_password(self):
            self.password = "!"

        def save(self, *, update_fields):
            self.saved_update_fields = update_fields

    fake_user = _FakeUser()

    class _FakeManager:
        def get_or_create(self, *, username):
            assert username == "discord_1299308718009356289"
            return fake_user, True

    class _FakeUserModel:
        objects = _FakeManager()

    monkeypatch.setattr(views, "get_user_model", lambda: _FakeUserModel)
    with override_settings(ROB_PORTAL_OWNER_USER_ID=1299308718009356289):
        user = views._sync_django_user(
            {
                "id": "1299308718009356289",
                "username": "pat",
                "global_name": "Pat",
            }
        )

    assert user is fake_user
    assert user.first_name == "Pat"
    assert user.is_staff is True
    assert user.is_active is True
    assert user.is_superuser is True
    assert user.password == "!"
    assert user.saved_update_fields is not None


def test_database_page_does_not_expose_raw_database_url(monkeypatch):
    request = RequestFactory().get("/portal/database/")
    request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "discord_1")
    _attach_session(request)
    request.session["portal_discord_user_id"] = 1299308718009356289
    request.session["portal_discord_display_name"] = "Pat"

    raw_view = _unwrap_view(views.database_view)
    response = raw_view(request)
    body = response.content.decode("utf-8")
    assert "postgresql://" not in body


def test_bot_ops_health_unavailable_does_not_crash_dashboard(monkeypatch):
    request = RequestFactory().get("/portal/dashboard/")
    request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "discord_1")
    _attach_session(request)
    request.session["portal_discord_user_id"] = 1299308718009356289
    request.session["portal_discord_display_name"] = "Pat"

    class _BrokenClient:
        def health(self):
            raise RuntimeError("offline")

    monkeypatch.setattr(views, "_build_bot_ops_client", lambda: _BrokenClient())
    raw_view = _unwrap_view(views.dashboard_view)
    response = raw_view(request)
    assert response.status_code == 200


def test_refresh_public_names_action_requires_superadmin():
    request = RequestFactory().post(
        "/portal/leaderboards/",
        data={"intent": "refresh_names", "guild_id": "123"},
    )
    request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "discord_2")
    _attach_session(request)
    request.session["portal_discord_user_id"] = 42
    response = views.leaderboards_view(request)
    assert response.status_code == 403


def test_leaderboard_actions_template_includes_csrf_tokens():
    repo_root = Path(__file__).resolve().parents[2]
    template_path = repo_root / "portal" / "rob_admin" / "templates" / "rob_admin" / "leaderboards.html"
    content = template_path.read_text(encoding="utf-8")
    assert "{% csrf_token %}" in content


def test_base_template_uses_post_logout_form_with_csrf():
    repo_root = Path(__file__).resolve().parents[2]
    template_path = repo_root / "portal" / "rob_admin" / "templates" / "rob_admin" / "base.html"
    content = template_path.read_text(encoding="utf-8")
    assert '<form method="post" action="/portal/logout/">' in content
    assert "{% csrf_token %}" in content
    assert '<a href="/portal/logout/">' not in content


def test_leaderboard_actions_reject_non_post_mutations():
    request = RequestFactory().put("/portal/leaderboards/")
    request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "discord_1")
    _attach_session(request)
    request.session["portal_discord_user_id"] = 1299308718009356289
    response = views.leaderboards_view(request)
    assert response.status_code == 405


def test_portal_logout_is_post_only():
    client = Client()
    get_response = client.get("/portal/logout/")
    assert get_response.status_code == 405

    post_response = client.post("/portal/logout/")
    assert post_response.status_code == 302
    assert post_response["Location"].endswith("/portal/login/")


def test_settings_page_does_not_expose_raw_secrets(monkeypatch):
    request = RequestFactory().get("/portal/settings/")
    request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "discord_1")
    _attach_session(request)
    request.session["portal_discord_user_id"] = 1299308718009356289
    request.session["portal_discord_display_name"] = "Pat"

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:db-secret-pass@localhost:5432/rob_dev")
    monkeypatch.setenv("PORTAL_DATABASE_URL", "postgresql://portal:portal-secret@localhost:5432/rob_dev")

    with override_settings(
        DISCORD_CLIENT_SECRET="discord-oauth-secret",
        ROB_OPS_SECRET="ops-bridge-secret",
    ):
        raw_view = _unwrap_view(views.settings_view)
        response = raw_view(request)

    body = response.content.decode("utf-8")
    assert "db-secret-pass" not in body
    assert "portal-secret" not in body
    assert "discord-oauth-secret" not in body
    assert "ops-bridge-secret" not in body
    assert "***" in body


def test_dashboard_separates_local_services_and_remote_bridge(monkeypatch):
    request = RequestFactory().get("/portal/dashboard/")
    request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "discord_1")
    _attach_session(request)
    request.session["portal_discord_user_id"] = 1299308718009356289

    class _HealthyClient:
        def health(self):
            return SimpleNamespace(ok=True, status_code=200, payload={"bot_user_id": "42"}, error=None)

    monkeypatch.setattr(views, "_build_bot_ops_client", lambda: _HealthyClient())
    raw_view = _unwrap_view(views.dashboard_view)
    response = raw_view(request)
    body = response.content.decode("utf-8")
    assert "Local Portal Host" in body
    assert "Remote Bot Bridge" in body
    assert "Bot user ID" in body


def test_dashboard_remote_bridge_403_shows_secret_warning(monkeypatch):
    request = RequestFactory().get("/portal/dashboard/")
    request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "discord_1")
    _attach_session(request)
    request.session["portal_discord_user_id"] = 1299308718009356289

    class _ForbiddenClient:
        def health(self):
            return SimpleNamespace(ok=False, status_code=403, payload={}, error="Forbidden - check ROB_OPS_SECRET")

    monkeypatch.setattr(views, "_build_bot_ops_client", lambda: _ForbiddenClient())
    raw_view = _unwrap_view(views.dashboard_view)
    response = raw_view(request)
    body = response.content.decode("utf-8")
    assert "Remote bot bridge: Unreachable" in body
    assert "Forbidden - check ROB_OPS_SECRET" in body


def test_services_page_explains_local_checks(monkeypatch):
    request = RequestFactory().get("/portal/services/")
    request.user = SimpleNamespace(is_authenticated=True, get_username=lambda: "discord_1")
    _attach_session(request)
    request.session["portal_discord_user_id"] = 1299308718009356289

    raw_view = _unwrap_view(views.services_view)
    response = raw_view(request)
    body = response.content.decode("utf-8")
    assert "service checks are local" in body.lower()
    assert "Bot Ops Bridge health" in body


def test_docs_include_split_server_bot_ops_guidance():
    repo_root = Path(__file__).resolve().parents[2]
    doc = (repo_root / "docs" / "web-portal.md").read_text(encoding="utf-8")
    assert "Split-server dev" in doc
    assert "do **not** expose the bot ops bridge publicly" in doc
