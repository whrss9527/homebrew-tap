#!/usr/bin/env python3
"""Bump casks in Casks/ to the latest GitHub release of their app.

For every cask whose `url` points at a GitHub release asset, this looks up the
repository's latest release (drafts and prereleases are ignored), downloads the
asset, verifies its SHA-256 against the digest GitHub reports and against the
release's SHA256SUMS.txt, and rewrites `version` and `sha256`.

  bump_casks.py                      check every cask, rewrite the outdated ones
  bump_casks.py pop meno             only these casks
  bump_casks.py --dry-run            report, change nothing
  bump_casks.py --output plan.json   also write the changes as JSON
  bump_casks.py --apply plan.json    write exactly the changes in plan.json
                                     (no network; used to replay a tested plan)

Set GITHUB_TOKEN to avoid the 60 requests/hour unauthenticated API limit.
Exits non-zero if any cask could not be checked or failed verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASKS = ROOT / "Casks"
API = "https://api.github.com"
USER_AGENT = "whrss9527-homebrew-tap-bump"

VERSION_RE = re.compile(r'^(  version ")([^"]+)(")$', re.M)
SHA256_RE = re.compile(r'^(  sha256 ")([0-9a-f]{64})(")$', re.M)
URL_RE = re.compile(r'^  url "([^"]+)"', re.M)
RELEASE_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/releases/download/(?P<tag>[^/]+)/(?P<asset>[^/]+)$"
)


class BumpError(Exception):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def request(url: str, *, accept: str = "application/vnd.github+json", attempts: int = 5) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and url.startswith(API):
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    delay = 5.0
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            retryable = error.code in (403, 429) or error.code >= 500
            if not retryable or attempt == attempts:
                raise BumpError(f"GET {url} failed: HTTP {error.code}") from error
            wait = delay
            if error.headers.get("Retry-After"):
                wait = float(error.headers["Retry-After"])
            elif error.headers.get("X-RateLimit-Remaining") == "0" and error.headers.get("X-RateLimit-Reset"):
                wait = float(error.headers["X-RateLimit-Reset"]) - time.time() + 1
            if wait > 600:
                raise BumpError(f"GET {url}: rate limited for {int(wait)}s, giving up") from error
            log(f"  HTTP {error.code} for {url}, retrying in {int(max(wait, 1))}s")
            time.sleep(max(wait, 1))
            delay *= 2
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == attempts:
                raise BumpError(f"GET {url} failed: {error}") from error
            log(f"  {error} for {url}, retrying in {int(delay)}s")
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


def sha256_of(url: str) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/octet-stream"}
    for attempt in range(1, 4):
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=300) as response:
                for chunk in iter(lambda: response.read(1 << 20), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == 3:
                raise BumpError(f"download {url} failed: {error}") from error
            log(f"  {error} downloading {url}, retrying")
            time.sleep(10 * attempt)
    raise AssertionError("unreachable")


def version_key(version: str) -> tuple:
    parts = re.split(r"[.\-+]", version)
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts)


def read_cask(path: Path) -> dict:
    text = path.read_text()
    version = VERSION_RE.findall(text)
    sha = SHA256_RE.findall(text)
    url = URL_RE.findall(text)
    if len(version) != 1 or len(sha) != 1 or len(url) != 1:
        raise BumpError(f"{path.name}: expected exactly one top-level version, sha256 and url")
    return {"text": text, "version": version[0][1], "sha256": sha[0][1], "url": url[0]}


def write_cask(path: Path, text: str, version: str, sha256: str) -> None:
    text = VERSION_RE.sub(lambda m: f"{m[1]}{version}{m[3]}", text, count=1)
    text = SHA256_RE.sub(lambda m: f"{m[1]}{sha256}{m[3]}", text, count=1)
    path.write_text(text)


def check(token: str, path: Path) -> dict | None:
    cask = read_cask(path)
    match = RELEASE_URL_RE.match(cask["url"])
    if not match or "#{version}" not in match["tag"]:
        raise BumpError(f"{token}: url is not a versioned GitHub release asset: {cask['url']}")
    owner, repo = match["owner"], match["repo"]
    tag_prefix, _, tag_suffix = match["tag"].partition("#{version}")

    release = json.loads(request(f"{API}/repos/{owner}/{repo}/releases/latest"))
    if release.get("draft") or release.get("prerelease"):
        log(f"{token}: latest release {release.get('tag_name')} is a draft or prerelease, skipping")
        return None
    tag = release["tag_name"]
    if not (tag.startswith(tag_prefix) and tag.endswith(tag_suffix)):
        raise BumpError(f"{token}: tag {tag} does not match {match['tag']}")
    latest = tag[len(tag_prefix) : len(tag) - len(tag_suffix)]
    if not re.fullmatch(r"[0-9A-Za-z.\-+]+", latest):
        raise BumpError(f"{token}: unexpected version {latest!r} from tag {tag}")

    current = cask["version"]
    if latest == current:
        log(f"{token}: {current} is up to date")
        return None
    if version_key(latest) < version_key(current):
        log(f"{token}: cask has {current}, newer than the latest release {latest}; leaving it alone")
        return None

    asset_name = match["asset"].replace("#{version}", latest)
    url = cask["url"].replace("#{version}", latest)
    assets = {a["name"]: a for a in release.get("assets", [])}
    asset = assets.get(asset_name)
    if asset is None:
        raise BumpError(f"{token}: release {tag} has no asset {asset_name}")
    if asset["browser_download_url"] != url:
        raise BumpError(f"{token}: asset URL {asset['browser_download_url']} != cask URL {url}")

    log(f"{token}: {current} -> {latest}, downloading {asset_name}")
    sha256 = sha256_of(url)

    sources = ["download"]
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:"):
        if digest.removeprefix("sha256:") != sha256:
            raise BumpError(f"{token}: SHA-256 {sha256} does not match GitHub's asset digest {digest}")
        sources.append("GitHub asset digest")
    sums = assets.get("SHA256SUMS.txt")
    if sums is not None:
        listed = {}
        for line in request(sums["browser_download_url"], accept="application/octet-stream").decode().splitlines():
            parts = line.split()
            if len(parts) == 2:
                listed[parts[1].lstrip("*")] = parts[0].lower()
        if asset_name not in listed:
            raise BumpError(f"{token}: {asset_name} is not listed in SHA256SUMS.txt")
        if listed[asset_name] != sha256:
            raise BumpError(f"{token}: SHA-256 {sha256} does not match SHA256SUMS.txt ({listed[asset_name]})")
        sources.append("SHA256SUMS.txt")
    else:
        log(f"  warning: {tag} has no SHA256SUMS.txt")
    log(f"  sha256 {sha256} (verified: {', '.join(sources)})")

    return {
        "token": token,
        "old": current,
        "new": latest,
        "sha256": sha256,
        "url": url,
        "release": release.get("html_url", ""),
    }


def apply(changes: list[dict]) -> None:
    for change in changes:
        path = CASKS / f"{change['token']}.rb"
        cask = read_cask(path)
        if cask["version"] == change["new"] and cask["sha256"] == change["sha256"]:
            log(f"{change['token']}: already at {change['new']}")
            continue
        if cask["version"] != change["old"]:
            raise BumpError(f"{change['token']}: cask is at {cask['version']}, plan expected {change['old']}")
        write_cask(path, cask["text"], change["new"], change["sha256"])
        log(f"{change['token']}: {change['old']} -> {change['new']}")


def github_output(changes: list[dict]) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as handle:
            handle.write(f"changed={'true' if changes else 'false'}\n")
            handle.write(f"casks={' '.join(c['token'] for c in changes)}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as handle:
            if changes:
                handle.write("| Cask | From | To | SHA-256 |\n|---|---|---|---|\n")
                for c in changes:
                    handle.write(f"| `{c['token']}` | {c['old']} | [{c['new']}]({c['release']}) | `{c['sha256']}` |\n")
            else:
                handle.write("All casks are up to date.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("casks", nargs="*", help="cask tokens (default: every cask in Casks/)")
    parser.add_argument("--dry-run", action="store_true", help="report only, do not edit casks")
    parser.add_argument("--output", type=Path, help="write the planned changes to this JSON file")
    parser.add_argument("--apply", type=Path, help="apply the changes from this JSON file and exit")
    args = parser.parse_args()

    try:
        if args.apply:
            apply(json.loads(args.apply.read_text()))
            return 0

        tokens = args.casks or sorted(p.stem for p in CASKS.glob("*.rb"))
        changes, failures = [], []
        for token in tokens:
            path = CASKS / f"{token}.rb"
            if not re.fullmatch(r"[a-z0-9][a-z0-9@.-]*", token) or not path.is_file():
                failures.append(f"{token}: no such cask")
                continue
            try:
                change = check(token, path)
            except BumpError as error:
                failures.append(str(error))
                continue
            if change:
                changes.append(change)
                if not args.dry_run:
                    cask = read_cask(path)
                    write_cask(path, cask["text"], change["new"], change["sha256"])
    except BumpError as error:
        log(f"error: {error}")
        return 1

    if args.output:
        args.output.write_text(json.dumps(changes, indent=2) + "\n")
    github_output(changes)
    for failure in failures:
        log(f"error: {failure}")
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::error::{failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
