cask "meno" do
  version "0.13.0"
  sha256 "82f5721319fd33e6ee1a70506062831d729a3abf13aaa5a5729f413a5b000089"

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
