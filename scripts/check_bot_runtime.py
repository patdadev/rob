from __future__ import annotations

from rob.config.settings import load_bot_settings


def main() -> None:
    settings = load_bot_settings()
    if settings.rob_age_verification_enabled and not settings.rob_backend_url:
        raise RuntimeError(
            "ROB_BACKEND_URL is required when ROB_AGE_VERIFICATION_ENABLED=true on the bot."
        )
    if settings.rob_age_verification_enabled and not settings.rob_backend_secret:
        raise RuntimeError(
            "ROB_BACKEND_SECRET is required when ROB_AGE_VERIFICATION_ENABLED=true on the bot."
        )

    print(
        "Loaded bot settings:",
        f"bot_name={settings.bot_name}",
        f"age_enabled={settings.rob_age_verification_enabled}",
        f"backend_url={settings.rob_backend_url or 'unset'}",
    )
    if (
        settings.rob_age_verification_enabled
        and settings.rob_age_verified_role_id is None
    ):
        print(
            "WARNING: ROB_AGE_VERIFIED_ROLE_ID is not set; Rob can verify age but will skip the 18+ role sync."
        )
    if not settings.rob_ops_secret:
        print(
            "WARNING: ROB_OPS_SECRET is blank; bot ops health checks and webhook-to-bot sync are unauthenticated."
        )


if __name__ == "__main__":
    main()
