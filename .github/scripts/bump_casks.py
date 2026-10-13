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
  bump_casks.py --apply plan.json    replay changes whose verified inputs still
                                     match (no network); --output records accepted changes

Set GITHUB_TOKEN to avoid the 60 requests/hour unauthenticated API limit.
Exits non-zero if any cask could not be checked or failed verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
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
PLAN_FIELDS = ("schema", "token", "old", "old_sha256", "url_template", "new", "sha256", "url")


class BumpError(Exception):
    pass


def validate_change(change: dict) -> None:
    if not isinstance(change, dict) or type(change.get("schema")) is not int or change["schema"] != 2:
        raise BumpError("verification plan schema is unsupported; check and verify the cask again")
    if not all(isinstance(change.get(key), str) for key in PLAN_FIELDS if key != "schema"):
        raise BumpError("verification plan is missing its bound inputs")
    if not re.fullmatch(r"[a-z0-9][a-z0-9@.-]*", change["token"]):
        raise BumpError("verification plan has an invalid cask token")
    if not all(re.fullmatch(r"[0-9A-Za-z.\-+]+", change[key]) for key in ("old", "new")):
        raise BumpError("verification plan has an invalid version")
    if not all(re.fullmatch(r"[0-9a-f]{64}", change[key]) for key in ("old_sha256", "sha256")):
        raise BumpError("verification plan has an invalid digest")
    match = RELEASE_URL_RE.fullmatch(change["url_template"])
    if not match or "#{version}" not in match["tag"]:
        raise BumpError("verification plan has an invalid URL template")
    if change["url"] != change["url_template"].replace("#{version}", change["new"]):
        raise BumpError("verification plan target URL does not match its bound template and version")
    target = urllib.parse.urlsplit(change["url"])
    if (target.scheme != "https" or target.netloc != "github.com" or target.query or target.fragment
            or not RELEASE_URL_RE.fullmatch(change["url"])):
        raise BumpError("verification plan target URL is not a complete GitHub release asset URL")


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
            try:
                if error.headers.get("Retry-After"):
                    wait = float(error.headers["Retry-After"])
                elif error.headers.get("X-RateLimit-Remaining") == "0" and error.headers.get("X-RateLimit-Reset"):
                    wait = float(error.headers["X-RateLimit-Reset"]) - time.time() + 1
            except ValueError as header_error:
                raise BumpError(f"GET {url}: invalid retry/rate-limit header") from header_error
            if not math.isfinite(wait):
                raise BumpError(f"GET {url}: invalid retry/rate-limit header") from error
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
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BumpError(f"{path.name}: could not read cask: {error}") from error
    version = VERSION_RE.findall(text)
    sha = SHA256_RE.findall(text)
    url = URL_RE.findall(text)
    if len(version) != 1 or len(sha) != 1 or len(url) != 1:
        raise BumpError(f"{path.name}: expected exactly one top-level version, sha256 and url")
    return {"text": text, "version": version[0][1], "sha256": sha[0][1], "url": url[0]}


def write_cask(path: Path, text: str, version: str, sha256: str) -> None:
    text = VERSION_RE.sub(lambda m: f"{m[1]}{version}{m[3]}", text, count=1)
    text = SHA256_RE.sub(lambda m: f"{m[1]}{sha256}{m[3]}", text, count=1)
    temporary = None
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.chmod(mode)
        temporary.replace(path)
    except OSError as error:
        raise BumpError(f"{path.name}: could not write cask: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as error:
                log(f"  warning: could not remove temporary cask {temporary.name}: {error}")


def release_data(payload: bytes, token: str) -> dict:
    try:
        release = json.loads(payload)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise BumpError(f"{token}: latest release response is not valid JSON") from error
    if not isinstance(release, dict):
        raise BumpError(f"{token}: latest release response must be an object")
    if not isinstance(release.get("tag_name"), str) or not release["tag_name"]:
        raise BumpError(f"{token}: latest release has no valid tag_name")
    if not all(type(release.get(field)) is bool for field in ("draft", "prerelease")):
        raise BumpError(f"{token}: latest release has invalid draft/prerelease flags")
    if "html_url" in release and not isinstance(release["html_url"], str):
        raise BumpError(f"{token}: latest release has an invalid html_url")
    if not isinstance(release.get("assets"), list):
        raise BumpError(f"{token}: latest release assets must be an array")
    names = set()
    for asset in release["assets"]:
        if not isinstance(asset, dict) or not all(
            isinstance(asset.get(field), str) and asset[field]
            for field in ("name", "browser_download_url")
        ):
            raise BumpError(f"{token}: latest release has an invalid asset name or download URL")
        if asset["name"] in names:
            raise BumpError(f"{token}: latest release has duplicate asset names")
        names.add(asset["name"])
        asset_url = asset["browser_download_url"]
        try:
            target = urllib.parse.urlsplit(asset_url)
            _ = target.port
        except ValueError as error:
            raise BumpError(f"{token}: latest release has a malformed asset download URL") from error
        if (target.scheme != "https" or not target.hostname or not asset_url.isascii()
                or any(ord(character) <= 32 or ord(character) == 127 for character in asset_url)):
            raise BumpError(f"{token}: latest release has a malformed asset download URL")
        digest = asset.get("digest")
        if digest is not None and not isinstance(digest, str):
            raise BumpError(f"{token}: latest release has an invalid asset digest")
        if isinstance(digest, str) and digest.startswith("sha256:") and not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise BumpError(f"{token}: latest release has a malformed SHA-256 digest")
    return release


def check(token: str, path: Path) -> dict | None:
    cask = read_cask(path)
    match = RELEASE_URL_RE.match(cask["url"])
    if not match or "#{version}" not in match["tag"]:
        raise BumpError(f"{token}: url is not a versioned GitHub release asset: {cask['url']}")
    owner, repo = match["owner"], match["repo"]
    tag_prefix, _, tag_suffix = match["tag"].partition("#{version}")

    release = release_data(request(f"{API}/repos/{owner}/{repo}/releases/latest"), token)
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
        try:
            checksum_text = request(sums["browser_download_url"], accept="application/octet-stream").decode("utf-8")
        except UnicodeDecodeError as error:
            raise BumpError(f"{token}: SHA256SUMS.txt is not valid UTF-8") from error
        for line in checksum_text.splitlines():
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
        "schema": 2,
        "token": token,
        "old": current,
        "old_sha256": cask["sha256"],
        "url_template": cask["url"],
        "new": latest,
        "sha256": sha256,
        "url": url,
        "release": release.get("html_url", ""),
    }


