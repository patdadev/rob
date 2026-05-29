#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/rob-bot/app}"
SERVICE_NAME="${SERVICE_NAME:-rob-bot-dev.service}"
PYTHON_BIN="${PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: Required command not found: $1"; exit 1; }
}

require_env() {
  local key="$1"
  if [[ -z "${!key:-}" ]]; then
    echo "ERROR: Required environment variable is missing: ${key}"
    exit 1
  fi
}

echo "[1/7] Checking required commands"
require_cmd git
require_cmd python3
require_cmd sudo

echo "[2/7] Checking app directory"
[[ -d "${APP_DIR}" ]] || { echo "ERROR: APP_DIR does not exist: ${APP_DIR}"; exit 1; }
cd "${APP_DIR}"
[[ -d .git ]] || { echo "ERROR: ${APP_DIR} is not a git repository."; exit 1; }
[[ -f .env ]] || { echo "ERROR: ${APP_DIR}/.env does not exist."; exit 1; }

echo "[3/7] Checking virtual environment"
[[ -x "${PYTHON_BIN}" ]] || { echo "ERROR: Python executable missing: ${PYTHON_BIN}"; exit 1; }

echo "[4/7] Checking systemd service"
if ! systemctl cat "${SERVICE_NAME}" >/dev/null 2>&1; then
  echo "ERROR: systemd service not found: ${SERVICE_NAME}"
  exit 1
fi

echo "[5/7] Loading environment"
set -a
source .env
set +a
require_env DATABASE_URL
require_env DISCORD_TOKEN
require_env BOT_NAME

echo "[6/7] Running database check"
PYTHONPATH=. "$PYTHON_BIN" scripts/check_db.py

echo "[7/7] Checking current service state"
systemctl is-active "$SERVICE_NAME" || true

echo
printf 'Bot server pre-check passed.\n'
