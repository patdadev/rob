#!/usr/bin/env bash
set -Eeuo pipefail

# Rob Portal Dev - First-Time Installer
#
# Installs the Django Rob Portal as its own service on the webhook/web server.
#
# Default install:
#   /opt/rob-portal/app
#   rob-portal-dev.service
#   127.0.0.1:8090
#
# This script does NOT overwrite .env.
# This script does NOT configure Nginx automatically.
# This script does NOT print secrets.

APP_PARENT="${APP_PARENT:-/opt/rob-portal}"
APP_DIR="${APP_DIR:-${APP_PARENT}/app}"
REPO_URL="${REPO_URL:-https://github.com/PlainStack2/rob-dev.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-rob-portal-dev.service}"
SERVICE_USER="${SERVICE_USER:-deployuser}"
SERVICE_GROUP="${SERVICE_GROUP:-deployuser}"
PYTHON_BIN="${PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"
PIP_BIN="${PIP_BIN:-${APP_DIR}/.venv/bin/pip}"
SYSTEMD_SOURCE="${SYSTEMD_SOURCE:-${APP_DIR}/deploy/systemd/rob-portal-dev.service}"
SYSTEMD_TARGET="/etc/systemd/system/${SERVICE_NAME}"

print_step() {
  printf '\n[%s] %s\n' "$1" "$2"
}

fail() {
  printf '\nERROR: %s\n' "$1" >&2
  exit 1
}

require_root_or_sudo() {
  if [[ "${EUID}" -ne 0 ]] && ! sudo -n true 2>/dev/null; then
    fail "This installer needs sudo access for package installation and systemd setup."
  fi
}

ensure_user_exists() {
  if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    print_step "INFO" "Creating service user ${SERVICE_USER}"
    sudo adduser --system --group --home "${APP_PARENT}" "${SERVICE_USER}"
  fi
}

install_packages() {
  print_step "1/11" "Installing required OS packages"

  sudo apt-get update -y
  sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    git \
    curl \
    ca-certificates
}

prepare_directories() {
  print_step "2/11" "Preparing ${APP_PARENT}"

  sudo mkdir -p "${APP_PARENT}"
  sudo chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_PARENT}"
}

clone_or_update_repo() {
  print_step "3/11" "Cloning or updating repository"

  if [[ -d "${APP_DIR}/.git" ]]; then
    sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" fetch origin --prune
    sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" checkout "${DEPLOY_BRANCH}"
    sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" reset --hard "origin/${DEPLOY_BRANCH}"
  else
    sudo -u "${SERVICE_USER}" git clone --branch "${DEPLOY_BRANCH}" "${REPO_URL}" "${APP_DIR}"
  fi
}

create_venv() {
  print_step "4/11" "Creating Python virtual environment"

  if [[ ! -x "${PYTHON_BIN}" ]]; then
    sudo -u "${SERVICE_USER}" python3 -m venv "${APP_DIR}/.venv"
  else
    printf 'Virtual environment already exists.\n'
  fi
}

install_python_dependencies() {
  print_step "5/11" "Installing Python dependencies"

  sudo -u "${SERVICE_USER}" "${PYTHON_BIN}" -m pip install --upgrade pip
  sudo -u "${SERVICE_USER}" "${PIP_BIN}" install -r "${APP_DIR}/requirements.txt" -r "${APP_DIR}/portal/requirements.txt"
}

create_env_if_missing() {
  print_step "6/11" "Checking portal .env"

  if [[ -f "${APP_DIR}/.env" ]]; then
    printf '%s already exists. Leaving it untouched.\n' "${APP_DIR}/.env"
    return
  fi

  if [[ -f "${APP_DIR}/.env.example" ]]; then
    sudo -u "${SERVICE_USER}" cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  else
    sudo -u "${SERVICE_USER}" touch "${APP_DIR}/.env"
  fi

  cat <<EOF

Created ${APP_DIR}/.env.

You must edit it before starting the portal.

Required portal values:

ROB_PORTAL_ENABLED=true
ROB_PORTAL_ENV=dev
ROB_PORTAL_BASE_URL=https://rob-dev.barecoding.com
ROB_PORTAL_ALLOWED_HOSTS=rob-dev.barecoding.com,127.0.0.1,localhost
ROB_PORTAL_CSRF_TRUSTED_ORIGINS=https://rob-dev.barecoding.com
ROB_PORTAL_SECRET_KEY=<generate-a-long-random-secret>
ROB_PORTAL_SUPERADMIN_USER_IDS=<your-discord-user-id>

DISCORD_CLIENT_ID=<discord-oauth-client-id>
DISCORD_CLIENT_SECRET=<discord-oauth-client-secret>
DISCORD_REDIRECT_URI=https://rob-dev.barecoding.com/portal/auth/discord/callback/

PORTAL_DATABASE_URL=postgresql://rob_dev_portal:<password>@<host>:<port>/rob_dev?sslmode=require

ROB_OPS_HOST=<bot-server-or-localhost>
ROB_OPS_PORT=8811
ROB_OPS_SECRET=<same-secret-as-bot-if-used>

EOF
}

