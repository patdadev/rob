from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import load_dotenv


@dataclass(frozen=True)
class BaseSettings:
    app_env: str
    log_level: str
    database_url: str
    rob_ops_host: str
    rob_ops_port: int
    rob_ops_secret: str | None
    rob_bot_notify_url: str | None
    rob_backend_secret: str | None
    rob_age_verification_enabled: bool
    rob_age_verification_test_only: bool
    rob_age_verified_role_id: int | None
    throne_parse_test_sends_as_real_sends: bool
    throne_test_gifter_usernames: tuple[str, ...]
    throne_test_send_leaderboard_owner_user_id: int | None
    leaderboard_limit: int
    send_queue_loop_seconds: int
    public_leaderboard_cache_seconds: int
    inactivity_enabled_default: bool
    inactivity_loop_minutes: int
    inactivity_new_member_grace_days: int
    inactivity_assignment_grace_days: int
    inactivity_bootstrap_grace_days: int
    inactivity_final_notice_days: int
    inactivity_owner_user_id: int | None
    inactivity_notice_channel_id: int | None
    rob_public_base_url: str
    rob_terms_version: str
    rob_terms_url: str | None
    rob_privacy_url: str | None
    rob_terms_owner_user_id: int | None


@dataclass(frozen=True)
class WebhookSettings(BaseSettings):
    throne_webhook_host: str
    throne_webhook_port: int
    throne_webhook_base_url: str
    throne_webhook_require_signature: bool
    throne_public_key_pem: str | None
    throne_webhook_debug_log_payload: bool
    throne_webhook_timestamp_header: str
    throne_webhook_signature_header: str
    throne_webhook_signed_message_format: str
    throne_webhook_max_timestamp_skew_seconds: int
    yoti_environment: str
    yoti_sdk_id: str | None
    yoti_api_key: str | None
    yoti_private_key_path: str | None
    yoti_age_threshold: int
    yoti_age_estimation_threshold: int
    yoti_public_base_url: str | None
    yoti_callback_url: str | None
    yoti_notification_url: str | None
    yoti_success_url: str | None
    yoti_cancel_url: str | None


@dataclass(frozen=True)
class BotSettings(BaseSettings):
    discord_token: str
    bot_name: str
    rob_backend_url: str | None


def _load_env_file(env_file: str | Path | None) -> None:
    disable_dotenv = os.getenv("PYTHON_DOTENV_DISABLED", "").strip().lower()
    if disable_dotenv in {"1", "true", "yes", "on"}:
        return

    if env_file is not None:
        load_dotenv(env_file)
        return
    load_dotenv()


