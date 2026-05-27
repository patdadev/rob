from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on", "y"}:
        return True
    if lowered in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _env_int_csv(name: str, default: str = "") -> tuple[int, ...]:
    values: list[int] = []
    for value in _env_csv(name, default):
        try:
            values.append(int(value))
        except ValueError:
            continue
    return tuple(values)


ROOT_DIR = Path(__file__).resolve().parents[2]
PORTAL_DIR = Path(__file__).resolve().parents[1]

load_dotenv(ROOT_DIR / ".env")
portal_env_file = os.getenv("ROB_PORTAL_ENV_FILE")
if portal_env_file:
    load_dotenv(portal_env_file, override=False)

ROB_PORTAL_ENV = os.getenv("ROB_PORTAL_ENV", "dev").strip() or "dev"
ROB_PORTAL_ENABLED = _env_bool("ROB_PORTAL_ENABLED", False)

_DEFAULT_SECRET_KEY = "rob-portal-dev-only-change-me"
_secret_key_from_env = (os.getenv("ROB_PORTAL_SECRET_KEY") or "").strip()
SECRET_KEY = _secret_key_from_env or _DEFAULT_SECRET_KEY
DEBUG = ROB_PORTAL_ENV != "prod"

portal_database_url = os.getenv("PORTAL_DATABASE_URL") or os.getenv("DATABASE_URL")
if ROB_PORTAL_ENABLED and not portal_database_url:
    raise RuntimeError("ROB_PORTAL_ENABLED=true requires PORTAL_DATABASE_URL or DATABASE_URL.")
if ROB_PORTAL_ENABLED and portal_database_url.lower().startswith("sqlite"):
    raise RuntimeError("ROB_PORTAL_ENABLED=true requires a PostgreSQL PORTAL_DATABASE_URL or DATABASE_URL.")
if ROB_PORTAL_ENABLED and (not _secret_key_from_env or _secret_key_from_env == _DEFAULT_SECRET_KEY):
    raise RuntimeError(
        "ROB_PORTAL_ENABLED=true requires ROB_PORTAL_SECRET_KEY to be set to a non-default value."
    )

ALLOWED_HOSTS = list(
    _env_csv(
        "ROB_PORTAL_ALLOWED_HOSTS",
        "127.0.0.1,localhost",
    )
)
CSRF_TRUSTED_ORIGINS = list(_env_csv("ROB_PORTAL_CSRF_TRUSTED_ORIGINS", ""))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rob_admin",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "rob_portal.middleware.PortalEnabledMiddleware",
]

ROOT_URLCONF = "rob_portal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "rob_portal.wsgi.application"
ASGI_APPLICATION = "rob_portal.asgi.application"

if portal_database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            portal_database_url,
            conn_max_age=300,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(ROOT_DIR / ".portal-local.sqlite3"),
        }
    }

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/portal/static/"
STATIC_ROOT = str(PORTAL_DIR / "staticfiles")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/portal/login/"
LOGIN_REDIRECT_URL = "/portal/dashboard/"
LOGOUT_REDIRECT_URL = "/portal/login/"

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

ROB_PORTAL_BASE_URL = os.getenv("ROB_PORTAL_BASE_URL", "https://rob-dev.barecoding.com")
ROB_PORTAL_SUPERADMIN_USER_IDS = _env_int_csv(
    "ROB_PORTAL_SUPERADMIN_USER_IDS",
    "",
)
ROB_PORTAL_OWNER_USER_ID = ROB_PORTAL_SUPERADMIN_USER_IDS[0] if ROB_PORTAL_SUPERADMIN_USER_IDS else None
ROB_PORTAL_MODERATOR_USER_IDS = _env_int_csv("ROB_PORTAL_MODERATOR_USER_IDS", "")

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI",
    "https://rob-dev.barecoding.com/portal/auth/discord/callback",
).strip()
DISCORD_OAUTH_SCOPES = "identify guilds"
DISCORD_API_BASE = "https://discord.com/api"

ROB_OPS_HOST = os.getenv("ROB_OPS_HOST", "127.0.0.1").strip() or "127.0.0.1"
ROB_OPS_PORT = int(os.getenv("ROB_OPS_PORT", "8811"))
ROB_OPS_SECRET = os.getenv("ROB_OPS_SECRET", "").strip()

ROB_PORTAL_ALLOWED_SERVICES = _env_csv(
    "ROB_PORTAL_ALLOWED_SERVICES",
    "rob-bot-dev.service,rob-webhook-dev.service,rob-portal-dev.service",
)
ROB_PORTAL_ENABLE_SERVICE_ACTIONS = _env_bool("ROB_PORTAL_ENABLE_SERVICE_ACTIONS", False)