patch_systemd_unit_if_needed() {
  print_step "7/11" "Installing systemd service"

  [[ -f "${SYSTEMD_SOURCE}" ]] || fail "Systemd source file not found: ${SYSTEMD_SOURCE}"

  tmp_unit="$(mktemp)"

  sed \
    -e "s#User=deployuser#User=${SERVICE_USER}#g" \
    -e "s#Group=deployuser#Group=${SERVICE_GROUP}#g" \
    -e "s#WorkingDirectory=/opt/rob-portal/app/portal#WorkingDirectory=${APP_DIR}/portal#g" \
    -e "s#EnvironmentFile=/opt/rob-portal/app/.env#EnvironmentFile=${APP_DIR}/.env#g" \
    -e "s#ExecStart=/opt/rob-portal/app/.venv/bin/gunicorn rob_portal.wsgi:application --bind 127.0.0.1:8090#ExecStart=${APP_DIR}/.venv/bin/gunicorn rob_portal.wsgi:application --bind 127.0.0.1:8090#g" \
    "${SYSTEMD_SOURCE}" > "${tmp_unit}"

  sudo cp "${tmp_unit}" "${SYSTEMD_TARGET}"
  rm -f "${tmp_unit}"

  sudo systemctl daemon-reload
  sudo systemctl enable "${SERVICE_NAME}"
}

compile_check() {
  print_step "8/11" "Running compile check"

  cd "${APP_DIR}"
  sudo -u "${SERVICE_USER}" env PYTHONPATH=. "${PYTHON_BIN}" -m compileall apps rob scripts portal
}

check_env_configured() {
  print_step "9/11" "Checking whether portal .env appears configured"

  env_file="${APP_DIR}/.env"

  if ! grep -q '^ROB_PORTAL_ENABLED=true' "${env_file}" 2>/dev/null; then
    cat <<EOF

Portal is installed but not started.

Reason:
  ROB_PORTAL_ENABLED=true is not set in ${env_file}

Edit the file, then run:

  sudo systemctl start ${SERVICE_NAME}

EOF
    return 1
  fi

  required_keys=(
    "ROB_PORTAL_SECRET_KEY="
    "ROB_PORTAL_SUPERADMIN_USER_IDS="
    "DISCORD_CLIENT_ID="
    "DISCORD_CLIENT_SECRET="
    "DISCORD_REDIRECT_URI="
  )

  for key in "${required_keys[@]}"; do
    if ! grep -q "^${key}" "${env_file}" 2>/dev/null; then
      cat <<EOF

Portal is installed but not started.

Reason:
  Missing ${key} in ${env_file}

Edit the file, then run:

  sudo systemctl start ${SERVICE_NAME}

EOF
      return 1
    fi
  done

  if ! grep -q '^PORTAL_DATABASE_URL=' "${env_file}" 2>/dev/null && ! grep -q '^DATABASE_URL=' "${env_file}" 2>/dev/null; then
    cat <<EOF

Portal is installed but not started.

Reason:
  Missing PORTAL_DATABASE_URL or DATABASE_URL in ${env_file}

Edit the file, then run:

  sudo systemctl start ${SERVICE_NAME}

EOF
    return 1
  fi

  return 0
}

run_deploy_if_configured() {
  print_step "10/11" "Running portal deploy steps if configured"

  if check_env_configured; then
    cd "${APP_DIR}"

    set -a
    # shellcheck disable=SC1090
    source "${APP_DIR}/.env"
    set +a

    sudo -u "${SERVICE_USER}" env PYTHONPATH=. "${PYTHON_BIN}" -m scripts.run_migrations
    sudo -u "${SERVICE_USER}" env PYTHONPATH=. "${PYTHON_BIN}" -m scripts.check_db

    cd "${APP_DIR}/portal"
    sudo -u "${SERVICE_USER}" "${PYTHON_BIN}" manage.py migrate --noinput
    sudo -u "${SERVICE_USER}" "${PYTHON_BIN}" manage.py collectstatic --noinput
    sudo -u "${SERVICE_USER}" "${PYTHON_BIN}" manage.py check

    sudo systemctl restart "${SERVICE_NAME}"
    sudo systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,14p'
  fi
}

print_nginx_instructions() {
  print_step "11/11" "Next steps"

  cat <<EOF

Rob Portal install complete.

Service:
  ${SERVICE_NAME}

App directory:
  ${APP_DIR}

Portal listens on:
  127.0.0.1:8090

Recommended public URL:
  https://rob-dev.barecoding.com/portal/

Add this to the Nginx server block for rob-dev.barecoding.com.
Place it above any generic location / proxy rule.

------------------------------------------------------------
location /portal/static/ {
    alias ${APP_DIR}/portal/staticfiles/;
    access_log off;
    expires 1h;
}

location /portal/ {
    proxy_pass http://127.0.0.1:8090/portal/;
    proxy_http_version 1.1;

    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;

    proxy_redirect off;
}
------------------------------------------------------------

Then test Nginx and reload:

  sudo nginx -t
  sudo systemctl reload nginx

Cloudflare:
  - DNS A/CNAME should already point rob-dev.barecoding.com to this server.
  - SSL/TLS mode should be Full (strict).
  - Add a cache bypass rule for /portal/*.

Discord Developer Portal:
  Add OAuth redirect URL:

  https://rob-dev.barecoding.com/portal/auth/discord/callback/

Useful commands:

  sudo systemctl status ${SERVICE_NAME} --no-pager
  sudo journalctl -u ${SERVICE_NAME} -n 100 --no-pager
  sudo systemctl restart ${SERVICE_NAME}

EOF
}

main() {
  require_root_or_sudo
  ensure_user_exists
  install_packages
  prepare_directories
  clone_or_update_repo
  create_venv
  install_python_dependencies
  create_env_if_missing
  patch_systemd_unit_if_needed
  compile_check
  run_deploy_if_configured || true
  print_nginx_instructions
}

main "$@"
