cask "stox" do
  version "1.4.4"
  sha256 "4a9fb5972cea5a9f8c7f43a1a9601c68f71ab9a46a71aff9e90b1b8ce0aefabc"

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
