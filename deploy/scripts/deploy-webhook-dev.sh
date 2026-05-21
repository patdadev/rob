#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rob-webhook/app}"
SERVICE_NAME="${SERVICE_NAME:-rob-webhook-dev.service}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"
PIP_BIN="${PIP_BIN:-${APP_DIR}/.venv/bin/pip}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/health}"

echo "[1/9] Entering ${APP_DIR}"
cd "${APP_DIR}"

echo "[2/9] Fetching ${DEPLOY_BRANCH}"
git fetch origin

echo "[3/9] Checking out ${DEPLOY_BRANCH}"
git checkout "${DEPLOY_BRANCH}"

echo "[4/9] Pulling latest code"
git pull --ff-only origin "${DEPLOY_BRANCH}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[5/9] Creating virtual environment"
  python3 -m venv "${APP_DIR}/.venv"
else
  echo "[5/9] Virtual environment already present"
fi

echo "[6/9] Installing dependencies"
"${PYTHON_BIN}" -m pip install --upgrade pip
"${PIP_BIN}" install -r requirements.txt

echo "[7/9] Running compile checks"
PYTHONPATH=. "${PYTHON_BIN}" -m compileall apps rob scripts
PYTHONPATH=. "${PYTHON_BIN}" -m scripts.check_db

echo "[8/9] Restarting ${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "[9/9] Running health check"
curl -fsS "${HEALTH_URL}"
printf '\nWebhook deploy complete.\n'
