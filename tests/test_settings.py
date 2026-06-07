from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import rob.config.settings as settings_module
from rob.config.settings import load_base_settings, load_bot_settings, load_webhook_settings
from rob.services.registration_service import sanitize_webhook_base_url


def _write_test_private_key(tmp_path: Path) -> Path:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_path = tmp_path / "yoti-test.pem"
    pem_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return pem_path


def test_load_base_settings_only_requires_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)

    settings = load_base_settings()

    assert settings.database_url == "postgresql://example/db"
    assert settings.app_env == "dev"
    assert settings.rob_ops_host == "127.0.0.1"
    assert settings.rob_ops_port == 8811
    assert settings.rob_bot_notify_url is None
    assert settings.rob_backend_secret is None
    assert settings.rob_age_verification_enabled is False
    assert settings.rob_age_verification_test_only is True
    assert settings.rob_age_verified_role_id is None
    assert settings.inactivity_enabled_default is False
    assert settings.inactivity_loop_minutes == 60
    assert settings.rob_public_base_url == "https://leaderboard.robthebot.com"
    assert settings.rob_terms_version == "2026-06-05"
    assert settings.rob_terms_url is None
    assert settings.rob_privacy_url is None
    assert settings.rob_terms_owner_user_id is None


def test_load_bot_settings_requires_discord_token(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)

    try:
        load_bot_settings()
    except RuntimeError as exc:
        assert "DISCORD_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected DISCORD_TOKEN requirement to fail.")


def test_load_webhook_settings_does_not_require_discord_token(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)

    settings = load_webhook_settings()

    assert settings.database_url == "postgresql://example/db"
    assert settings.throne_webhook_require_signature is True
    assert settings.throne_test_gifter_usernames == ("marie_123",)
    assert settings.leaderboard_limit == 10
    assert settings.yoti_environment == "sandbox"
    assert settings.yoti_sdk_id is None
    assert settings.yoti_api_key is None


def test_sanitize_webhook_base_url_handles_bad_equals_quotes_and_slash():
    raw = "  '=https://throne.robthebot.com/'  "
    assert sanitize_webhook_base_url(raw) == "https://throne.robthebot.com"


def test_load_webhook_url_sanitizes_when_generating_registration_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("THRONE_WEBHOOK_BASE_URL", "==https://throne.robthebot.com/")
    settings = load_webhook_settings()
    assert sanitize_webhook_base_url(settings.throne_webhook_base_url) == "https://throne.robthebot.com"


def test_load_base_settings_supports_test_sender_and_leaderboard_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("ROB_OPS_HOST", "127.0.0.2")
    monkeypatch.setenv("ROB_OPS_PORT", "9911")
    monkeypatch.setenv("ROB_OPS_SECRET", "shared-secret")
    monkeypatch.setenv("ROB_BOT_NOTIFY_URL", "https://bot-01.robthebot.com/ops/sends/process")
    monkeypatch.setenv("THRONE_TEST_GIFTER_USERNAMES", "marie_123, test_sender ")
    monkeypatch.setenv("THRONE_TEST_SEND_LEADERBOARD_OWNER_USER_ID", "42")
    monkeypatch.setenv("LEADERBOARD_LIMIT", "15")
    monkeypatch.setenv("ROB_PUBLIC_BASE_URL", "https://example.com")

    settings = load_base_settings()

    assert settings.rob_ops_host == "127.0.0.2"
    assert settings.rob_ops_port == 9911
    assert settings.rob_ops_secret == "shared-secret"
    assert settings.rob_bot_notify_url == "https://bot-01.robthebot.com/ops/sends/process"
    assert settings.throne_test_gifter_usernames == ("marie_123", "test_sender")
    assert settings.throne_test_send_leaderboard_owner_user_id == 42
    assert settings.leaderboard_limit == 15
    assert settings.rob_public_base_url == "https://example.com"


def test_load_base_settings_supports_terms_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("ROB_TERMS_VERSION", "2026-09-01")
    monkeypatch.setenv("ROB_TERMS_URL", "https://example.com/terms")
    monkeypatch.setenv("ROB_PRIVACY_URL", "https://example.com/privacy")
    monkeypatch.setenv("ROB_TERMS_OWNER_USER_ID", "77")

    settings = load_base_settings()

    assert settings.rob_terms_version == "2026-09-01"
    assert settings.rob_terms_url == "https://example.com/terms"
    assert settings.rob_privacy_url == "https://example.com/privacy"
    assert settings.rob_terms_owner_user_id == 77


