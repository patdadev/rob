#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_ROBCTL="${APP_ROOT}/scripts/robctl"
TARGET_BIN_DIR="${HOME}/.local/bin"
TARGET_ROBCTL="${TARGET_BIN_DIR}/robctl"
MARKER_START="# >>> robctl global path >>>"
MARKER_END="# <<< robctl global path <<<"

if [[ ! -x "${SOURCE_ROBCTL}" ]]; then
  chmod +x "${SOURCE_ROBCTL}"
fi

mkdir -p "${TARGET_BIN_DIR}"
ln -sf "${SOURCE_ROBCTL}" "${TARGET_ROBCTL}"

append_path_block() {
  local rc_file="$1"
  [[ -f "${rc_file}" ]] || touch "${rc_file}"
  if grep -q "${MARKER_START}" "${rc_file}"; then
    return
  fi
  cat >> "${rc_file}" <<EOF
${MARKER_START}
if [ -d "\$HOME/.local/bin" ]; then
  case ":\$PATH:" in
    *":\$HOME/.local/bin:"*) ;;
    *) export PATH="\$HOME/.local/bin:\$PATH" ;;
  esac
fi
${MARKER_END}
EOF
}

append_path_block "${HOME}/.bashrc"
append_path_block "${HOME}/.zshrc"

cat <<EOF
Installed robctl globally:
  ${TARGET_ROBCTL} -> ${SOURCE_ROBCTL}

Restart your shell or run:
  export PATH="\$HOME/.local/bin:\$PATH"

Then verify:
  robctl
EOF
