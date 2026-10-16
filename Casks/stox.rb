cask "stox" do
  version "1.6.1"
  sha256 "620c373c10410ccc6900db9a8c63318683423905c6eb004739d8ff24c7d0dde6"

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
