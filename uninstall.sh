#!/usr/bin/env bash

set -euo pipefail

INSTALL_ROOT="${HOME}/.local/share/eam"
BIN_DIR="${HOME}/.local/bin"
REMOVE_CONFIG=0

usage() {
  cat <<'EOF'
Usage: uninstall.sh [options]

Options:
  --install-root PATH   Installed source root, default: ~/.local/share/eam
  --bin-dir PATH        Binary directory, default: ~/.local/bin
  --remove-config       Also remove ~/.config/eam
  -h, --help            Show this help
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --install-root)
        INSTALL_ROOT="${2:-}"
        shift 2
        ;;
      --bin-dir)
        BIN_DIR="${2:-}"
        shift 2
        ;;
      --remove-config)
        REMOVE_CONFIG=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "unknown argument: $1" >&2
        usage >&2
        exit 2
        ;;
    esac
  done
}

main() {
  parse_args "$@"

  rm -rf "$INSTALL_ROOT"
  rm -f "$BIN_DIR/eam"

  if [[ $REMOVE_CONFIG -eq 1 ]]; then
    rm -rf "${HOME}/.config/eam"
  fi

  echo "Removed eam from $INSTALL_ROOT"
}

main "$@"
