# whrss9527/tap

Homebrew casks for [whrss9527](https://github.com/whrss9527)'s macOS menu bar apps. Every app is signed with a Developer ID, notarized by Apple, and installed straight from its GitHub release.

**English** · [简体中文](README.zh-CN.md)

## Install

```sh
brew install --cask whrss9527/tap/pop
brew install --cask whrss9527/tap/meno
brew install --cask whrss9527/tap/stox
brew install --cask whrss9527/tap/proxi
```

Always use the full name `whrss9527/tap/<app>`. It taps this repository and trusts that cask in one step, and it can't be confused with another package of the same name (Homebrew itself has an unrelated `pop` formula).

| App | What it does | Cask | Needs |
|---|---|---|---|
| [Pop](https://whrss.com/pop/) ([source](https://github.com/whrss9527/pop)) | Right-click ring toolbox: OCR, translation, clipboard history, plugins | `whrss9527/tap/pop` | macOS 15 |
| [Meno](https://whrss.com/meno/) ([source](https://github.com/whrss9527/meno)) | Menu bar manager: hide and stash icons, rules and scenes | `whrss9527/tap/meno` | macOS 14 |
| [Stox](https://whrss.com/stox/) ([source](https://github.com/whrss9527/stox)) | Stock quotes in the menu bar: A-shares, Hong Kong, US | `whrss9527/tap/stox` | macOS 13 |
| [Proxi](https://whrss.com/proxi/) ([source](https://github.com/whrss9527/proxi)) | Proxy switch for developers: points the system proxy, Terminal, git and npm at your own proxy server; also links the `proxi` command | `whrss9527/tap/proxi` | macOS 14 |

## Updates

The apps update themselves, so the casks are marked `auto_updates` and a plain `brew upgrade` leaves them alone. Let the app update, or have Homebrew do it:

```sh
brew upgrade --cask --greedy whrss9527/tap/pop
```

This tap follows each app's latest GitHub release within about an hour. Every bump is checked against the release's `SHA256SUMS.txt` and installed on macOS in CI before it lands.

## Uninstall

```sh
brew uninstall --cask proxi          # remove the app
brew uninstall --cask --zap proxi    # also remove its settings, caches and history
```

`--zap` removes data under `~/Library` only. Anything an app syncs through iCloud Drive (Stox watchlists, Proxi profiles) is left in place, and so are proxy passwords Proxi saved in your keychain (remove them in Keychain Access if you like).

Proxi 0.12 and earlier could install a background helper. If one is still there, uninstalling (or upgrading through Homebrew) stops and removes it, and Homebrew asks for your password to do it.

## Troubleshooting

- **`Refusing to load cask … from untrusted tap`**: install with the full name as shown above, or run `brew trust whrss9527/tap` once.
- **`It seems there is already a Binary at '/usr/local/bin/proxi'`** (Intel Macs): that's the script Proxi's *Automation → Install Command-Line Tool* button puts there. Remove it with `sudo rm /usr/local/bin/proxi` and install again. Homebrew's `proxi` does the same job.
- **Installed the app from a download before?** Run `brew install --cask --adopt whrss9527/tap/<app>` to let Homebrew take over the existing copy in `/Applications`.
- **Something else**: open an issue in the app's repository.
