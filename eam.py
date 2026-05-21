#!/usr/bin/env python3

import argparse
import json
import os
import posixpath
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_CANDIDATES = [
    Path(os.environ.get("EAM_CONFIG", "")) if os.environ.get("EAM_CONFIG") else None,
    Path.cwd() / "config" / "servers.yaml",
    Path.home() / ".config" / "eam" / "servers.yaml",
]
def parse_timeout_env(name: str, default: float | None) -> float | None:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value in {"", "none", "0"}:
        return None

    return float(raw_value)


DEFAULT_ADB_TIMEOUT = parse_timeout_env("EAM_ADB_TIMEOUT", 5.0)
DEFAULT_TRANSFER_TIMEOUT = parse_timeout_env("EAM_TRANSFER_TIMEOUT", None)
DEFAULT_COMPLETION_TIMEOUT = parse_timeout_env("EAM_COMPLETION_TIMEOUT", 5.0)
DEFAULT_ZSH_REMOTE_DIR = os.environ.get("EAM_ZSH_REMOTE_DIR", "/data/local/tmp/eam/zsh-runtime")
DEFAULT_ZSH_HOME_DIR = os.environ.get("EAM_ZSH_HOME_DIR")
DEFAULT_ZSH_WORK_DIR = os.environ.get("EAM_ZSH_WORK_DIR")

DEFAULT_CONFIG_CONTENT = """servers:
  - name: signal
    host: 10.95.64.240
    port: 5037
    zsh:
      local_dir: ./zsh-runtime
      remote_dir: /data/local/tmp/eam/zsh-runtime
      work_dir: /data/local/zhangzhicheng
      home_dir: /data/local/zhangzhicheng
"""


@dataclass
class Server:
    name: str
    host: str
    port: int = 5037
    zsh_local_dir: str | None = None
    zsh_remote_dir: str | None = None
    zsh_work_dir: str | None = None
    zsh_home_dir: str | None = None


class ConfigError(Exception):
    pass


class AdbTimeoutError(RuntimeError):
    pass


def default_zsh_local_dir() -> Path:
    if os.environ.get("EAM_ZSH_RUNTIME"):
        return Path(os.environ["EAM_ZSH_RUNTIME"]).expanduser()
    cwd_runtime = Path.cwd() / "zsh-runtime"
    if cwd_runtime.exists():
        return cwd_runtime
    return Path(__file__).resolve().parent / "zsh-runtime"


