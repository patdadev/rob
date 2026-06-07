from __future__ import annotations

from rob.config.settings import load_webhook_settings
from rob.services.yoti_age_provider import YotiAgeProvider


def main() -> None:
    settings = load_webhook_settings()
    if settings.rob_age_verification_enabled and not settings.rob_backend_secret:
        raise RuntimeError(
            "ROB_BACKEND_SECRET is required when ROB_AGE_VERIFICATION_ENABLED=true on the webhook backend."
        )
    if settings.rob_age_verification_enabled:
        YotiAgeProvider.from_settings(settings).validate_startup_configuration()

    print(
        "Loaded webhook settings:",
        f"listen={settings.throne_webhook_host}:{settings.throne_webhook_port}",
        f"public_base={settings.throne_webhook_base_url}",
        f"age_enabled={settings.rob_age_verification_enabled}",
        f"yoti_public_base={settings.yoti_public_base_url or 'derived-from-callbacks'}",
    )
    if settings.rob_bot_notify_url and not settings.rob_ops_secret:
        print(
            "WARNING: ROB_BOT_NOTIFY_URL is set but ROB_OPS_SECRET is blank; the bot-notify bridge may be unauthenticated."
        )


if __name__ == "__main__":
    main()
