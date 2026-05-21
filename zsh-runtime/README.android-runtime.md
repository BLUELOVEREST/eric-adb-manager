# Android Zsh Runtime

This directory is a self-contained `aarch64-android` runtime for `adb shell`.

## Contents

- `bin/zsh`: Android `zsh 5.9`
- `lib/`: Android `ncursesw` and `tinfow` shared libraries
- `share/terminfo/`: terminal capability database
- `root-home/`: first-run template for `~/.zshrc` and `~/.oh-my-zsh/`
- `bin/start-zsh.sh`: startup wrapper

## Device-side install

Example layout on device:

```sh
/data/local/zhangzhicheng/
  zsh-runtime/
    bin/
    lib/
    share/
    root-home/
```

Example:

```sh
adb push android-runtime /data/local/zhangzhicheng/zsh-runtime
adb shell su -c 'chmod -R 755 /data/local/zhangzhicheng/zsh-runtime'
adb shell
su
cd /data/local/zhangzhicheng/zsh-runtime/bin
./start-zsh.sh
```

On first launch, the wrapper will populate these files under the parent directory:

```sh
/data/local/zhangzhicheng/.zshrc
/data/local/zhangzhicheng/.oh-my-zsh
```

## Optional system shortcut

To make launch easier after copying to the device:

```sh
ln -sf /data/local/zhangzhicheng/zsh-runtime/bin/start-zsh.sh /data/local/bin/zsh-start
```

Then start it from `adb shell` with:

```sh
su -c /data/local/bin/zsh-start
```

## Notes

- This runtime expects an Android `aarch64` userspace.
- The wrapper sets `LD_LIBRARY_PATH`, `TERMINFO`, `HOME`, `ZDOTDIR`, and `ZSH`.
- By default, `HOME` is the parent directory of `zsh-runtime`. Override it with `ZSH_HOME_DIR=/your/path ./start-zsh.sh` if needed.
- If `xterm-256color` renders badly in your environment, change `TERM` in `bin/start-zsh.sh` to `vt100`.
