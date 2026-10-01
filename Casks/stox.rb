cask "stox" do
  version "0.48.0"
  sha256 "8bd0e81baf6b6c3225970e2e9ec4e1dbd98e01b9293f509f58ed3733d80217c2"

  url "https://github.com/whrss9527/stox/releases/download/v#{version}/Stox.zip",
      verified: "github.com/whrss9527/stox/"
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