def config_path(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    for candidate in DEFAULT_CONFIG_CANDIDATES:
        if candidate and candidate.exists():
            return candidate
    return Path.cwd() / "config" / "servers.yaml"


def target_config_path(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    return Path.home() / ".config" / "eam" / "servers.yaml"


def default_cache_dir() -> Path:
    if os.environ.get("EAM_CACHE_DIR"):
        return Path(os.environ["EAM_CACHE_DIR"]).expanduser()
    if os.environ.get("XDG_CACHE_HOME"):
        return Path(os.environ["XDG_CACHE_HOME"]).expanduser() / "eam"
    return Path.home() / ".cache" / "eam"


def target_cache_path() -> Path:
    return default_cache_dir() / "targets.json"


def load_target_cache() -> dict[str, list[str]]:
    cache_path = target_cache_path()
    if not cache_path.exists():
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    targets = data.get("targets")
    if not isinstance(targets, dict):
        return {}
    result: dict[str, list[str]] = {}
    for server_name, items in targets.items():
        if isinstance(server_name, str) and isinstance(items, list):
            result[server_name] = [item for item in items if isinstance(item, str)]
    return result


def save_target_cache(targets: dict[str, list[str]]) -> None:
    cache_dir = default_cache_dir()
    cache_path = target_cache_path()
    payload = {
        "updated_at": int(time.time()),
        "targets": targets,
    }
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except OSError:
        return


def refresh_target_cache(servers: list[Server], server_filter: str | None = None) -> dict[str, list[str]]:
    cached_targets = load_target_cache()
    for server in servers:
        if server_filter and server.name != server_filter:
            continue
        try:
            devices = get_server_devices(server)
        except (RuntimeError, AdbTimeoutError):
            continue
        cached_targets[server.name] = [
            f"{server.name}/{device['serial']}" for device in devices if device["state"] == "device"
        ]
    save_target_cache(cached_targets)
    return cached_targets


def parse_scalar(raw: str) -> str | int:
    value = raw.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.isdigit():
        return int(value)
    return value


def parse_config(text: str, path: Path) -> dict[str, object]:
    servers: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_nested: dict[str, object] | None = None
    in_servers = False

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped == "servers:":
            in_servers = True
            continue

        if not in_servers:
            raise ConfigError(f"unsupported config format in {path}:{lineno}")

        if stripped.startswith("- "):
            current = {}
            current_nested = None
            servers.append(current)
            stripped = stripped[2:].strip()
            if not stripped:
                continue
            if ":" not in stripped:
                raise ConfigError(f"invalid server entry in {path}:{lineno}")
            key, value = stripped.split(":", 1)
            current[key.strip()] = parse_scalar(value)
            continue

        if current is None:
            raise ConfigError(f"invalid server entry in {path}:{lineno}")
        if ":" not in stripped:
            raise ConfigError(f"invalid mapping in {path}:{lineno}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            nested: dict[str, object] = {}
            current[key] = nested
            current_nested = nested
            continue
        if indent >= 4 and current_nested is not None:
            current_nested[key] = parse_scalar(value)
            continue
        current_nested = None
        current[key] = parse_scalar(value)

    return {"servers": servers}


def load_servers(path: Path) -> list[Server]:
    if not path.exists():
        raise ConfigError(
            f"config not found: {path}\n"
            "create one from config/servers.example.yaml or pass --config"
        )

    with path.open("r", encoding="utf-8") as fh:
        data = parse_config(fh.read(), path)

    raw_servers = data.get("servers")
    if not isinstance(raw_servers, list) or not raw_servers:
        raise ConfigError(f"no servers defined in {path}")

    servers = []
    for item in raw_servers:
        if not isinstance(item, dict):
            raise ConfigError(f"invalid server entry in {path}: {item!r}")
        zsh_config = item.get("zsh", {})
        if zsh_config is None:
            zsh_config = {}
        if not isinstance(zsh_config, dict):
            raise ConfigError(f"invalid zsh config in {path}: {zsh_config!r}")
        try:
            servers.append(
                Server(
                    name=str(item["name"]),
                    host=str(item["host"]),
                    port=int(item.get("port", 5037)),
                    zsh_local_dir=str(zsh_config["local_dir"]) if "local_dir" in zsh_config else None,
                    zsh_remote_dir=str(zsh_config["remote_dir"]) if "remote_dir" in zsh_config else None,
                    zsh_work_dir=str(zsh_config["work_dir"]) if "work_dir" in zsh_config else None,
                    zsh_home_dir=str(zsh_config["home_dir"]) if "home_dir" in zsh_config else None,
                )
            )
        except KeyError as exc:
            raise ConfigError(f"missing key {exc} in {path}") from exc
    return servers


def server_map(servers: list[Server]) -> dict[str, Server]:
    return {server.name: server for server in servers}


def run_adb(
    server: Server,
    adb_args: list[str],
    serial: str | None = None,
    timeout: float | None = DEFAULT_ADB_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    cmd = ["adb", "-H", server.host, "-P", str(server.port)]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(adb_args)
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        timeout_value = timeout if timeout is not None else "unknown"
        raise AdbTimeoutError(f"adb command timed out after {timeout_value}s for {server.name}") from exc


def adb_command(server: Server, adb_args: list[str], serial: str | None = None) -> list[str]:
    cmd = ["adb", "-H", server.host, "-P", str(server.port)]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(adb_args)
    return cmd


def run_adb_interactive(server: Server, adb_args: list[str], serial: str | None = None) -> int:
    return subprocess.run(adb_command(server, adb_args, serial=serial)).returncode


def parse_devices_output(text: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices attached"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        entry = {
            "serial": parts[0],
            "state": parts[1],
            "model": "",
            "device": "",
            "transport_id": "",
        }
        for item in parts[2:]:
            if ":" not in item:
                continue
            key, value = item.split(":", 1)
            if key in entry:
                entry[key] = value
        devices.append(entry)
    return devices


def get_server_devices(server: Server) -> list[dict[str, str]]:
    result = run_adb(server, ["devices", "-l"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"adb devices failed for {server.name}")
    return parse_devices_output(result.stdout)


def parse_target(target: str, servers_by_name: dict[str, Server]) -> tuple[Server, str]:
    if "/" not in target:
        raise ConfigError("target must be in the form server/serial")
    server_name, serial = target.split("/", 1)
    if not server_name or not serial:
        raise ConfigError("target must be in the form server/serial")
    server = servers_by_name.get(server_name)
    if not server:
        raise ConfigError(f"unknown server: {server_name}")
    return server, serial


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def complete_remote_paths(target: str, current_path: str, servers_by_name: dict[str, Server]) -> list[str]:
    try:
        server, serial = parse_target(target, servers_by_name)
    except ConfigError:
        return []

    normalized = current_path or "."
    if normalized.endswith("/"):
        remote_dir = normalized.rstrip("/") or "/"
        prefix = ""
    else:
        remote_dir = posixpath.dirname(normalized)
        prefix = posixpath.basename(normalized)
        if remote_dir == "":
            remote_dir = "."

    # Detect directories explicitly on the device instead of relying on ls -F.
    shell_script = (
        f"cd {shell_quote(remote_dir)} || exit 1; "
        'for name in .* *; do '
        '[ "$name" = "." ] && continue; '
        '[ "$name" = ".." ] && continue; '
        '[ -e "$name" ] || continue; '
        'if [ -d "$name" ]; then printf "%s\n" "$name/"; '
        'else printf "%s\n" "$name"; fi; '
        'done'
    )
    try:
        result = run_adb(
            server,
            ["shell", shell_script],
            serial=serial,
            timeout=DEFAULT_COMPLETION_TIMEOUT,
        )
    except (RuntimeError, AdbTimeoutError):
        return []
    if result.returncode != 0:
        return []

    items: list[str] = []
    for line in result.stdout.splitlines():
        raw_name = line.strip()
        if not raw_name:
            continue

        is_dir = raw_name.endswith("/")
        clean_name = raw_name[:-1] if is_dir else raw_name
        if prefix and not clean_name.startswith(prefix):
            continue

        candidate = posixpath.join(remote_dir, clean_name) if remote_dir != "." else clean_name
        if is_dir:
            candidate = f"{candidate}/"
        items.append(candidate)
    return items


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, col in enumerate(row):
            widths[index] = max(widths[index], len(col))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    for row in rows:
        print("  ".join(col.ljust(widths[index]) for index, col in enumerate(row)))


def cmd_servers(args: argparse.Namespace) -> int:
    servers = load_servers(config_path(args.config))
    rows = [[server.name, server.host, str(server.port)] for server in servers]
    print_table(["NAME", "HOST", "PORT"], rows)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    path = target_config_path(args.config)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not args.force:
        raise ConfigError(f"config already exists: {path} (use --force to overwrite)")

    path.write_text(DEFAULT_CONFIG_CONTENT, encoding="utf-8")
    print(f"initialized config: {path}")
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    servers = load_servers(config_path(args.config))
    rows: list[list[str]] = []
    cached_targets = load_target_cache()

    for server in servers:
        if args.server and args.server != server.name:
            continue
        try:
            devices = get_server_devices(server)
        except (RuntimeError, AdbTimeoutError) as exc:
            rows.append([server.name, "-", "error", str(exc)])
            continue
        cached_targets[server.name] = [
            f"{server.name}/{device['serial']}" for device in devices if device["state"] == "device"
        ]
        if not devices:
            rows.append([server.name, "-", "empty", "-"])
            continue
        for device in devices:
            label = device["model"] or device["device"] or "-"
            rows.append([server.name, device["serial"], device["state"], label])

    if not rows:
        print("no matching devices")
        return 0
    save_target_cache(cached_targets)
    print_table(["SERVER", "SERIAL", "STATE", "MODEL"], rows)
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    servers = load_servers(config_path(args.config))
    cached_targets = refresh_target_cache(servers, server_filter=args.server)
    rows: list[list[str]] = []
    for server in servers:
        if args.server and server.name != args.server:
            continue
        rows.append([server.name, str(len(cached_targets.get(server.name, [])))])
    if not rows:
        print("no matching servers")
        return 0
    print_table(["SERVER", "CACHED_TARGETS"], rows)
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    servers = load_servers(config_path(args.config))
    server, serial = parse_target(args.target, server_map(servers))
    if not args.shell_command:
        cmd = adb_command(server, ["shell"], serial=serial)
        return subprocess.run(cmd).returncode
    result = run_adb(server, ["shell", *args.shell_command], serial=serial)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def cmd_push(args: argparse.Namespace) -> int:
    servers = load_servers(config_path(args.config))
    server, serial = parse_target(args.target, server_map(servers))
    result = run_adb(
        server,
        ["push", args.local_path, args.remote_path],
        serial=serial,
        timeout=DEFAULT_TRANSFER_TIMEOUT,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def cmd_pull(args: argparse.Namespace) -> int:
    servers = load_servers(config_path(args.config))
    server, serial = parse_target(args.target, server_map(servers))
    result = run_adb(
        server,
        ["pull", args.remote_path, args.local_path],
        serial=serial,
        timeout=DEFAULT_TRANSFER_TIMEOUT,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def install_zsh_runtime(server: Server, serial: str, local_dir: Path, remote_dir: str) -> int:
    local_dir = local_dir.expanduser()
    if not local_dir.is_dir():
        print(f"error: zsh runtime directory not found: {local_dir}", file=sys.stderr)
        return 2
    start_script = local_dir / "bin" / "start-zsh.sh"
    if not start_script.is_file():
        print(f"error: start script not found: {start_script}", file=sys.stderr)
        return 2

    remote_dir = remote_dir.rstrip("/")
    result = run_adb(server, ["shell", "mkdir", "-p", remote_dir], serial=serial)
    if result.returncode != 0:
        if result.stderr:
            sys.stderr.write(result.stderr)
        return result.returncode

    source = str(local_dir) + os.sep + "."
    result = run_adb(server, ["push", source, remote_dir + "/"], serial=serial, timeout=None)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0:
        return result.returncode

    result = run_adb(server, ["shell", "chmod", "-R", "755", posixpath.join(remote_dir, "bin")], serial=serial)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def start_zsh_runtime(
    server: Server,
    serial: str,
    remote_dir: str,
    work_dir: str | None = None,
    home_dir: str | None = None,
) -> int:
    remote_dir = remote_dir.rstrip("/")
    start_script = posixpath.join(remote_dir, "bin", "start-zsh.sh")
    check = run_adb(
        server,
        ["shell", "test", "-f", start_script],
        serial=serial,
    )
    if check.returncode != 0:
        print(
            f"error: zsh runtime is not installed at {remote_dir}; run `eam zsh-install` first",
            file=sys.stderr,
        )
        return check.returncode

    work_dir = (work_dir or remote_dir).rstrip("/") or "/"
    env_prefix = f"ZSH_HOME_DIR={shlex.quote(home_dir)} " if home_dir else ""
    shell_command = (
        f"mkdir -p {shlex.quote(work_dir)}"
        f"{f' {shlex.quote(home_dir)}' if home_dir else ''}"
        f" && cd {shlex.quote(work_dir)}"
        f" && exec {env_prefix}{shlex.quote(start_script)}"
    )
    return run_adb_interactive(server, ["shell", shell_command], serial=serial)


def cmd_zsh_install(args: argparse.Namespace) -> int:
    servers = load_servers(config_path(args.config))
    server, serial = parse_target(args.target, server_map(servers))
    local_dir = args.local_dir or server.zsh_local_dir or str(default_zsh_local_dir())
    remote_dir = args.remote_dir or server.zsh_remote_dir or DEFAULT_ZSH_REMOTE_DIR
    return install_zsh_runtime(server, serial, Path(local_dir), remote_dir)


def cmd_zsh(args: argparse.Namespace) -> int:
    servers = load_servers(config_path(args.config))
    server, serial = parse_target(args.target, server_map(servers))
    local_dir = args.local_dir or server.zsh_local_dir or str(default_zsh_local_dir())
    remote_dir = args.remote_dir or server.zsh_remote_dir or DEFAULT_ZSH_REMOTE_DIR
    work_dir = args.work_dir or server.zsh_work_dir or DEFAULT_ZSH_WORK_DIR
    home_dir = args.home_dir or server.zsh_home_dir or DEFAULT_ZSH_HOME_DIR
    if args.install:
        result = install_zsh_runtime(server, serial, Path(local_dir), remote_dir)
        if result != 0:
            return result
    return start_zsh_runtime(server, serial, remote_dir, work_dir=work_dir, home_dir=home_dir)


def complete_servers(path: Path) -> list[str]:
    try:
        return [server.name for server in load_servers(path)]
    except Exception:
        return []


def complete_targets(path: Path) -> list[str]:
    try:
        servers = load_servers(path)
    except Exception:
        return []
    cached_targets = load_target_cache()
    items: list[str] = []
    for server in servers:
        items.extend(cached_targets.get(server.name, []))
    return items


def cmd_internal_complete(args: argparse.Namespace) -> int:
    cfg = config_path(args.config)
    words = args.words
    if not words:
        for item in ["init", "refresh", "servers", "devices", "shell", "push", "pull", "zsh", "zsh-install", "completion"]:
            print(item)
        return 0

    current = words[-1]
    previous = words[-2] if len(words) >= 2 else ""
    command = words[0]

    if len(words) == 1:
        for item in ["init", "refresh", "servers", "devices", "shell", "push", "pull", "zsh", "zsh-install", "completion"]:
            if item.startswith(current):
                print(item)
        return 0

    if command == "init":
        for item in ["--force", "--config"]:
            if item.startswith(current):
                print(item)
        return 0

    if command == "servers":
        for item in ["list"]:
            if item.startswith(current):
                print(item)
        return 0

    if command == "devices":
        if previous == "--server" or (len(words) == 2 and not current.startswith("-")):
            for item in complete_servers(cfg):
                if item.startswith(current):
                    print(item)
            return 0
        for item in ["--server"]:
            if item.startswith(current):
                print(item)
        return 0

    if command == "refresh":
        if previous == "--server" or (len(words) == 2 and not current.startswith("-")):
            for item in complete_servers(cfg):
                if item.startswith(current):
                    print(item)
            return 0
        for item in ["--server"]:
            if item.startswith(current):
                print(item)
        return 0

    if command == "shell":
        if len(words) == 2:
            for item in complete_targets(cfg):
                if item.startswith(current):
                    print(item)
            return 0
        return 0

    if command == "push":
        if len(words) == 2:
            for item in complete_targets(cfg):
                if item.startswith(current):
                    print(item)
            return 0
        if len(words) == 4:
            servers = load_servers(cfg)
            for item in complete_remote_paths(words[1], current, server_map(servers)):
                if item.startswith(current):
                    print(item)
            return 0
        return 0

    if command == "pull":
        if len(words) == 2:
            for item in complete_targets(cfg):
                if item.startswith(current):
                    print(item)
            return 0
        if len(words) == 3:
            servers = load_servers(cfg)
            for item in complete_remote_paths(words[1], current, server_map(servers)):
                if item.startswith(current):
                    print(item)
            return 0
        return 0

    if command in {"zsh", "zsh-install"}:
        if len(words) == 2:
            for item in complete_targets(cfg):
                if item.startswith(current):
                    print(item)
            return 0
        if previous == "--local-dir":
            return 0
        options = ["--local-dir", "--remote-dir"]
        if command == "zsh":
            options = ["--install", "--home-dir", "--work-dir", *options]
        for item in options:
            if item.startswith(current):
                print(item)
        return 0

    if command == "completion":
        for item in ["zsh"]:
            if item.startswith(current):
                print(item)
        return 0

    return 0


def cmd_completion_zsh(_: argparse.Namespace) -> int:
    script = r"""#compdef eam.py eam

_eam_complete() {
  local -a completions
  local -a dirs
  local -a dir_displays
  local -a files
  local -a file_displays
  local -a args
  local word
  local command
  local item
  local ret=1
  local display

  args=("${words[@]:1}")
  word="${args[-1]}"
  command="${words[2]:-}"

  if [[ "$command" == "push" ]]; then
    if (( CURRENT == 4 )); then
      _files
      return
    fi
  fi

  if [[ "$command" == "pull" ]]; then
    if (( CURRENT == 5 )); then
      _files
      return
    fi
  fi

  if [[ "$command" == "zsh" || "$command" == "zsh-install" ]]; then
    if [[ "${words[CURRENT-1]}" == "--local-dir" ]]; then
      _files -/
      return
    fi
  fi

  completions=("${(@f)$($words[1] __complete -- "${args[@]}" 2>/dev/null)}")
  dirs=()
  dir_displays=()
  files=()
  file_displays=()

  for item in "${completions[@]}"; do
    [[ -z "$item" ]] && continue
    if [[ "$item" == */ ]]; then
      dirs+=("$item")
      display="${${item%/}:t}/"
      dir_displays+=("$display")
    else
      files+=("$item")
      display="${item:t}"
      file_displays+=("$display")
    fi
  done

  if (( ${#dirs[@]} )); then
    compadd -Q -S '' -d dir_displays -- "${dirs[@]}" && ret=0
  fi
  if (( ${#files[@]} )); then
    compadd -Q -d file_displays -- "${files[@]}" && ret=0
  fi

  return ret
}

compdef _eam_complete eam.py
compdef _eam_complete eam
"""
    print(script)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eam", description="Remote adb server manager")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a config file")
    init_parser.add_argument("--config", help="Config path to create")
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing config file")
    init_parser.set_defaults(func=cmd_init)

    servers_parser = subparsers.add_parser("servers", help="List configured adb servers")
    servers_parser.add_argument("action", choices=["list"])
    servers_parser.add_argument("--config")
    servers_parser.set_defaults(func=cmd_servers)

    devices_parser = subparsers.add_parser("devices", help="List devices across servers")
    devices_parser.add_argument("--server", help="Filter by server name")
    devices_parser.add_argument("--config")
    devices_parser.set_defaults(func=cmd_devices)

    refresh_parser = subparsers.add_parser("refresh", help="Refresh cached device targets")
    refresh_parser.add_argument("--server", help="Filter by server name")
    refresh_parser.add_argument("--config")
    refresh_parser.set_defaults(func=cmd_refresh)

    shell_parser = subparsers.add_parser("shell", help="Run adb shell on a target")
    shell_parser.add_argument("target", help="Target in the form server/serial")
    shell_parser.add_argument("shell_command", nargs=argparse.REMAINDER)
    shell_parser.add_argument("--config")
    shell_parser.set_defaults(func=cmd_shell)

    push_parser = subparsers.add_parser("push", help="Push a file to a target")
    push_parser.add_argument("target", help="Target in the form server/serial")
    push_parser.add_argument("local_path")
    push_parser.add_argument("remote_path")
    push_parser.add_argument("--config")
    push_parser.set_defaults(func=cmd_push)

    pull_parser = subparsers.add_parser("pull", help="Pull a file from a target")
    pull_parser.add_argument("target", help="Target in the form server/serial")
    pull_parser.add_argument("remote_path")
    pull_parser.add_argument("local_path")
    pull_parser.add_argument("--config")
    pull_parser.set_defaults(func=cmd_pull)

    zsh_parser = subparsers.add_parser("zsh", help="Start zsh-runtime on a target")
    zsh_parser.add_argument("target", help="Target in the form server/serial")
    zsh_parser.add_argument("--install", action="store_true", help="Install zsh-runtime before starting it")
    zsh_parser.add_argument("--local-dir", help="Local zsh-runtime directory")
    zsh_parser.add_argument("--remote-dir", help="Remote zsh-runtime directory")
    zsh_parser.add_argument("--work-dir", help="Remote working directory after zsh starts")
    zsh_parser.add_argument("--home-dir", help="Remote HOME directory for zsh")
    zsh_parser.add_argument("--config")
    zsh_parser.set_defaults(func=cmd_zsh)

    zsh_install_parser = subparsers.add_parser("zsh-install", help="Install zsh-runtime on a target")
    zsh_install_parser.add_argument("target", help="Target in the form server/serial")
    zsh_install_parser.add_argument("--local-dir", help="Local zsh-runtime directory")
    zsh_install_parser.add_argument("--remote-dir", help="Remote zsh-runtime directory")
    zsh_install_parser.add_argument("--config")
    zsh_install_parser.set_defaults(func=cmd_zsh_install)

    completion_parser = subparsers.add_parser("completion", help="Generate shell completion")
    completion_parser.add_argument("shell_name", choices=["zsh"])
    completion_parser.add_argument("--config")
    completion_parser.set_defaults(func=cmd_completion_zsh)

    internal_complete = subparsers.add_parser("__complete")
    internal_complete.add_argument("--config")
    internal_complete.add_argument("separator", nargs="?")
    internal_complete.add_argument("words", nargs=argparse.REMAINDER)
    internal_complete.set_defaults(func=cmd_internal_complete)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "subcommand", None) == "__complete" and args.separator == "--":
        pass
    elif getattr(args, "subcommand", None) == "__complete" and args.separator is not None:
        args.words.insert(0, args.separator)

    if args.subcommand == "servers" and args.action != "list":
        raise SystemExit("unsupported servers action")
    if args.subcommand == "completion" and args.shell_name != "zsh":
        raise SystemExit("unsupported completion shell")

    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except AdbTimeoutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
