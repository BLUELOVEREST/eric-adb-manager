export ZSH="${ZSH:-$HOME/.oh-my-zsh}"
export LANG="${LANG:-en_US.UTF-8}"
export LC_CTYPE="${LC_CTYPE:-en_US.UTF-8}"
unset LC_ALL
export TERM="${TERM:-xterm-256color}"
zstyle ':omz:alpha:lib:git' async-prompt no

# Rebuild fpath explicitly from the runtime location. Relying on exported
# FPATH alone has been unreliable on some Android shells.
typeset -g _zsh_runtime_dir="${SHELL:h:h}"
fpath=(
  "$_zsh_runtime_dir/share/zsh/5.9/functions"
  "$_zsh_runtime_dir/share/zsh/site-functions"
  $fpath
)

ZSH_THEME="robbyrussell"
DISABLE_AUTO_UPDATE="true"
DISABLE_UPDATE_PROMPT="true"
ZSH_DISABLE_COMPFIX="true"
ENABLE_CORRECTION="false"
HISTFILE="$HOME/.zsh_history"
HISTSIZE=5000
SAVEHIST=5000

plugins=(
  zsh-autosuggestions
  zsh-syntax-highlighting
)

source "$ZSH/oh-my-zsh.sh"
