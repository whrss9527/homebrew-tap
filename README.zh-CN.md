# whrss9527/tap

[whrss9527](https://github.com/whrss9527) 的几款 macOS 菜单栏 App 的 Homebrew 安装源。每个 App 都用 Developer ID 签名、经过 Apple 公证，直接从 GitHub Releases 下载安装。

[English](README.md) · **简体中文**

## 安装

```sh
brew install --cask whrss9527/tap/pop
brew install --cask whrss9527/tap/meno
brew install --cask whrss9527/tap/stox
brew install --cask whrss9527/tap/proxi
```

请始终使用完整名字 `whrss9527/tap/<app>`：一条命令同时完成添加本仓库和信任这个 cask，也不会和别的同名软件混淆（Homebrew 官方就有一个不相干的 `pop` formula）。

| App | 用途 | Cask | 系统要求 |
|---|---|---|---|
| [Pop](https://whrss.com/pop/)（[源码](https://github.com/whrss9527/pop)） | 右键圆环工具箱：OCR、翻译、剪贴板历史、插件 | `whrss9527/tap/pop` | macOS 15 |
| [Meno](https://whrss.com/meno/)（[源码](https://github.com/whrss9527/meno)） | 菜单栏管理：隐藏、收纳图标，规则和场景 | `whrss9527/tap/meno` | macOS 14 |
| [Stox](https://whrss.com/stox/)（[源码](https://github.com/whrss9527/stox)） | 菜单栏看行情：A 股、港股、美股 | `whrss9527/tap/stox` | macOS 13 |
| [Proxi](https://whrss.com/proxi/)（[源码](https://github.com/whrss9527/proxi)） | 一键切换系统、终端、git、npm 代理；同时提供 `proxi` 命令 | `whrss9527/tap/proxi` | macOS 14 |

## 更新

这些 App 会自己更新，所以 cask 标了 `auto_updates`，普通的 `brew upgrade` 不会动它们。让 App 自己更新即可，或者用 Homebrew 更新：

```sh
brew upgrade --cask --greedy whrss9527/tap/pop
```

本仓库会在 App 发布新版后一小时左右跟进。每次更新都会核对发布页的 `SHA256SUMS.txt`，并先在 CI 的 macOS 上装一遍，通过后才提交。

## 卸载

```sh
brew uninstall --cask proxi          # 删除 App
brew uninstall --cask --zap proxi    # 连同设置、缓存和历史记录一起删除
```

`--zap` 只删除 `~/Library` 下的数据，通过 iCloud 云盘同步的内容（Stox 的自选股、Proxi 的配置）会保留。

Proxi 的特权助手（增强模式和网关模式要用）会在卸载时停掉并删除，Homebrew 会为此请你输入密码。

## 常见问题

- **提示 `Refusing to load cask … from untrusted tap`**：按上面的写法用完整名字安装，或者先运行一次 `brew trust whrss9527/tap`。
- **提示 `It seems there is already a Binary at '/usr/local/bin/proxi'`**（Intel 芯片的 Mac）：这是 Proxi「自动化 → 安装命令行工具」装的脚本。用 `sudo rm /usr/local/bin/proxi` 删掉后再装即可，Homebrew 提供的 `proxi` 用法完全一样。
- **`brew upgrade --greedy` 或 `brew reinstall` 之后 Proxi 的增强模式、网关模式停了**：Homebrew 替换 App 时会删除特权助手。在 Proxi 里重新打开该模式即可重装助手；也可以让 Proxi 自己更新，就不会这样。
- **以前下载安装过？** 运行 `brew install --cask --adopt whrss9527/tap/<app>`，让 Homebrew 接管 `/Applications` 里已有的那份。
- **其他问题**：请到对应 App 的仓库提 issue。
