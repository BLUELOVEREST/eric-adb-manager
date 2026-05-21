# eric-adb-manager

`eam` 是一个用于集中管理多台远程 `adb server` 和多台 Android 测试设备的命令行工具。

它适合两种场景：

- 当前机器可以直接访问远程机器暴露出来的 `adb server`
- 当前机器不能访问远程 `adb server`，但可以先 SSH 到连接设备的机器，再在那台机器上执行 `eam`

## 安装

从 GitHub 安装到用户目录：

```bash
curl -fsSL https://raw.githubusercontent.com/BLUELOVEREST/eric-adb-manager/main/install.sh | bash
```

默认安装位置：

- 命令入口：`~/.local/bin/eam`
- 程序目录：`~/.local/share/eam`
- 配置文件：`~/.config/eam/servers.yaml`

安装脚本会：

- 下载代码到 `~/.local/share/eam`
- 创建 `~/.local/bin/eam`
- 如果配置文件不存在，则初始化 `~/.config/eam/servers.yaml`
- 如果当前使用的是 zsh，会检查 `~/.local/bin` 是否已经在 `PATH` 中，并只在需要时询问是否写入 `~/.zshrc`

如果你跳过了 shell 初始化，并且 `~/.local/bin` 不在 `PATH` 中，可以手动加到 `~/.zshrc`：

```zsh
export PATH="$HOME/.local/bin:$PATH"
```

## 配置

默认配置文件是：

```text
~/.config/eam/servers.yaml
```

示例：

```yaml
servers:
  - name: signal
    host: 10.95.64.240
    port: 5037
    zsh:
      local_dir: ./zsh-runtime
      remote_dir: /data/local/tmp/eam/zsh-runtime
      work_dir: /data/local/zhangzhicheng
      home_dir: /data/local/zhangzhicheng

  - name: lab-a
    host: 10.95.64.241
    port: 5037
```

字段说明：

- `name`：服务器短名字，命令里会用到，比如 `signal`
- `host`：远程 `adb server` 的 IP 或主机名
- `port`：远程 `adb server` 端口，通常是 `5037`
- `zsh.local_dir`：本机上的 `zsh-runtime` 目录，用于安装到设备
- `zsh.remote_dir`：设备上保存 `zsh-runtime` 的目录
- `zsh.work_dir`：进入 zsh 后的当前工作目录，也就是 `pwd` 看到的位置
- `zsh.home_dir`：zsh 的 `HOME` 和 `ZDOTDIR`，`.zshrc` 和 `.oh-my-zsh` 会放在这里

zsh 配置优先级：

```text
命令行参数 > server 配置 > 环境变量 > 内置默认值
```

## 基础命令

查看配置的服务器：

```bash
eam servers list
```

刷新设备缓存：

```bash
eam refresh
eam refresh --server signal
```

查看设备：

```bash
eam devices
eam devices --server signal
```

进入原生 adb shell：

```bash
eam shell signal/SO5LZ5TGFI7LLFXO
```

执行单条 shell 命令：

```bash
eam shell signal/SO5LZ5TGFI7LLFXO getprop ro.product.model
```

推送文件：

```bash
eam push signal/SO5LZ5TGFI7LLFXO ./app.apk /data/local/tmp/app.apk
```

拉取文件：

```bash
eam pull signal/SO5LZ5TGFI7LLFXO /sdcard/Download/log.txt ./log.txt
```

## zsh-runtime

如果你的 Android 设备上需要使用打包好的 zsh + oh-my-zsh 环境，可以使用内置的 `zsh` 命令。

第一次安装 runtime：

```bash
eam zsh-install signal/SO5LZ5TGFI7LLFXO
```

进入 zsh 环境：

```bash
eam zsh signal/SO5LZ5TGFI7LLFXO
```

安装并直接进入：

```bash
eam zsh signal/SO5LZ5TGFI7LLFXO --install
```

临时覆盖工作目录或 HOME：

```bash
eam zsh signal/SO5LZ5TGFI7LLFXO --work-dir /data/local/zhangzhicheng/project
eam zsh signal/SO5LZ5TGFI7LLFXO --home-dir /data/local/zhangzhicheng
```

如果配置文件里已经写了 `zsh.work_dir` 和 `zsh.home_dir`，日常只需要：

```bash
eam zsh signal/SO5LZ5TGFI7LLFXO
```

## 不能直连 adb server 时

如果当前机器不能访问远程 `adb server`，但可以 SSH 到连接设备的服务器，推荐在那台服务器上也安装 `eam`。

远程服务器上的配置可以写成本机 adb server：

```yaml
servers:
  - name: local
    host: 127.0.0.1
    port: 5037
    zsh:
      remote_dir: /data/local/zhangzhicheng/zsh-runtime
      work_dir: /data/local/zhangzhicheng
      home_dir: /data/local/zhangzhicheng
```

SSH 到远程服务器后：

```bash
eam devices --server local
eam zsh local/SO5LZ5TGFI7LLFXO
```

也可以在本机 `~/.zshrc` 里加一个薄封装：

```zsh
ream-zsh() {
  ssh -t "$1" "eam zsh 'local/$2'"
}

ream-devices() {
  ssh -t "$1" "eam devices --server local"
}
```

用法：

```bash
ream-devices lab-server
ream-zsh lab-server SO5LZ5TGFI7LLFXO
```

这样不需要远程机器暴露 `adb server` 端口，本机只需要能 SSH 到那台机器。

## zsh 补全

安装脚本会尝试把补全写入 `~/.zshrc`。如果你需要手动加载：

```zsh
eval "$(eam completion zsh)"
```

补全支持：

- 子命令
- 配置中的服务器名
- `server/serial` 目标设备，来源于本地缓存
- `push` 的本地路径和远端路径
- `pull` 的远端路径和本地路径
- `zsh` 和 `zsh-install` 的目标设备

设备目标补全依赖缓存，刷新方式：

```bash
eam refresh
```

缓存默认位置：

```text
~/.cache/eam/targets.json
```

## 环境变量

可选环境变量：

- `EAM_CONFIG`：指定配置文件路径
- `EAM_CACHE_DIR`：指定缓存目录
- `EAM_ADB_TIMEOUT`：短 adb 操作超时，默认 5 秒
- `EAM_COMPLETION_TIMEOUT`：远端路径补全超时，默认 5 秒
- `EAM_TRANSFER_TIMEOUT`：`push`、`pull`、`zsh-install` 的传输超时，默认不超时；可以设为秒数，或设为 `none` / `0` 禁用
- `EAM_ZSH_RUNTIME`：默认本地 `zsh-runtime` 目录
- `EAM_ZSH_REMOTE_DIR`：默认设备端 `zsh-runtime` 目录
- `EAM_ZSH_WORK_DIR`：默认 zsh 工作目录
- `EAM_ZSH_HOME_DIR`：默认 zsh HOME

## 卸载

默认安装布局下：

```bash
~/.local/share/eam/uninstall.sh
```
