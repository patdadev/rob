#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rob-bot/app}"
SERVICE_NAME="${SERVICE_NAME:-rob-bot-dev.service}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"
PIP_BIN="${PIP_BIN:-${APP_DIR}/.venv/bin/pip}"

echo "[1/8] Entering ${APP_DIR}"
cd "${APP_DIR}"

echo "[2/8] Fetching ${DEPLOY_BRANCH}"
git fetch origin

echo "[3/8] Checking out ${DEPLOY_BRANCH}"
git checkout "${DEPLOY_BRANCH}"

echo "[4/8] Pulling latest code"
git pull --ff-only origin "${DEPLOY_BRANCH}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[5/8] Creating virtual environment"
  python3 -m venv "${APP_DIR}/.venv"
else
  echo "[5/8] Virtual environment already present"
fi

echo "[6/8] Installing dependencies"
"${PYTHON_BIN}" -m pip install --upgrade pip
"${PIP_BIN}" install -r requirements.txt

echo "[7/8] Running compile checks"
PYTHONPATH=. "${PYTHON_BIN}" -m compileall apps rob scripts
PYTHONPATH=. "${PYTHON_BIN}" -m scripts.check_db

echo "[8/8] Restarting ${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,12p'
printf '\nBot deploy complete.\n'
