from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.portal_home, name="portal_home"),
    path("login/", views.portal_login, name="portal_login"),
    path("logout/", views.portal_logout, name="portal_logout"),
    path("auth/discord/", views.discord_auth_start, name="portal_discord_auth_start"),
    path("auth/discord/callback/", views.discord_auth_callback, name="portal_discord_auth_callback"),
    path("dashboard/", views.dashboard_view, name="portal_dashboard"),
    path("dashboard/test-bot-bridge/", views.test_bot_bridge_view, name="portal_test_bot_bridge"),
    path("services/", views.services_view, name="portal_services"),
    path("logs/", views.logs_view, name="portal_logs"),
    path("database/", views.database_view, name="portal_database"),
    path("leaderboards/", views.leaderboards_view, name="portal_leaderboards"),
    path("sends/", views.sends_view, name="portal_sends"),
    path("settings/", views.settings_view, name="portal_settings"),
]
