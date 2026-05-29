#!/usr/bin/env bash
set -euo pipefail

DEFAULT_TUNNEL_NAME="rob-webhook"
DEFAULT_PUBLIC_HOSTNAME="throne.robthebot.com"
DEFAULT_SERVICE_URL="http://127.0.0.1:8080"
CLOUDFLARED_DIR="/etc/cloudflared"
CLOUDFLARED_CONFIG="${CLOUDFLARED_DIR}/config.yml"
WEBHOOK_ENV_FILE="${WEBHOOK_ENV_FILE:-/opt/rob-webhook/app/.env}"

log() {
  printf '[install-cloudflared-webhook] %s\n' "$*"
}

warn() {
  printf '[install-cloudflared-webhook] warning: %s\n' "$*" >&2
}

die() {
  printf '[install-cloudflared-webhook] error: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Run this script with sudo or as root."
  fi
}

prompt_with_default() {
  local prompt="$1"
  local default_value="$2"
  local value=""

  read -r -p "${prompt} [${default_value}]: " value
  printf '%s' "${value:-${default_value}}"
}

prompt_yes_no() {
  local prompt="$1"
  local answer=""

  read -r -p "${prompt} [y/N]: " answer
  case "${answer}" in
    [Yy]|[Yy][Ee][Ss]) return 0 ;;
    *) return 1 ;;
  esac
}

install_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    log "cloudflared is already installed: $(command -v cloudflared)"
    cloudflared --version || true
    return
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    die "This installer supports Ubuntu/Debian hosts with apt-get. Install cloudflared manually on this OS."
  fi

  log "Installing cloudflared for Ubuntu/Debian"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y curl ca-certificates gnupg lsb-release

  install -d -m 0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
    | gpg --dearmor \
    | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

  local codename
  codename="$(lsb_release -cs)"
  cat > /etc/apt/sources.list.d/cloudflared.list <<EOF_REPO
# Cloudflare packages for cloudflared
deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared ${codename} main
EOF_REPO

  apt-get update -y
  apt-get install -y cloudflared
}

find_origin_cert() {
  local cert=""

  if [[ -f /root/.cloudflared/cert.pem ]]; then
    printf '%s' /root/.cloudflared/cert.pem
    return 0
  fi

  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    local sudo_home
    sudo_home="$(getent passwd "${SUDO_USER}" | cut -d: -f6 || true)"
    if [[ -n "${sudo_home}" && -f "${sudo_home}/.cloudflared/cert.pem" ]]; then
      printf '%s' "${sudo_home}/.cloudflared/cert.pem"
      return 0
    fi
  fi

  return 1
}

cloudflared_with_cert() {
  local cert="$1"
  shift

  if [[ -n "${cert}" ]]; then
    TUNNEL_ORIGIN_CERT="${cert}" cloudflared "$@"
  else
    cloudflared "$@"
  fi
}

backup_existing_config() {
  if [[ -f "${CLOUDFLARED_CONFIG}" ]]; then
    local backup_path
    backup_path="${CLOUDFLARED_CONFIG}.bak-$(date +%Y%m%d-%H%M%S)"
    log "Backing up existing ${CLOUDFLARED_CONFIG} to ${backup_path}"
    cp -a "${CLOUDFLARED_CONFIG}" "${backup_path}"
  fi
}

set_cloudflared_permissions() {
  chown -R root:root "${CLOUDFLARED_DIR}"
  chmod 700 "${CLOUDFLARED_DIR}"
  find "${CLOUDFLARED_DIR}" -maxdepth 1 -type f -name '*.json' -exec chmod 600 {} +
  if [[ -f "${CLOUDFLARED_CONFIG}" ]]; then
    chmod 644 "${CLOUDFLARED_CONFIG}"
  fi
}

install_token_service() {
  local token="$1"

  log "Installing cloudflared systemd service with the supplied Cloudflare-managed tunnel token"
  cloudflared service install "${token}"
  log "The token was not printed or written to the repository by this script. cloudflared may store service credentials locally as part of the tunnel service install."
  systemctl enable cloudflared
  systemctl restart cloudflared
  systemctl status cloudflared --no-pager || true
}

create_named_tunnel_if_needed() {
  local tunnel_name="$1"
  local origin_cert="$2"
  local credentials_file="$3"

  if cloudflared_with_cert "${origin_cert}" tunnel info "${tunnel_name}" >/dev/null 2>&1; then
    log "Named tunnel ${tunnel_name} already exists."
    return
  fi

  log "Creating named tunnel ${tunnel_name}"
  cloudflared_with_cert "${origin_cert}" tunnel create --credentials-file "${credentials_file}" "${tunnel_name}"
}

require_named_tunnel_credentials() {
  local tunnel_name="$1"
  local credentials_file="${CLOUDFLARED_DIR}/${tunnel_name}.json"

  if [[ -f "${credentials_file}" ]]; then
    printf '%s' "${credentials_file}"
    return 0
  fi

  die "Named tunnel ${tunnel_name} exists, but ${credentials_file} was not found.

Please copy the correct credentials JSON for this exact tunnel to:
${credentials_file}

Then rerun this script."
}

