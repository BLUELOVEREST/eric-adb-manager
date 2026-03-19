# eric-adb-manager

Thin CLI for managing multiple remote `adb server` endpoints from one machine.

## Install

Install from GitHub into your user directories:

```bash
curl -fsSL https://raw.githubusercontent.com/BLUELOVEREST/eric-adb-manager/main/install.sh | bash
```

Default install locations:

- binary: `~/.local/bin/eam`
- source: `~/.local/share/eam`
- config: `~/.config/eam/servers.yaml`

If your shell does not already include `~/.local/bin`, add this to `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

The installer will:

- download the requested GitHub ref into `~/.local/share/eam`
- link `eam` into `~/.local/bin`
- initialize `~/.config/eam/servers.yaml` if it does not exist
- append `eval "$(eam completion zsh)"` to `~/.zshrc`

## Quick start

Initialize the default config:

```bash
bin/eam init
```

List configured servers:

```bash
bin/eam servers list
```

List devices across all servers:

```bash
bin/eam devices
```

Run a shell command:

```bash
bin/eam shell signal/R58Mxxxx getprop ro.product.model
```

Push a file:

```bash
bin/eam push signal/R58Mxxxx ./app.apk /data/local/tmp/app.apk
```

## zsh completion

Load completion into `oh-my-zsh`:

```bash
export PATH="/absolute/path/to/eric-adb-manager/bin:$PATH"
eval "$(eam completion zsh)"
```

If you want to initialize a config somewhere else:

```bash
eam init --config ~/.config/eam/servers.yaml
```

The completion script dynamically completes:

- subcommands
- configured server names
- `server/serial` targets from remote `adb devices -l`

## Notes

- Default config search order:
  - `$EAM_CONFIG`
  - `./config/servers.yaml`
  - `~/.config/eam/servers.yaml`
- Completion calls back into `eam.py`, so remote target completion depends on the configured `adb server` being reachable.

## Uninstall

If you installed with the default layout:

```bash
~/.local/share/eam/uninstall.sh
```
