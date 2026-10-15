cask "stox" do
  version "1.4.2"
  sha256 "a343f8abd13691cffedc1e0cf6c31c4432a4ab71e94f88f93b1f3f60a4f31298"

  url "https://github.com/whrss9527/stox/releases/download/v#{version}/Stox.zip"
  name "Stox"
  desc "Menu bar stock quotes for China A-share, Hong Kong and US markets"
  homepage "https://whrss.com/stox/"

  livecheck do
    url :url
    strategy :github_latest
  end

  auto_updates true
  depends_on macos: :ventura

  app "Stox.app"

  uninstall quit: "io.github.whrss9527.stox"

  # Synced watchlists in iCloud Drive are intentionally left alone.
  zap trash: [
    "~/Library/Application Support/Stox",
    "~/Library/Caches/io.github.whrss9527.stox",
    "~/Library/HTTPStorages/io.github.whrss9527.stox",
    "~/Library/Preferences/io.github.whrss9527.stox.plist",
  ]
end
