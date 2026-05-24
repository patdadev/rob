#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/rob-bot/app}"
SERVICE_NAME="${SERVICE_NAME:-rob-bot-dev.service}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_REF="${DEPLOY_REF:-${DEPLOY_BRANCH}}"
PYTHON_BIN="${PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"
PIP_BIN="${PIP_BIN:-${APP_DIR}/.venv/bin/pip}"

echo "[1/10] Entering ${APP_DIR}"
cd "${APP_DIR}"

echo "[2/10] Verifying repository and environment"
if [[ ! -d ".git" ]]; then
  echo "ERROR: ${APP_DIR} is not a git repository."
  exit 1
fi
if [[ ! -f ".env" ]]; then
  echo "ERROR: ${APP_DIR}/.env does not exist."
  exit 1
fi

echo "[3/10] Fetching ${DEPLOY_BRANCH} + deploy ref ${DEPLOY_REF}"
git fetch origin --prune "${DEPLOY_BRANCH}"
git fetch origin "${DEPLOY_REF}" || true

if [[ "${DEPLOY_REF}" == "${DEPLOY_BRANCH}" ]]; then
  echo "[4/10] Checking out origin/${DEPLOY_BRANCH}"
  git checkout "${DEPLOY_BRANCH}" || git checkout -B "${DEPLOY_BRANCH}" "origin/${DEPLOY_BRANCH}"
  git reset --hard "origin/${DEPLOY_BRANCH}"
else
  echo "[4/10] Checking out deploy ref ${DEPLOY_REF}"
  if git rev-parse --verify --quiet "${DEPLOY_REF}" >/dev/null; then
    git checkout --detach "${DEPLOY_REF}"
  else
    git checkout --detach FETCH_HEAD
  fi
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[5/10] Creating virtual environment"
  python3 -m venv "${APP_DIR}/.venv"
else
  echo "[5/10] Virtual environment already present"
fi

echo "[6/10] Installing dependencies"
"${PYTHON_BIN}" -m pip install --upgrade pip
"${PIP_BIN}" install -r requirements.txt

echo "[7/10] Running compile checks"
PYTHONPATH=. "${PYTHON_BIN}" -m compileall apps rob scripts

echo "[8/10] Running migrations and DB checks"
set -a
source .env
set +a
PYTHONPATH=. "${PYTHON_BIN}" scripts/run_migrations.py
PYTHONPATH=. "${PYTHON_BIN}" -m scripts.check_db

echo "[9/10] Restarting ${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,12p'

echo "[10/10] Verifying service active state"
sudo systemctl is-active "${SERVICE_NAME}"
printf '\nBot deploy complete.\n'