write_named_tunnel_config() {
  local tunnel_name="$1"
  local public_hostname="$2"
  local service_url="$3"
  local credentials_file="$4"

  install -d -m 0700 -o root -g root "${CLOUDFLARED_DIR}"
  backup_existing_config

  log "Writing ${CLOUDFLARED_CONFIG}"
  cat > "${CLOUDFLARED_CONFIG}" <<EOF_CONFIG
tunnel: ${tunnel_name}
credentials-file: ${credentials_file}

ingress:
  - hostname: ${public_hostname}
    service: ${service_url}
  - service: http_status:404
EOF_CONFIG

  set_cloudflared_permissions
}

install_named_tunnel_service() {
  log "Installing cloudflared systemd service for locally managed named tunnel"
  cloudflared service install
  systemctl enable cloudflared
  systemctl restart cloudflared
  systemctl status cloudflared --no-pager || true
}

warn_if_webhook_env_mismatch() {
  local expected_base_url="$1"

  if [[ ! -f "${WEBHOOK_ENV_FILE}" ]]; then
    warn "Webhook .env not found at ${WEBHOOK_ENV_FILE}; keep THRONE_WEBHOOK_HOST=127.0.0.1, THRONE_WEBHOOK_PORT=8080, and THRONE_WEBHOOK_BASE_URL=${expected_base_url}."
    return
  fi

  local current_base_url=""
  current_base_url="$(grep -E '^THRONE_WEBHOOK_BASE_URL=' "${WEBHOOK_ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
  if [[ "${current_base_url}" != "${expected_base_url}" ]]; then
    warn "${WEBHOOK_ENV_FILE} has THRONE_WEBHOOK_BASE_URL=${current_base_url:-<unset>}; expected ${expected_base_url}."
  fi
}

print_no_token_guidance() {
  cat <<'EOF_GUIDANCE'

No Cloudflare tunnel token supplied.

Recommended Cloudflare-managed flow:
  1. Open the Cloudflare Zero Trust dashboard.
  2. Create a tunnel for the webhook host.
  3. Add a public hostname route for throne.robthebot.com to http://127.0.0.1:8080.
  4. Copy the tunnel install token and rerun this script.

Alternatively, run cloudflared tunnel login first, then this script can create and configure a locally managed named tunnel.
EOF_GUIDANCE
}

print_validation() {
  local public_hostname="$1"
  local service_url="$2"

  cat <<EOF_VALIDATION

Cloudflared webhook setup next steps and validation:

Webhook app environment should remain local-only:
  THRONE_WEBHOOK_HOST=127.0.0.1
  THRONE_WEBHOOK_PORT=8080
  THRONE_WEBHOOK_BASE_URL=https://${public_hostname}

Expected Cloudflare route:
  Hostname: ${public_hostname}
  Service:  ${service_url}

Check the service:
  systemctl status cloudflared --no-pager
  journalctl -u cloudflared -n 100 --no-pager

Check webhook health:
  curl -fsS http://127.0.0.1:8080/health
  curl -I https://${public_hostname}/health

The external HTTPS check may fail until DNS and tunnel routing have propagated.
EOF_VALIDATION
}

main() {
  require_root

  local tunnel_name
  local public_hostname
  local service_url

  tunnel_name="$(prompt_with_default "Cloudflare tunnel name" "${DEFAULT_TUNNEL_NAME}")"
  public_hostname="$(prompt_with_default "Public hostname" "${DEFAULT_PUBLIC_HOSTNAME}")"
  service_url="$(prompt_with_default "Local service URL" "${DEFAULT_SERVICE_URL}")"

  install_cloudflared

  if prompt_yes_no "Do you have a Cloudflare tunnel token?"; then
    local tunnel_token=""
    read -r -s -p "Cloudflare tunnel token: " tunnel_token
    printf '\n'
    if [[ -z "${tunnel_token}" ]]; then
      die "Tunnel token cannot be empty when token-based setup is selected."
    fi
    install_token_service "${tunnel_token}"
    unset tunnel_token
    warn_if_webhook_env_mismatch "https://${public_hostname}"
    print_validation "${public_hostname}" "${service_url}"
    return
  fi

  print_no_token_guidance

  local origin_cert=""
  if ! origin_cert="$(find_origin_cert)"; then
    die "No cloudflared tunnel login credentials found. Rerun with a Cloudflare tunnel token or run cloudflared tunnel login first."
  fi

  log "Using cloudflared origin certificate at ${origin_cert}"
  install -d -m 0700 -o root -g root "${CLOUDFLARED_DIR}"

  local credentials_file
  credentials_file="${CLOUDFLARED_DIR}/${tunnel_name}.json"
  create_named_tunnel_if_needed "${tunnel_name}" "${origin_cert}" "${credentials_file}"
  credentials_file="$(require_named_tunnel_credentials "${tunnel_name}")"

  log "Creating DNS route ${public_hostname} -> ${tunnel_name}"
  if ! cloudflared_with_cert "${origin_cert}" tunnel route dns "${tunnel_name}" "${public_hostname}"; then
    warn "Could not create DNS route automatically. If it already exists, this may be safe to ignore; otherwise configure ${public_hostname} in Cloudflare."
  fi

  write_named_tunnel_config "${tunnel_name}" "${public_hostname}" "${service_url}" "${credentials_file}"
  install_named_tunnel_service
  warn_if_webhook_env_mismatch "https://${public_hostname}"
  print_validation "${public_hostname}" "${service_url}"
}

main "$@"
