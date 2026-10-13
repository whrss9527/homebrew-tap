#!/bin/bash
# Replay verified inputs against each freshly fetched CI checkout before pushing.
set -euo pipefail

[[ "${GITHUB_ACTIONS:-}" == true ]] || { echo "This script requires a disposable Actions checkout."; exit 1; }
repository="$(git rev-parse --show-toplevel)"
cd "$repository"
branch="${CASK_DEFAULT_BRANCH:?}"
git check-ref-format --branch "$branch" >/dev/null
git diff --quiet && git diff --cached --quiet && [[ -z "$(git ls-files --others --exclude-standard)" ]] \
  || { echo "Refusing to replay changes in a dirty checkout."; exit 1; }

work="$(mktemp -d "${RUNNER_TEMP:?}/cask-plan-replay.XXXXXX")"
cp "${1:?Verified plan is required.}" "$work/verified-plan.json"
cp "$(dirname "$0")/bump_casks.py" "$work/bump_casks.py"
echo "Replay evidence: $work"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for attempt in 1 2 3; do
  git fetch origin "$branch"
  base="$(git rev-parse FETCH_HEAD)"
  git switch --detach "$base"
  approved="$work/approved-$attempt.json"
  if ! PYTHONDONTWRITEBYTECODE=1 python3 "$work/bump_casks.py" --apply "$work/verified-plan.json" \
      --casks-dir "$repository/Casks" --output "$approved"; then
    echo "rejected=true" >> "${GITHUB_OUTPUT:?}"
  fi
  jq -c '.[]' "$approved" | while read -r change; do
    token="$(jq -r .token <<<"$change")"
    if git diff --quiet -- "Casks/$token.rb"; then continue; fi
    git add "Casks/$token.rb"
    git commit --quiet \
      -m "$(jq -r '"\(.token) \(.old) -> \(.new)"' <<<"$change")" \
      -m "$(jq -r '"Release: \(.release)\nSHA-256: \(.sha256)"' <<<"$change")"
  done
  if [[ "$(git rev-parse HEAD)" == "$base" ]]; then
    echo "Nothing to push."
    exit 0
  fi
  git update-ref "refs/cask-candidates/attempt-$attempt" HEAD
  git push origin "HEAD:refs/heads/$branch" && exit 0
  if [[ "$attempt" -lt 3 ]]; then sleep $((attempt * 5)); fi
done
exit 1