def apply(changes: list[dict], casks: Path | None = None) -> tuple[list[dict], list[str]]:
    approved, failures = [], []
    casks = casks or CASKS
    for change in changes:
        try:
            validate_change(change)
            path = casks / f"{change['token']}.rb"
            if not path.is_file():
                raise BumpError(f"{change['token']}: cask no longer exists")
            cask = read_cask(path)
            if cask["url"] != change["url_template"]:
                raise BumpError(f"{change['token']}: URL template changed since verification")
            if cask["url"].replace("#{version}", change["new"]) != change["url"]:
                raise BumpError(f"{change['token']}: target URL changed since verification")
            if cask["version"] == change["new"] and cask["sha256"] == change["sha256"]:
                log(f"{change['token']}: already at the exact verified target")
            elif cask["version"] == change["old"] and cask["sha256"] == change["old_sha256"]:
                write_cask(path, cask["text"], change["new"], change["sha256"])
                log(f"{change['token']}: {change['old']} -> {change['new']}")
            else:
                raise BumpError(f"{change['token']}: version or digest changed since verification")
            approved.append(change)
        except BumpError as error:
            failures.append(str(error))
        except OSError as error:
            failures.append(f"{change['token']}: could not access cask: {error}")
    return approved, failures


def github_output(changes: list[dict], *, applying: bool = False, rejected: int = 0) -> None:
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
                    handle.write(f"| `{c['token']}` | {c['old']} | [{c['new']}]({c.get('release', '')}) | `{c['sha256']}` |\n")
            else:
                if applying:
                    handle.write("No verified replay changes were accepted.\n")
                elif rejected:
                    handle.write("No candidate updates were accepted.\n")
                else:
                    handle.write("All casks are up to date.\n")
            if rejected:
                handle.write(f"{rejected} replay changes were held for a new check and verification.\n" if applying
                             else f"{rejected} casks could not be checked or updated.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("casks", nargs="*", help="cask tokens (default: every cask in Casks/)")
    parser.add_argument("--dry-run", action="store_true", help="report only, do not edit casks")
    parser.add_argument("--output", type=Path, help="write the planned changes to this JSON file")
    parser.add_argument("--apply", type=Path, help="apply the changes from this JSON file and exit")
    parser.add_argument("--casks-dir", type=Path, help="cask directory when replaying a plan")
    args = parser.parse_args()
    if args.casks_dir and not args.apply:
        parser.error("--casks-dir requires --apply")

    try:
        if args.apply:
            changes, failures = apply(json.loads(args.apply.read_text()), args.casks_dir)
        else:
            tokens = args.casks or sorted(p.stem for p in CASKS.glob("*.rb"))
            changes, failures = [], []
            for token in tokens:
                path = CASKS / f"{token}.rb"
                if not re.fullmatch(r"[a-z0-9][a-z0-9@.-]*", token):
                    failures.append(f"{token}: no such cask")
                    continue
                try:
                    if not path.is_file():
                        raise BumpError(f"{token}: no such cask")
                    change = check(token, path)
                    if change:
                        if not args.dry_run:
                            cask = read_cask(path)
                            write_cask(path, cask["text"], change["new"], change["sha256"])
                        changes.append(change)
                except BumpError as error:
                    failures.append(str(error))
                except OSError as error:
                    failures.append(f"{token}: could not check or update cask: {error}")
    except BumpError as error:
        log(f"error: {error}")
        return 1

    if args.output:
        args.output.write_text(json.dumps(changes, indent=2) + "\n")
    github_output(changes, applying=bool(args.apply), rejected=len(failures))
    for failure in failures:
        log(f"error: {failure}")
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::error::{failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
