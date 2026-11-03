cask "meno" do
  version "0.14.0"
  sha256 "0723abd80e905d342c5da8e082b24fd63048bf46dbeb10d4e36fb250a8d1d837"

  url "https://github.com/whrss9527/meno/releases/download/v#{version}/Meno.zip"
  name "Meno"
  desc "Menu bar manager to hide and stash icons with rules and scenes"
  homepage "https://whrss.com/meno/"

  livecheck do
    url :url
    strategy :github_latest
  end

  auto_updates true
  depends_on macos: :sonoma

  app "Meno.app"

  uninstall quit: "io.github.whrss9527.meno"

  zap trash: [
    "~/Library/Application Support/Meno",
    "~/Library/Caches/io.github.whrss9527.meno",
    "~/Library/HTTPStorages/io.github.whrss9527.meno",
    "~/Library/Preferences/io.github.whrss9527.meno.plist",
  ]
end
