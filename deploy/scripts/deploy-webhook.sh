#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/rob-webhook/app}"
SERVICE_NAME="${SERVICE_NAME:-rob-webhook.service}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_REF="${DEPLOY_REF:-${DEPLOY_BRANCH}}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/health}"
HEALTH_ATTEMPTS="${HEALTH_ATTEMPTS:-20}"
HEALTH_SLEEP_SECONDS="${HEALTH_SLEEP_SECONDS:-2}"
GIT_CLEAN="${GIT_CLEAN:-true}"
INSTALL_ROB_GLOBAL="${INSTALL_ROB_GLOBAL:-true}"
PYTHON_BIN="${PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"

trap 'echo "Deploy failed. Showing service diagnostics:"; sudo systemctl status "$SERVICE_NAME" --no-pager || true; sudo journalctl -u "$SERVICE_NAME" -n 120 --no-pager || true' ERR

echo "[1/13] Pre-flight checks"
command -v git >/dev/null
command -v python3 >/dev/null
command -v sudo >/dev/null
command -v curl >/dev/null

echo "[2/13] Enter app directory"
[[ -d "$APP_DIR" ]] || { echo "ERROR: APP_DIR does not exist: $APP_DIR"; exit 1; }
cd "$APP_DIR"

echo "[3/13] Verify repository and .env"
[[ -d .git ]] || { echo "ERROR: ${APP_DIR} is not a git repository."; exit 1; }
[[ -f .env ]] || { echo "ERROR: ${APP_DIR}/.env does not exist."; exit 1; }

echo "[4/13] Sync git ref"
git fetch origin --prune "$DEPLOY_BRANCH"
git fetch origin "$DEPLOY_REF" || true
if [[ "$DEPLOY_REF" == "$DEPLOY_BRANCH" ]]; then
  git checkout "$DEPLOY_BRANCH" || git checkout -B "$DEPLOY_BRANCH" "origin/$DEPLOY_BRANCH"
  git reset --hard "origin/$DEPLOY_BRANCH"
else
  if git rev-parse --verify --quiet "$DEPLOY_REF" >/dev/null; then
    git checkout --detach "$DEPLOY_REF"
  else
    git checkout --detach FETCH_HEAD
  fi
fi
if [[ "$GIT_CLEAN" == "true" ]]; then
  git clean -fd --exclude=.env --exclude=.venv
fi

echo "[5/13] Prepare virtual environment"
if [[ ! -x "$PYTHON_BIN" ]]; then
  python3 -m venv "$APP_DIR/.venv"
fi

echo "[6/13] Install dependencies"
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements.txt

echo "[7/13] Run compile checks"
PYTHONPATH=. "$PYTHON_BIN" -m compileall apps rob scripts

echo "[8/13] Install global rob command if enabled"
if [[ "$INSTALL_ROB_GLOBAL" == "true" ]]; then
  ./scripts/install-rob-global.sh
else
  echo "Skipping global rob command installation."
fi

echo "[9/13] Load and validate environment"
set -a; source .env; set +a
for key in DATABASE_URL THRONE_WEBHOOK_HOST THRONE_WEBHOOK_PORT; do
  [[ -n "${!key:-}" ]] || { echo "ERROR: Missing required environment variable: $key"; exit 1; }
done
if [[ -z "${THRONE_WEBHOOK_BASE_URL:-}" ]]; then
  echo "WARNING: THRONE_WEBHOOK_BASE_URL is not set."
fi

echo "[10/13] Run database checks"
PYTHONPATH=. "$PYTHON_BIN" scripts/check_db.py

echo "[11/13] Restart webhook service"
sudo systemctl restart "$SERVICE_NAME"

echo "[12/13] Wait for health check"
for ((i=1; i<=HEALTH_ATTEMPTS; i++)); do
  if curl -fsS "$HEALTH_URL" >/dev/null; then
    echo "Health check passed."
    break
  fi
  if [[ "$i" -eq "$HEALTH_ATTEMPTS" ]]; then
    echo "ERROR: Health check failed after ${HEALTH_ATTEMPTS} attempts."
    sudo systemctl status "$SERVICE_NAME" --no-pager || true
    sudo journalctl -u "$SERVICE_NAME" -n 120 --no-pager || true
    exit 1
  fi
  sleep "$HEALTH_SLEEP_SECONDS"
done

echo "[13/13] Show final service status"
sudo systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,14p'

echo "Webhook deployment completed successfully."
