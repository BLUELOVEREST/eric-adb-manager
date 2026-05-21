#!/system/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNTIME_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PARENT_DIR=$(CDPATH= cd -- "$RUNTIME_DIR/.." && pwd)
TEMPLATE_HOME_DIR="$RUNTIME_DIR/root-home"

DEFAULT_HOME_DIR="$PARENT_DIR"
# Override this at launch time with ZSH_HOME_DIR=/your/home/path if needed.
HOME_DIR="${ZSH_HOME_DIR:-/data/local/zhangzhicheng}"

export PATH="$RUNTIME_DIR/bin:${PATH:-/system/bin}"
export LD_LIBRARY_PATH="$RUNTIME_DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TERMINFO="$RUNTIME_DIR/share/terminfo"
export FPATH="$RUNTIME_DIR/share/zsh/5.9/functions:$RUNTIME_DIR/share/zsh/site-functions${FPATH:+:$FPATH}"
export HOME="$HOME_DIR"
export ZDOTDIR="$HOME"
export SHELL="$RUNTIME_DIR/bin/zsh"
export TMPDIR="$RUNTIME_DIR/tmp"
export TERM="${TERM:-xterm-256color}"
export ZSH="$HOME/.oh-my-zsh"

mkdir -p "$TMPDIR" "$HOME/.cache" "$HOME/.config"

sync_template_item() {
  src="$1"
  dst="$2"
  [ -e "$dst" ] && return 0
  cp -R "$src" "$dst"
}

sync_template_item "$TEMPLATE_HOME_DIR/.zshrc" "$HOME/.zshrc"
sync_template_item "$TEMPLATE_HOME_DIR/.oh-my-zsh" "$HOME/.oh-my-zsh"

if [ "$#" -eq 0 ]; then
  exec "$RUNTIME_DIR/bin/zsh" -i
fi

exec "$RUNTIME_DIR/bin/zsh" "$@"