def _env_str(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        if required:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return "" if default is None else default
    return value.strip()


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer.") from exc

    if minimum is not None and value < minimum:
        raise RuntimeError(f"Environment variable {name} must be at least {minimum}.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError(f"Environment variable {name} must be a boolean value.")


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None

    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer.") from exc


def _env_lower_csv(name: str, default: str) -> tuple[str, ...]:
    raw = _env_str(name, default)
    return tuple(value.strip().lower() for value in raw.split(",") if value.strip())


def _validate_yoti_private_key_path(private_key_path: str) -> None:
    path = Path(private_key_path).expanduser()
    try:
        pem_bytes = path.read_bytes()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Configured YOTI_PRIVATE_KEY_PATH does not exist: {path}"
        ) from exc
    except PermissionError as exc:
        raise RuntimeError(
            f"Configured YOTI_PRIVATE_KEY_PATH is not readable by the backend process: {path}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Configured YOTI_PRIVATE_KEY_PATH could not be read by the backend process: {path}"
        ) from exc

    try:
        private_key = serialization.load_pem_private_key(
            pem_bytes,
            password=None,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Configured YOTI_PRIVATE_KEY_PATH is not a valid PEM private key: {path}"
        ) from exc

    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise RuntimeError(
            f"Configured YOTI_PRIVATE_KEY_PATH is not an RSA private key: {path}"
        )


def _validate_webhook_yoti_settings(settings: WebhookSettings) -> None:
    if not settings.rob_age_verification_enabled:
        return
    if not settings.yoti_sdk_id:
        raise RuntimeError(
            "YOTI_SDK_ID is required when ROB_AGE_VERIFICATION_ENABLED=true on the webhook backend."
        )
    if not settings.yoti_private_key_path:
        raise RuntimeError(
            "YOTI_PRIVATE_KEY_PATH is required when ROB_AGE_VERIFICATION_ENABLED=true on the webhook backend."
        )
    _validate_yoti_private_key_path(settings.yoti_private_key_path)


def load_base_settings(env_file: str | Path | None = None) -> BaseSettings:
    _load_env_file(env_file)
    return BaseSettings(
        app_env=_env_str("APP_ENV", "dev"),
        log_level=_env_str("LOG_LEVEL", "INFO"),
        database_url=_env_str("DATABASE_URL", required=True),
        rob_ops_host=_env_str("ROB_OPS_HOST", "127.0.0.1"),
        rob_ops_port=_env_int("ROB_OPS_PORT", 8811, minimum=1),
        rob_ops_secret=_env_str("ROB_OPS_SECRET") or None,
        rob_bot_notify_url=_env_str("ROB_BOT_NOTIFY_URL") or None,
        rob_backend_secret=_env_str("ROB_BACKEND_SECRET") or None,
        rob_age_verification_enabled=_env_bool("ROB_AGE_VERIFICATION_ENABLED", False),
        rob_age_verification_test_only=_env_bool("ROB_AGE_VERIFICATION_TEST_ONLY", True),
        rob_age_verified_role_id=_env_optional_int("ROB_AGE_VERIFIED_ROLE_ID"),
        throne_parse_test_sends_as_real_sends=_env_bool(
            "THRONE_PARSE_TEST_SENDS_AS_REAL_SENDS",
            False,
        ),
        throne_test_gifter_usernames=_env_lower_csv(
            "THRONE_TEST_GIFTER_USERNAMES",
            "marie_123",
        ),
        throne_test_send_leaderboard_owner_user_id=_env_optional_int(
            "THRONE_TEST_SEND_LEADERBOARD_OWNER_USER_ID"
        ),
        leaderboard_limit=_env_int("LEADERBOARD_LIMIT", 10, minimum=1),
        send_queue_loop_seconds=_env_int("SEND_QUEUE_LOOP_SECONDS", 10, minimum=1),
        public_leaderboard_cache_seconds=_env_int("PUBLIC_LEADERBOARD_CACHE_SECONDS", 60, minimum=1),
        inactivity_enabled_default=_env_bool("INACTIVITY_ENABLED_DEFAULT", False),
        inactivity_loop_minutes=_env_int("INACTIVITY_LOOP_MINUTES", 60, minimum=1),
        inactivity_new_member_grace_days=_env_int("INACTIVITY_NEW_MEMBER_GRACE_DAYS", 7, minimum=1),
        inactivity_assignment_grace_days=_env_int("INACTIVITY_ASSIGNMENT_GRACE_DAYS", 14, minimum=1),
        inactivity_bootstrap_grace_days=_env_int("INACTIVITY_BOOTSTRAP_GRACE_DAYS", 21, minimum=1),
        inactivity_final_notice_days=_env_int("INACTIVITY_FINAL_NOTICE_DAYS", 7, minimum=1),
        inactivity_owner_user_id=_env_optional_int("INACTIVITY_OWNER_USER_ID"),
        inactivity_notice_channel_id=_env_optional_int("INACTIVITY_NOTICE_CHANNEL_ID"),
        rob_public_base_url=_env_str("ROB_PUBLIC_BASE_URL", "https://leaderboard.robthebot.com"),
        rob_terms_version=_env_str("ROB_TERMS_VERSION", "2026-06-05"),
        rob_terms_url=_env_str("ROB_TERMS_URL") or None,
        rob_privacy_url=_env_str("ROB_PRIVACY_URL") or None,
        rob_terms_owner_user_id=_env_optional_int("ROB_TERMS_OWNER_USER_ID"),
    )


def load_webhook_settings(env_file: str | Path | None = None) -> WebhookSettings:
    base = load_base_settings(env_file)
    settings = WebhookSettings(
        app_env=base.app_env,
        log_level=base.log_level,
        database_url=base.database_url,
        rob_ops_host=base.rob_ops_host,
        rob_ops_port=base.rob_ops_port,
        rob_ops_secret=base.rob_ops_secret,
        rob_bot_notify_url=base.rob_bot_notify_url,
        rob_backend_secret=base.rob_backend_secret,
        rob_age_verification_enabled=base.rob_age_verification_enabled,
        rob_age_verification_test_only=base.rob_age_verification_test_only,
        rob_age_verified_role_id=base.rob_age_verified_role_id,
        throne_parse_test_sends_as_real_sends=base.throne_parse_test_sends_as_real_sends,
        throne_test_gifter_usernames=base.throne_test_gifter_usernames,
        throne_test_send_leaderboard_owner_user_id=base.throne_test_send_leaderboard_owner_user_id,
        leaderboard_limit=base.leaderboard_limit,
        send_queue_loop_seconds=base.send_queue_loop_seconds,
        public_leaderboard_cache_seconds=base.public_leaderboard_cache_seconds,
        inactivity_enabled_default=base.inactivity_enabled_default,
        inactivity_loop_minutes=base.inactivity_loop_minutes,
        inactivity_new_member_grace_days=base.inactivity_new_member_grace_days,
        inactivity_assignment_grace_days=base.inactivity_assignment_grace_days,
        inactivity_bootstrap_grace_days=base.inactivity_bootstrap_grace_days,
        inactivity_final_notice_days=base.inactivity_final_notice_days,
        inactivity_owner_user_id=base.inactivity_owner_user_id,
        inactivity_notice_channel_id=base.inactivity_notice_channel_id,
        rob_terms_version=base.rob_terms_version,
        rob_terms_url=base.rob_terms_url,
        rob_privacy_url=base.rob_privacy_url,
        rob_terms_owner_user_id=base.rob_terms_owner_user_id,
        throne_webhook_host=_env_str("THRONE_WEBHOOK_HOST", "127.0.0.1"),
        throne_webhook_port=_env_int("THRONE_WEBHOOK_PORT", 8080, minimum=1),
        throne_webhook_base_url=_env_str(
            "THRONE_WEBHOOK_BASE_URL",
            "https://throne.robthebot.com",
        ),
        throne_webhook_require_signature=_env_bool(
            "THRONE_WEBHOOK_REQUIRE_SIGNATURE",
            True,
        ),
        throne_public_key_pem=_env_str("THRONE_PUBLIC_KEY_PEM") or None,
        throne_webhook_debug_log_payload=_env_bool(
            "THRONE_WEBHOOK_DEBUG_LOG_PAYLOAD",
            False,
        ),
        throne_webhook_timestamp_header=_env_str(
            "THRONE_WEBHOOK_TIMESTAMP_HEADER",
            "X-Signature-Timestamp",
        ),
        throne_webhook_signature_header=_env_str(
            "THRONE_WEBHOOK_SIGNATURE_HEADER",
            "X-Signature-Ed25519",
        ),
        throne_webhook_signed_message_format=_env_str(
            "THRONE_WEBHOOK_SIGNED_MESSAGE_FORMAT",
            "timestamp_dot_body",
        ),
        throne_webhook_max_timestamp_skew_seconds=_env_int(
            "THRONE_WEBHOOK_MAX_TIMESTAMP_SKEW_SECONDS",
            300,
            minimum=0,
        ),
        yoti_environment=_env_str("YOTI_ENVIRONMENT", "sandbox"),
        yoti_sdk_id=_env_str("YOTI_SDK_ID") or None,
        yoti_api_key=_env_str("YOTI_API_KEY") or None,
        yoti_private_key_path=_env_str("YOTI_PRIVATE_KEY_PATH") or None,
        yoti_age_threshold=_env_int("YOTI_AGE_THRESHOLD", 18, minimum=1),
        yoti_age_estimation_threshold=_env_int(
            "YOTI_AGE_ESTIMATION_THRESHOLD",
            21,
            minimum=1,
        ),
        yoti_public_base_url=_env_str("YOTI_PUBLIC_BASE_URL") or None,
        yoti_callback_url=_env_str("YOTI_CALLBACK_URL") or None,
        yoti_notification_url=_env_str("YOTI_NOTIFICATION_URL") or None,
        yoti_success_url=_env_str("YOTI_SUCCESS_URL") or None,
        yoti_cancel_url=_env_str("YOTI_CANCEL_URL") or None,
        rob_public_base_url=base.rob_public_base_url,
    )
    _validate_webhook_yoti_settings(settings)
    return settings


def load_bot_settings(env_file: str | Path | None = None) -> BotSettings:
    base = load_base_settings(env_file)
    return BotSettings(
        app_env=base.app_env,
        log_level=base.log_level,
        database_url=base.database_url,
        rob_ops_host=base.rob_ops_host,
        rob_ops_port=base.rob_ops_port,
        rob_ops_secret=base.rob_ops_secret,
        rob_bot_notify_url=base.rob_bot_notify_url,
        rob_backend_secret=base.rob_backend_secret,
        rob_age_verification_enabled=base.rob_age_verification_enabled,
        rob_age_verification_test_only=base.rob_age_verification_test_only,
        rob_age_verified_role_id=base.rob_age_verified_role_id,
        throne_parse_test_sends_as_real_sends=base.throne_parse_test_sends_as_real_sends,
        throne_test_gifter_usernames=base.throne_test_gifter_usernames,
        throne_test_send_leaderboard_owner_user_id=base.throne_test_send_leaderboard_owner_user_id,
        leaderboard_limit=base.leaderboard_limit,
        send_queue_loop_seconds=base.send_queue_loop_seconds,
        public_leaderboard_cache_seconds=base.public_leaderboard_cache_seconds,
        inactivity_enabled_default=base.inactivity_enabled_default,
        inactivity_loop_minutes=base.inactivity_loop_minutes,
        inactivity_new_member_grace_days=base.inactivity_new_member_grace_days,
        inactivity_assignment_grace_days=base.inactivity_assignment_grace_days,
        inactivity_bootstrap_grace_days=base.inactivity_bootstrap_grace_days,
        inactivity_final_notice_days=base.inactivity_final_notice_days,
        inactivity_owner_user_id=base.inactivity_owner_user_id,
        inactivity_notice_channel_id=base.inactivity_notice_channel_id,
        rob_public_base_url=base.rob_public_base_url,
        rob_terms_version=base.rob_terms_version,
        rob_terms_url=base.rob_terms_url,
        rob_privacy_url=base.rob_privacy_url,
        rob_terms_owner_user_id=base.rob_terms_owner_user_id,
        discord_token=_env_str("DISCORD_TOKEN", required=True),
        bot_name=_env_str("BOT_NAME", "Rob"),
        rob_backend_url=_env_str("ROB_BACKEND_URL") or None,
    )


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
