cask "pop" do
  version "0.42.1"
  sha256 "d8c55319b8fcc54e11aecbcc4288c9db20f66b9cbf89a0795e2a01e4fbd0a235"

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
