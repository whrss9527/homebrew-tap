cask "pop" do
  version "0.68.0"
  sha256 "100f273897886fe9022e0a7d66b7f1b18f0a0cc1ecba77cc3b241a34d5dd3a64"

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
