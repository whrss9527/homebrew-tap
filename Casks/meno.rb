cask "meno" do
  version "0.12.13"
  sha256 "20cdcc8aa34c47d0c0890d5d8b4ca0733bc05a7c2c67ebcd02995ed7c320016e"

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
