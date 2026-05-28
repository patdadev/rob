#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/rob-webhook/app}"
SERVICE_NAME="${SERVICE_NAME:-rob-webhook.service}"
PYTHON_BIN="${PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/health}"

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

echo "[1/8] Checking required commands"
require_cmd git
require_cmd python3
require_cmd sudo
require_cmd curl

echo "[2/8] Checking app directory"
[[ -d "${APP_DIR}" ]] || { echo "ERROR: APP_DIR does not exist: ${APP_DIR}"; exit 1; }
cd "${APP_DIR}"
[[ -d .git ]] || { echo "ERROR: ${APP_DIR} is not a git repository."; exit 1; }
[[ -f .env ]] || { echo "ERROR: ${APP_DIR}/.env does not exist."; exit 1; }

echo "[3/8] Checking virtual environment"
[[ -x "${PYTHON_BIN}" ]] || { echo "ERROR: Python executable missing: ${PYTHON_BIN}"; exit 1; }

echo "[4/8] Checking systemd service"
if ! systemctl cat "${SERVICE_NAME}" >/dev/null 2>&1; then
  echo "ERROR: systemd service not found: ${SERVICE_NAME}"
  exit 1
fi

echo "[5/8] Loading environment"
set -a
source .env
set +a
require_env DATABASE_URL
require_env THRONE_WEBHOOK_HOST
require_env THRONE_WEBHOOK_PORT

echo "[6/8] Running database check"
PYTHONPATH=. "$PYTHON_BIN" scripts/check_db.py

echo "[7/8] Checking current service state"
STATE="$(systemctl is-active "$SERVICE_NAME" || true)"
echo "${STATE}"

echo "[8/8] Checking current health endpoint if active"
if [[ "${STATE}" == "active" ]]; then
  curl -fsS "$HEALTH_URL" >/dev/null
  echo "Health endpoint is reachable: ${HEALTH_URL}"
else
  echo "Service is not active; skipping live health check."
fi

echo
printf 'Webhook server pre-check passed.\n'