def test_load_base_settings_supports_age_verification_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("ROB_BACKEND_SECRET", "backend-secret")
    monkeypatch.setenv("ROB_AGE_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("ROB_AGE_VERIFICATION_TEST_ONLY", "false")
    monkeypatch.setenv("ROB_AGE_VERIFIED_ROLE_ID", "99")

    settings = load_base_settings()

    assert settings.rob_backend_secret == "backend-secret"
    assert settings.rob_age_verification_enabled is True
    assert settings.rob_age_verification_test_only is False
    assert settings.rob_age_verified_role_id == 99


def test_load_bot_settings_supports_backend_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("DISCORD_TOKEN", "discord-token")
    monkeypatch.setenv("ROB_BACKEND_URL", "https://age.robthebot.com")

    settings = load_bot_settings()

    assert settings.rob_backend_url == "https://age.robthebot.com"


def test_load_webhook_settings_supports_yoti_sandbox_without_api_key(
    monkeypatch,
    tmp_path,
):
    pem_path = _write_test_private_key(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("ROB_AGE_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("YOTI_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("YOTI_SDK_ID", "sdk-123")
    monkeypatch.delenv("YOTI_API_KEY", raising=False)
    monkeypatch.setenv("YOTI_PRIVATE_KEY_PATH", str(pem_path))
    monkeypatch.setenv("YOTI_AGE_THRESHOLD", "18")
    monkeypatch.setenv("YOTI_AGE_ESTIMATION_THRESHOLD", "21")
    monkeypatch.setenv("YOTI_PUBLIC_BASE_URL", "https://age.robthebot.com")
    monkeypatch.setenv("YOTI_CALLBACK_URL", "https://age.robthebot.com/yoti/callback")
    monkeypatch.setenv(
        "YOTI_NOTIFICATION_URL",
        "https://age.robthebot.com/yoti/notification",
    )
    monkeypatch.setenv("YOTI_SUCCESS_URL", "https://robthebot.com/age-success")
    monkeypatch.setenv("YOTI_CANCEL_URL", "https://robthebot.com/age-cancelled")

    settings = load_webhook_settings()

    assert settings.yoti_environment == "sandbox"
    assert settings.yoti_sdk_id == "sdk-123"
    assert settings.yoti_api_key is None
    assert settings.yoti_private_key_path == str(pem_path)
    assert settings.yoti_age_threshold == 18
    assert settings.yoti_age_estimation_threshold == 21
    assert settings.yoti_public_base_url == "https://age.robthebot.com"
    assert settings.yoti_callback_url == "https://age.robthebot.com/yoti/callback"
    assert settings.yoti_notification_url == "https://age.robthebot.com/yoti/notification"
    assert settings.yoti_success_url == "https://robthebot.com/age-success"
    assert settings.yoti_cancel_url == "https://robthebot.com/age-cancelled"


def test_load_webhook_settings_requires_yoti_private_key_path_when_enabled(
    monkeypatch,
):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("ROB_AGE_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("YOTI_SDK_ID", "sdk-123")
    monkeypatch.delenv("YOTI_PRIVATE_KEY_PATH", raising=False)

    with pytest.raises(RuntimeError, match="YOTI_PRIVATE_KEY_PATH"):
        load_webhook_settings()


def test_load_webhook_settings_requires_yoti_sdk_id_when_enabled(monkeypatch, tmp_path):
    pem_path = _write_test_private_key(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("ROB_AGE_VERIFICATION_ENABLED", "true")
    monkeypatch.delenv("YOTI_SDK_ID", raising=False)
    monkeypatch.setenv("YOTI_PRIVATE_KEY_PATH", str(pem_path))

    with pytest.raises(RuntimeError, match="YOTI_SDK_ID"):
        load_webhook_settings()


def test_load_webhook_settings_requires_readable_yoti_private_key_file(
    monkeypatch,
    tmp_path,
):
    missing_path = tmp_path / "missing-yoti.pem"
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("ROB_AGE_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("YOTI_SDK_ID", "sdk-123")
    monkeypatch.setenv("YOTI_PRIVATE_KEY_PATH", str(missing_path))

    with pytest.raises(RuntimeError, match="does not exist"):
        load_webhook_settings()


def test_load_base_settings_skips_dotenv_when_disabled(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")

    def _raise_if_called(*_args, **_kwargs):
        raise RuntimeError("load_dotenv should not be called when disabled")

    monkeypatch.setattr(settings_module, "load_dotenv", _raise_if_called)

    settings = load_base_settings()
    assert settings.database_url == "postgresql://example/db"
