#!/usr/bin/env bash
set -Eeuo pipefail

WEBHOOK_ENV_FILE="${WEBHOOK_ENV_FILE:-/opt/rob-webhook/app/.env}"
PUBLIC_HOSTNAME="${PUBLIC_HOSTNAME:-throne.robthebot.com}"
ORIGIN_URL="${ORIGIN_URL:-http://127.0.0.1:8080}"
CONFIG_FILE="${CONFIG_FILE:-/etc/cloudflared/config.yml}"
CLOUDFLARED_CONFIG="${CONFIG_FILE}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-/etc/cloudflared/rob-webhook.json}"

log() {
  printf '[install-cloudflared-webhook] %s\n' "$*"
}

die() {
  printf '[install-cloudflared-webhook] error: %s\n' "$*" >&2
  exit 1
}

backup_existing_config() {
  if [[ -f "${CLOUDFLARED_CONFIG}" ]]; then
    local backup_path
    backup_path="${CLOUDFLARED_CONFIG}.bak-$(date +%Y%m%d-%H%M%S)"
    log "Backing up existing ${CLOUDFLARED_CONFIG} to ${backup_path}"
    cp -a "${CLOUDFLARED_CONFIG}" "${backup_path}"
  fi
}

ensure_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Run this script with sudo or as root."
  fi
}

install_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    log "cloudflared is already installed."
    return
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    die "cloudflared is not installed and apt-get is unavailable. Install cloudflared manually first."
  fi

  log "Installing cloudflared from the official Cloudflare apt repository."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y curl ca-certificates gnupg lsb-release
  install -d -m 0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
    | gpg --dearmor \
    | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
  local codename
  codename="$(lsb_release -cs)"
  cat > /etc/apt/sources.list.d/cloudflared.list <<EOF
deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared ${codename} main
EOF
  apt-get update -y
  apt-get install -y cloudflared
}

warn_webhook_env_values() {
  if [[ ! -f "${WEBHOOK_ENV_FILE}" ]]; then
    log "WARNING: ${WEBHOOK_ENV_FILE} not found; skipping webhook env checks."
    return
  fi

  local base_url
  base_url="$(grep -E '^THRONE_WEBHOOK_BASE_URL=' "${WEBHOOK_ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
  base_url="${base_url#\"}"
  base_url="${base_url%\"}"

  if [[ -n "${base_url}" && "${base_url}" != "https://throne.robthebot.com" ]]; then
    log "WARNING: THRONE_WEBHOOK_BASE_URL is '${base_url}' but should be https://throne.robthebot.com."
  fi

  if grep -E '^DISCORD_TOKEN=' "${WEBHOOK_ENV_FILE}" >/dev/null 2>&1; then
    log "WARNING: DISCORD_TOKEN is present in webhook .env; this host should stay webhook-only."
  fi
}

install_token_managed_tunnel() {
  local tunnel_token=""
  read -r -s -p "Paste Cloudflare tunnel token for ${PUBLIC_HOSTNAME}: " tunnel_token
  echo
  [[ -n "${tunnel_token}" ]] || die "Tunnel token cannot be empty."

  log "Installing cloudflared service using token-managed tunnel."
  cloudflared service install "${tunnel_token}"
  unset tunnel_token
}

write_named_tunnel_config() {
  local tunnel_id="$1"
  install -d -m 0750 /etc/cloudflared
  backup_existing_config

  cat > "${CLOUDFLARED_CONFIG}" <<EOF
tunnel: ${tunnel_id}
credentials-file: ${CREDENTIALS_FILE}
ingress:
  - hostname: ${PUBLIC_HOSTNAME}
    service: ${ORIGIN_URL}
  - service: http_status:404
EOF
  chmod 0640 "${CLOUDFLARED_CONFIG}"
  log "Wrote ${CLOUDFLARED_CONFIG} for named tunnel ingress."
}

install_named_tunnel() {
  local tunnel_name="${TUNNEL_NAME:-rob-webhook}"
  local credentials_file="${CREDENTIALS_FILE}"
  if [[ ! -f "${credentials_file}" ]]; then
    die "Named tunnel ${tunnel_name} exists, but ${credentials_file} was not found.

Please copy the correct credentials JSON for this exact tunnel to:
${credentials_file}

Then rerun this script."
  fi
  local tunnel_id=""
  read -r -p "Enter tunnel UUID for named tunnel mode: " tunnel_id
  [[ -n "${tunnel_id}" ]] || die "Tunnel UUID cannot be empty."

  write_named_tunnel_config "${tunnel_id}"

  if ! systemctl list-unit-files cloudflared.service >/dev/null 2>&1; then
    log "Installing cloudflared service unit."
    cloudflared service install
  fi
}

choose_mode() {
  local choice=""
  echo "Choose Cloudflared mode:"
  echo "  1) Token-managed tunnel (Cloudflare Zero Trust managed)"
  echo "  2) Named tunnel with local ingress config (${CONFIG_FILE})"
  read -r -p "Selection [1/2]: " choice
  case "${choice}" in
    1) install_token_managed_tunnel ;;
    2) install_named_tunnel ;;
    *) die "Invalid selection." ;;
  esac
}

restart_and_verify() {
  log "Restarting cloudflared service"
  systemctl daemon-reload
  systemctl enable cloudflared
  systemctl restart cloudflared
  systemctl --no-pager --full status cloudflared | sed -n '1,16p'
}

print_summary() {
  cat <<EOF

Cloudflared webhook setup complete.

Routing target:
  https://${PUBLIC_HOSTNAME} -> ${ORIGIN_URL}

Validation commands:
  curl -fsS http://127.0.0.1:8080/health
  curl -I https://${PUBLIC_HOSTNAME}/health
  sudo systemctl status cloudflared --no-pager
  sudo journalctl -u cloudflared -n 100 --no-pager

Notes:
  - Do not expose port 8080 publicly.
  - Do not commit tunnel tokens or credentials into the repository.
  - Named tunnel mode requires ${CREDENTIALS_FILE}; this script will not guess credential files.
  - Host-level routing keeps /health reachable for validation checks.
EOF
}

main() {
  ensure_root
  install_cloudflared
  warn_webhook_env_values
  choose_mode
  restart_and_verify
  print_summary
}

main "$@"
