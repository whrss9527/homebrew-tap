cask "proxi" do
  version "0.12.0"
  sha256 "00c2c88633b0b5ae25069559cf2c3843d7047423b209c79a0de62201ef0064f8"

  url "https://github.com/whrss9527/proxi/releases/download/v#{version}/Proxi-macos.zip"
  name "Proxi"
  desc "Switch the system, Terminal, git and npm proxy settings together"
  homepage "https://whrss.com/proxi/"

  livecheck do
    url :url
    strategy :github_latest
  end

  auto_updates true
  depends_on macos: :sonoma

  app "Proxi.app"
  # A wrapper rather than a symlink: the app finds its own bundle (version,
  # resources) only when started from its real path.
  command_wrapper "proxi", executable: "#{appdir}/Proxi.app/Contents/MacOS/Proxi"

  # Versions up to 0.12 could install a privileged background helper; 0.13 and
  # later only offer to remove it. Clean it up here so upgrades from older
  # versions leave nothing behind; every path below may be absent.
  uninstall launchctl: "com.whrss9527.proxyswitch.helper",
            quit:      "com.whrss9527.proxyswitch",
            delete:    [
              "/Library/Application Support/ProxySwitch",
              "/Library/LaunchDaemons/com.whrss9527.proxyswitch.helper.plist",
              "/Library/Logs/ProxySwitch-helper.log",
              "/Library/PrivilegedHelperTools/com.whrss9527.proxyswitch.*",
              "/var/run/com.whrss9527.proxyswitch.helper.sock",
            ]

  # Profiles synced through iCloud Drive (~/Library/Mobile Documents/
  # com~apple~CloudDocs/Proxi) are intentionally left alone, and so are proxy
  # passwords in the login keychain (service com.whrss9527.proxyswitch).
  zap delete: [
        "/usr/local/bin/proxi",
        "/usr/local/bin/proxyswitch",
      ],
      trash:  [
        "~/Library/Application Support/Proxi",
        "~/Library/Application Support/ProxySwitch",
        "~/Library/Caches/com.whrss9527.proxyswitch",
        "~/Library/HTTPStorages/com.whrss9527.proxyswitch",
        "~/Library/Preferences/com.whrss9527.proxyswitch.plist",
      ]
end
