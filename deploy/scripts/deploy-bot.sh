#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/rob-bot/app}"
SERVICE_NAME="${SERVICE_NAME:-rob-bot.service}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_REF="${DEPLOY_REF:-${DEPLOY_BRANCH}}"
GIT_CLEAN="${GIT_CLEAN:-true}"
INSTALL_ROB_GLOBAL="${INSTALL_ROB_GLOBAL:-true}"
PYTHON_BIN="${PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"

trap 'echo "Deploy failed. Showing service diagnostics:"; sudo systemctl status "$SERVICE_NAME" --no-pager || true; sudo journalctl -u "$SERVICE_NAME" -n 120 --no-pager || true' ERR

echo "[1/12] Pre-flight checks"
command -v git >/dev/null
command -v python3 >/dev/null
command -v sudo >/dev/null

echo "[2/12] Enter app directory"
[[ -d "$APP_DIR" ]] || { echo "ERROR: APP_DIR does not exist: $APP_DIR"; exit 1; }
cd "$APP_DIR"

echo "[3/12] Verify repository and .env"
[[ -d .git ]] || { echo "ERROR: ${APP_DIR} is not a git repository."; exit 1; }
[[ -f .env ]] || { echo "ERROR: ${APP_DIR}/.env does not exist."; exit 1; }

echo "[4/12] Sync git ref"
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

echo "[5/12] Prepare virtual environment"
if [[ ! -x "$PYTHON_BIN" ]]; then
  python3 -m venv "$APP_DIR/.venv"
fi

echo "[6/12] Install dependencies"
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements.txt

echo "[7/12] Run compile checks"
PYTHONPATH=. "$PYTHON_BIN" -m compileall apps rob scripts

echo "[8/12] Install global rob command if enabled"
if [[ "$INSTALL_ROB_GLOBAL" == "true" ]]; then
  ./scripts/install-rob-global.sh
else
  echo "Skipping global rob command installation."
fi

echo "[9/12] Load and validate environment"
set -a; source .env; set +a
for key in DATABASE_URL DISCORD_TOKEN BOT_NAME; do
  [[ -n "${!key:-}" ]] || { echo "ERROR: Missing required environment variable: $key"; exit 1; }
done

echo "[10/12] Run database checks"
if ! PYTHONPATH=. "$PYTHON_BIN" scripts/check_db.py; then
  echo "Database check failed."
  echo "This database has not been built for Rob v2 yet, or runtime grants are incomplete."
  echo
  echo "Manual fix:"
  echo "1. Open pgAdmin4 / psql as doadmin."
  echo "2. Select the target database."
  echo "3. Run scripts/db/build/001_core_schema.sql."
  echo "4. Run scripts/db/build/002_indexes.sql."
  echo "5. Run the correct grants file from scripts/db/grants/."
  echo "6. Rerun deploy."
  exit 1
fi

echo "[11/12] Restart bot service"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl is-active "$SERVICE_NAME"

echo "[12/12] Show final service status"
sudo systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,14p'

echo "Bot deployment completed successfully."
