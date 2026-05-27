from __future__ import annotations

import secrets

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User
from django.utils import timezone

from .models import (
    Blacklist,
    BotState,
    CountingState,
    Domme,
    GuildSettings,
    LeaderboardMessage,
    PortalAuditLog,
    PublicLeaderboard,
    SchemaMigration,
    Send,
    SendRequest,
    Sub,
    ThroneCreator,
)
from .services import audit_action


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class PortalUserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_superuser",
        "is_active",
        "last_login",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("-is_active", "username")

    add_fieldsets = (
        (
            "Create portal user",
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                    "is_active",
                    "groups",
                ),
                "description": "Use staff + groups for most users. Reserve superuser for trusted administrators.",
            },
        ),
    )

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "email")}),
        (
            "Portal access",
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
                "description": "Staff grants admin access. Assign groups to apply standard permission sets quickly.",
            },
        ),
        ("Security", {"fields": ("last_login", "date_joined")}),
    )


@admin.register(Group)
class PortalGroupAdmin(DjangoGroupAdmin):
    search_fields = ("name",)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        del obj
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        del obj
        return request.method in {"GET", "HEAD", "OPTIONS"}

    def get_readonly_fields(self, request, obj=None):
        del request, obj
        return [field.name for field in self.model._meta.fields]


@admin.register(GuildSettings)
class GuildSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "guild_id",
        "registration_channel_id",
        "leaderboard_channel_id",
        "send_track_channel_id",
        "counting_channel_id",
        "report_channel_id",
        "domme_role_id",
        "sub_role_id",
        "mod_role_id",
        "inactive_role_id",
        "updated_at",
    )
    search_fields = ("guild_id",)

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(Domme)
class DommeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "guild_id",
        "discord_user_id",
        "public_display_name",
        "throne_url",
        "registered_at",
        "updated_at",
    )
    search_fields = ("discord_user_id", "public_display_name", "throne_url")
    list_filter = ("guild_id",)

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(Sub)
class SubAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "guild_id",
        "discord_user_id",
        "send_name",
        "registered_at",
        "updated_at",
    )
    search_fields = ("discord_user_id", "send_name")
    list_filter = ("guild_id",)

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(Send)
class SendAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "guild_id",
        "domme_user_id",
        "sub_user_id",
        "sub_name",
        "amount_cents",
        "currency",
        "source",
        "discord_post_status",
        "is_test_send",
        "is_private",
        "sent_at",
        "created_at",
    )
    search_fields = (
        "id",
        "public_send_id",
        "domme_user_id",
        "sub_user_id",
        "sub_name",
        "event_id",
        "fallback_event_hash",
    )
    list_filter = ("guild_id", "discord_post_status", "source", "is_test_send", "is_private", "currency")


@admin.register(SendRequest)
class SendRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "guild_id",
        "sub_user_id",
        "domme_user_id",
        "amount_cents",
        "currency",
        "method",
        "status",
        "created_at",
        "resolved_at",
        "resolved_by_user_id",
    )
    list_filter = ("guild_id", "status", "currency")
    search_fields = ("id", "sub_user_id", "domme_user_id", "note", "denial_reason")

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(ThroneCreator)
class ThroneCreatorAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "guild_id",
        "discord_user_id",
        "throne_handle",
        "throne_creator_id",
        "tracking_mode",
        "webhook_connected_at",
        "last_successful_event_at",
        "last_test_webhook_at",
        "setup_verified_at",
        "updated_at",
    )
    search_fields = ("discord_user_id", "throne_handle", "throne_creator_id")
    list_filter = ("guild_id", "tracking_mode")
    exclude = ("webhook_secret", "webhook_secret_hash")
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(PublicLeaderboard)
class PublicLeaderboardAdmin(admin.ModelAdmin):
    list_display = ("id", "guild_id", "title", "enabled", "theme", "created_at", "updated_at", "public_url")
    search_fields = ("guild_id", "title", "public_token")
    list_filter = ("guild_id", "enabled", "theme")
    actions = ("enable_selected", "disable_selected", "rotate_token_selected")

    @admin.action(description="Enable selected leaderboards")
    def enable_selected(self, request, queryset):
        count = queryset.update(enabled=True, updated_at=timezone.now())
        audit_action(
            request=request,
            action="public_leaderboard_enable_selected",
            target_type="public_leaderboard",
            target_id=f"{count} rows",
            metadata={"count": count},
        )

    @admin.action(description="Disable selected leaderboards")
    def disable_selected(self, request, queryset):
        count = queryset.update(enabled=False, updated_at=timezone.now())
        audit_action(
            request=request,
            action="public_leaderboard_disable_selected",
            target_type="public_leaderboard",
            target_id=f"{count} rows",
            metadata={"count": count},
        )

    @admin.action(description="Rotate token for selected leaderboards")
    def rotate_token_selected(self, request, queryset):
        rotated = 0
        for row in queryset:
            row.public_token = secrets.token_urlsafe(32)
            row.updated_at = timezone.now()
            row.save(update_fields=["public_token", "updated_at"])
            rotated += 1
        audit_action(
            request=request,
            action="public_leaderboard_rotate_token_selected",
            target_type="public_leaderboard",
            target_id=f"{rotated} rows",
            metadata={"count": rotated},
        )

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(LeaderboardMessage)
class LeaderboardMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "guild_id",
        "message_key",
        "leaderboard_type",
        "channel_id",
        "message_id",
        "updated_at",
    )
    search_fields = ("guild_id", "message_key", "message_id", "channel_id")
    list_filter = ("guild_id", "message_key")

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(BotState)
class BotStateAdmin(ReadOnlyAdmin):
    list_display = ("key", "masked_value", "updated_at")
    search_fields = ("key",)

    def masked_value(self, obj: BotState) -> str:
        key = obj.key.lower()
        if any(token in key for token in ("secret", "token", "password", "key")):
            return "***"
        return obj.value

    masked_value.short_description = "value"


@admin.register(CountingState)
class CountingStateAdmin(admin.ModelAdmin):
    list_display = (
        "guild_id",
        "channel_id",
        "current_number",
        "last_user_id",
        "is_enabled",
        "pending_restore",
        "updated_at",
    )
    search_fields = ("guild_id", "channel_id")

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(Blacklist)
class BlacklistAdmin(admin.ModelAdmin):
    list_display = ("discord_user_id", "reason", "created_by", "created_at")
    search_fields = ("discord_user_id", "reason")

    def has_delete_permission(self, request, obj=None) -> bool:
        del request, obj
        return False


@admin.register(SchemaMigration)
class SchemaMigrationAdmin(ReadOnlyAdmin):
    list_display = ("version", "applied_at")
    search_fields = ("version",)


@admin.register(PortalAuditLog)
class PortalAuditLogAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "actor_discord_user_id",
        "actor_username",
        "action",
        "target_type",
        "target_id",
        "created_at",
    )
    search_fields = ("actor_discord_user_id", "actor_username", "action", "target_type", "target_id")


admin.site.site_header = "Rob Portal Admin"
admin.site.site_title = "Rob Portal"
admin.site.index_title = "Rob Administration"
