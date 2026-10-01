cask "meno" do
  version "0.12.0"
  sha256 "b0b1a94860b32d0a583b18cacc4ebbb19b6c0cba9e292b8db4e0d3fc6924d045"

  url "https://github.com/whrss9527/meno/releases/download/v#{version}/Meno.zip",
      verified: "github.com/whrss9527/meno/"
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
