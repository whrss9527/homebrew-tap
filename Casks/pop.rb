cask "pop" do
  version "0.67.1"
  sha256 "69cbd5f22386093a0636051ff362c3c59ef639e15bcaae62e42dfa66d2f04482"

  url "https://github.com/whrss9527/pop/releases/download/v#{version}/Pop-#{version}.zip"
  name "Pop"
  desc "Right-click ring toolbox with OCR, translation and clipboard history"
  homepage "https://whrss.com/pop/"

  livecheck do
    url :url
    strategy :github_latest
  end

  auto_updates true
  depends_on macos: :sequoia

  app "Pop.app"

  uninstall quit: "io.github.whrss9527.pop"

  zap trash: [
    "~/Library/Application Support/Pop",
    "~/Library/Caches/io.github.whrss9527.pop",
    "~/Library/HTTPStorages/io.github.whrss9527.pop",
    "~/Library/Preferences/io.github.whrss9527.pop.plist",
    "~/Library/WebKit/io.github.whrss9527.pop",
  ]
end
