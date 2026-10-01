cask "proxi" do
  version "0.12.0"
  sha256 "00c2c88633b0b5ae25069559cf2c3843d7047423b209c79a0de62201ef0064f8"

  url "https://github.com/whrss9527/proxi/releases/download/v#{version}/Proxi-macos.zip",
      verified: "github.com/whrss9527/proxi/"
  name "Proxi"
  desc "Menu bar proxy switch with subscriptions, rule-based routing and LAN sharing"
  homepage "https://whrss.com/proxi/"

  livecheck do
    url :url
    strategy :github_latest
  end

  auto_updates true
  depends_on macos: :sonoma

  app "Proxi.app"
  binary "#{appdir}/Proxi.app/Contents/MacOS/Proxi", target: "proxi"

  # The privileged helper (enhanced and gateway modes) is installed on demand
  # from the app; every path below may be absent.
  uninstall launchctl: "com.whrss9527.proxyswitch.helper",
            quit:      "com.whrss9527.proxyswitch",
            delete:    [
              "/Library/Application Support/ProxySwitch",
              "/Library/Logs/ProxySwitch-helper.log",
              "/Library/PrivilegedHelperTools/com.whrss9527.proxyswitch.helper",
              "/Library/PrivilegedHelperTools/com.whrss9527.proxyswitch.mihomo",
              "/var/run/com.whrss9527.proxyswitch.helper.sock",
            ]

  # Synced config in iCloud Drive is intentionally left alone.
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
