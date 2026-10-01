#!/bin/bash
# Audit, install, check and uninstall casks from this tap on a macOS runner.
#
#   .github/scripts/test-casks.sh              every cask in Casks/
#   .github/scripts/test-casks.sh pop proxi    only these
#
# Expects the tap to be set up as whrss9527/tap (Homebrew/actions/setup-homebrew
# links the checkout into Homebrew's Taps directory, so uncommitted changes are
# tested). Installs into /Applications and needs passwordless sudo, so run it on
# a disposable CI machine, not on your own Mac.
set -euo pipefail

TAP="whrss9527/tap"
cd "$(dirname "$0")/../.."

if [[ $# -gt 0 ]]; then
  tokens=("$@")
else
  tokens=()
  for file in Casks/*.rb; do
    tokens+=("$(basename "$file" .rb)")
  done
fi

macos_version="$(sw_vers -productVersion)"
echo "macOS ${macos_version} ($(uname -m)), $(brew --version | head -1)"

failures=()
fail() {
  echo "::error title=${token}::$*"
  failures+=("${token}: $*")
}

# Is `required` (e.g. "15", "14.0") <= the running macOS version?
macos_at_least() {
  [[ "$(printf '%s\n%s\n' "$1" "$macos_version" | sort -V | head -1)" == "$1" ]]
}

wait_for_process() { # name, seconds, want (running|gone)
  local i
  for ((i = 0; i < $2 * 2; i++)); do
    if pgrep -x "$1" >/dev/null; then
      [[ "$3" == running ]] && return 0
    else
      [[ "$3" == gone ]] && return 0
    fi
    sleep 0.5
  done
  return 1
}

echo "::group::brew style ${TAP}"
brew style "$TAP" || { token=style; fail "brew style failed"; }
echo "::endgroup::"

for token in "${tokens[@]}"; do
  cask="${TAP}/${token}"
  info="$(brew info --cask --json=v2 "$cask")"
  version="$(jq -r '.casks[0].version' <<<"$info")"
  app="$(jq -r '[.casks[0].artifacts[] | select(.app) | .app[0]][0] // empty' <<<"$info")"
  min_macos="$(jq -r '.casks[0].depends_on.macos[">="][0] // empty' <<<"$info")"
  binaries="$(jq -r '.casks[0].artifacts[]
    | (.binary // empty | (.[1].target // (.[0] | split("/") | last))),
      (.command_wrapper // empty | .[0])' <<<"$info")"

  echo "::group::${token} ${version}: audit"
  # --strict --online: every check that applies to a third-party tap, except
  #   token_conflicts   homebrew/core's unrelated `pop` formula; casks in a tap
  #                     are installed by their full name, so there is no clash
  #   livecheck_version a release newer than the cask is expected for up to an
  #                     hour; the Update workflow bumps it and the Lint job warns
  # --new is left out: it adds homebrew-cask admission checks (repository
  # notability and age). Signing and notarization are checked below.
  brew audit --cask --strict --online --except=token_conflicts,livecheck_version "$cask" \
    || fail "brew audit failed"
  echo "::endgroup::"

  if [[ -n "$min_macos" ]] && ! macos_at_least "$min_macos"; then
    echo "::notice title=${token}::needs macOS ${min_macos}, this runner has ${macos_version}; install not tested here"
    if brew install --cask "$cask" >/dev/null 2>&1; then
      fail "installed on macOS ${macos_version} despite depends_on macos >= ${min_macos}"
      brew uninstall --cask --zap "$cask" || true
    fi
    continue
  fi

  echo "::group::${token} ${version}: install"
  if ! brew install --cask "$cask"; then
    fail "brew install failed"
    echo "::endgroup::"
    continue
  fi
  echo "::endgroup::"

  echo "::group::${token} ${version}: check ${app}"
  path="/Applications/${app}"
  if [[ ! -d "$path" ]]; then
    fail "${path} is missing after install"
  else
    installed="$(defaults read "${path}/Contents/Info" CFBundleShortVersionString)"
    [[ "$installed" == "$version" ]] || fail "${app} reports version ${installed}, cask says ${version}"
    codesign --verify --deep --strict --verbose=2 "$path" || fail "codesign --verify failed"
    signature="$(codesign -dvvv "$path" 2>&1)"
    grep -q '^Authority=Developer ID Application:' <<<"$signature" || fail "not signed with a Developer ID certificate"
    grep -Eq 'flags=0x[0-9a-f]+\([^)]*runtime' <<<"$signature" || fail "hardened runtime is off"
    grep -E '^(Authority=Developer ID Application|TeamIdentifier|Timestamp)' <<<"$signature" || true
    # Gatekeeper, as on a user's Mac: brew quarantines the download, and
    # spctl must accept it as notarized Developer ID software.
    assessment="$(spctl --assess --type execute --verbose=4 "$path" 2>&1)" || fail "spctl rejected ${app}: ${assessment}"
    echo "$assessment"
    if grep -q 'override=security disabled' <<<"$assessment"; then
      echo "::warning title=${token}::Gatekeeper is disabled on this runner; spctl could not confirm notarization"
    elif ! grep -q 'source=Notarized Developer ID' <<<"$assessment"; then
      fail "spctl did not report 'Notarized Developer ID': ${assessment}"
    fi
    xcrun stapler validate "$path" || echo "(no stapled ticket; Gatekeeper checks notarization online)"
  fi
  for binary in $binaries; do
    if ! command -v "$binary" >/dev/null; then
      fail "binary ${binary} is not on PATH"
      continue
    fi
    echo "$binary -> $(readlink "$(command -v "$binary")")"
  done
  echo "::endgroup::"

  # Per-cask smoke tests for bundled command line tools.
  case "$token" in
    proxi)
      echo "::group::${token}: proxi CLI"
      output="$(proxi version 2>&1)" || fail "proxi version exited with $?: ${output}"
      echo "$output"
      [[ "$output" == "Proxi ${version}" ]] || fail "proxi version printed '${output}', expected 'Proxi ${version}'"
      echo "::endgroup::"
      ;;
  esac

  if [[ -d "$path" ]]; then
    echo "::group::${token}: launch"
    executable="$(defaults read "${path}/Contents/Info" CFBundleExecutable)"
    # In the background: `open` can wait for the app to finish launching, and an
    # app showing its first-run window never reports that on a headless runner.
    open -g "$path" &
    open_pid=$!
    if wait_for_process "$executable" 20 running; then
      sleep 3
      pgrep -x "$executable" >/dev/null || fail "${app} quit on its own right after launch"
    else
      fail "${app} did not start"
    fi
    kill "$open_pid" 2>/dev/null || true
    echo "::endgroup::"
  fi

  echo "::group::${token}: uninstall --zap"
  brew uninstall --cask --zap "$cask" || fail "brew uninstall --zap failed"
  [[ ! -e "/Applications/${app}" ]] || fail "/Applications/${app} is still there after uninstall"
  for binary in $binaries; do
    [[ ! -e "$(brew --prefix)/bin/${binary}" ]] || fail "$(brew --prefix)/bin/${binary} is still there after uninstall"
  done
  if [[ -n "${executable:-}" ]] && ! wait_for_process "$executable" 5 gone; then
    # Homebrew quits apps through Apple Events, which macOS only allows after the
    # user grants Automation access; a CI runner can't, so this is not an error.
    echo "::warning title=${token}::${executable} kept running: CI has no Automation access for brew's quit"
    pkill -x "$executable" || true
  fi
  unset executable
  echo "::endgroup::"
done

if [[ ${#failures[@]} -gt 0 ]]; then
  printf '\nFailed:\n' >&2
  printf '  %s\n' "${failures[@]}" >&2
  exit 1
fi
echo "All casks passed: ${tokens[*]}"
