cask "meno" do
  version "0.12.12"
  sha256 "9158a3007286e538c706c2732d39a1912fccadd5b01d4f3f547eb51573b6d73e"

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
