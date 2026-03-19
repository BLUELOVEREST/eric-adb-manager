#!/usr/bin/env bash

set -euo pipefail

REPO="BLUELOVEREST/eric-adb-manager"
REF="main"
INSTALL_ROOT="${HOME}/.local/share/eam"
BIN_DIR="${HOME}/.local/bin"
CONFIG_PATH="${HOME}/.config/eam/servers.yaml"
SKIP_SHELL=0
FORCE_CONFIG=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Options:
  --install-root PATH   Install source files to PATH, default: ~/.local/share/eam
  --bin-dir PATH        Link eam into PATH, default: ~/.local/bin
  --config PATH         Config path, default: ~/.config/eam/servers.yaml
  --skip-shell          Do not modify ~/.zshrc
  --force-config        Reinitialize config if it already exists
  -h, --help            Show this help

Example:
  curl -fsSL https://raw.githubusercontent.com/BLUELOVEREST/eric-adb-manager/main/install.sh | bash
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

append_zshrc() {
  local zshrc="$HOME/.zshrc"
  local marker="# eam completion"
  local line='eval "$(eam completion zsh)"'

  if [[ ! -f "$zshrc" ]]; then
    touch "$zshrc"
  fi

  if grep -Fq "$line" "$zshrc"; then
    return 0
  fi

  {
    echo
    echo "$marker"
    echo "$line"
  } >>"$zshrc"
}

download_archive() {
  local tmpdir="$1"
  local archive="${tmpdir}/eam.tar.gz"
  local url="https://github.com/${REPO}/archive/${REF}.tar.gz"

  curl -fsSL "$url" -o "$archive"
  tar -xzf "$archive" -C "$tmpdir"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo)
        echo "--repo is no longer supported" >&2
        exit 2
        ;;
      --ref)
        echo "--ref is no longer supported" >&2
        shift 2
        ;;
      --install-root)
        INSTALL_ROOT="${2:-}"
        shift 2
        ;;
      --bin-dir)
        BIN_DIR="${2:-}"
        shift 2
        ;;
      --config)
        CONFIG_PATH="${2:-}"
        shift 2
        ;;
      --skip-shell)
        SKIP_SHELL=1
        shift
        ;;
      --force-config)
        FORCE_CONFIG=1
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

  require_cmd curl
  require_cmd tar
  require_cmd python3
  require_cmd adb

  local tmpdir
  tmpdir="$(mktemp -d)"
  trap "rm -rf '$tmpdir'" EXIT

  download_archive "$tmpdir"

  local extracted
  extracted="$(find "$tmpdir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [[ -z "$extracted" ]]; then
    echo "failed to unpack archive" >&2
    exit 1
  fi

  mkdir -p "$(dirname "$INSTALL_ROOT")"
  rm -rf "$INSTALL_ROOT"
  mkdir -p "$INSTALL_ROOT"
  cp -R "$extracted"/. "$INSTALL_ROOT"/

  mkdir -p "$BIN_DIR"
  ln -sf "$INSTALL_ROOT/bin/eam" "$BIN_DIR/eam"

  if [[ $FORCE_CONFIG -eq 1 ]]; then
    "$BIN_DIR/eam" init --config "$CONFIG_PATH" --force
  elif [[ ! -f "$CONFIG_PATH" ]]; then
    "$BIN_DIR/eam" init --config "$CONFIG_PATH"
  fi

  if [[ $SKIP_SHELL -eq 0 ]]; then
    append_zshrc
  fi

  cat <<EOF
Installed eam
  source: $INSTALL_ROOT
  binary: $BIN_DIR/eam
  config: $CONFIG_PATH

Ensure your PATH includes:
  export PATH="$BIN_DIR:\$PATH"
EOF
}

main "$@"
