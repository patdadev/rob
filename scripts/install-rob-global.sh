#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_ROB="${APP_ROOT}/scripts/rob"
SOURCE_ROBCTL="${APP_ROOT}/scripts/robctl"
TARGET_BIN_DIR="${HOME}/.local/bin"
TARGET_ROB="${TARGET_BIN_DIR}/rob"
TARGET_ROBCTL="${TARGET_BIN_DIR}/robctl"
MARKER_START="# >>> rob global command >>>"
MARKER_END="# <<< rob global command <<<"

ensure_executable() {
  local file="$1"
  if [[ ! -x "${file}" ]]; then
    chmod +x "${file}"
  fi
}

ensure_executable "${SOURCE_ROB}"
ensure_executable "${SOURCE_ROBCTL}"

mkdir -p "${TARGET_BIN_DIR}"
ln -sf "${SOURCE_ROB}" "${TARGET_ROB}"
ln -sf "${SOURCE_ROBCTL}" "${TARGET_ROBCTL}"

append_shell_block() {
  local rc_file="$1"
  [[ -f "${rc_file}" ]] || touch "${rc_file}"

  if grep -q "${MARKER_START}" "${rc_file}"; then
    return
  fi

  cat >> "${rc_file}" <<'EOF'
# >>> rob global command >>>
if [ -d "$HOME/.local/bin" ]; then
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
  esac
fi

rob() {
  "$HOME/.local/bin/rob" "$@"
}

robctl() {
  "$HOME/.local/bin/rob" "$@"
}
# <<< rob global command <<<
EOF
}

append_shell_block "${HOME}/.bashrc"
append_shell_block "${HOME}/.bash_profile"
append_shell_block "${HOME}/.zshrc"
append_shell_block "${HOME}/.zprofile"
append_shell_block "${HOME}/.profile"

cat <<EOF
Installed Rob globally:
  ${TARGET_ROB} -> ${SOURCE_ROB}
  ${TARGET_ROBCTL} -> ${SOURCE_ROBCTL}

Added shell functions to:
  ${HOME}/.bashrc
  ${HOME}/.bash_profile
  ${HOME}/.zshrc
  ${HOME}/.zprofile
  ${HOME}/.profile

Restart your shell or run:
  export PATH="\$HOME/.local/bin:\$PATH"
  source "${HOME}/.bashrc" 2>/dev/null || true
  source "${HOME}/.bash_profile" 2>/dev/null || true
  source "${HOME}/.zshrc" 2>/dev/null || true
  source "${HOME}/.zprofile" 2>/dev/null || true

Then verify:
  rob
EOF
