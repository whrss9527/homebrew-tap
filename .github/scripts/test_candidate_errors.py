"""Exercise the real CLI with isolated casks and mocked transport/filesystem faults."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import bump_casks as bump
from test_plan_inputs import change, text


DRIVER = r'''
import io, json, runpy, sys, tempfile, urllib.error, urllib.request
from pathlib import Path
from unittest.mock import patch
root = Path(sys.argv[1])
spec = json.loads((root / "fixtures.json").read_text())
original_read = Path.read_text
original_write = Path.write_text
original_replace = Path.replace
original_temporary = tempfile.NamedTemporaryFile
reads = 0
def read(path, *args, **kwargs):
    global reads
    if path == root / "Casks/pop.rb":
        reads += 1
        if spec["fault"] == "read" or (spec["fault"] == "read-again" and reads > 1):
            raise OSError("fixture cask read failed")
    return original_read(path, *args, **kwargs)
def replace(path, target):
    if spec["fault"] == "replace" and target == root / "Casks/pop.rb":
        raise OSError("fixture cask replace failed")
    return original_replace(path, target)
def write(path, *args, **kwargs):
    if spec["fault"] == "output" and path == root / "accepted.json":
        raise OSError("fixture common output failed")
    return original_write(path, *args, **kwargs)
class PartialWrite:
    def __init__(self, handle):
        self.handle, self.name = handle, handle.name
    def __enter__(self):
        self.handle.__enter__()
        return self
    def __exit__(self, *args):
        return self.handle.__exit__(*args)
    def write(self, value):
        self.handle.write(value[:20])
        raise OSError("fixture partial temporary write failed")
def temporary(*args, **kwargs):
    handle = original_temporary(*args, **kwargs)
    if spec["fault"] == "write-partial" and kwargs.get("prefix") == ".pop.rb.":
        return PartialWrite(handle)
    return handle
def urlopen(request, **kwargs):
    if spec["fault"] == "runtime":
        raise RuntimeError("fixture programming error")
    if spec["fault"] == "assertion":
        raise AssertionError("fixture invariant error")
    url = request.full_url
    if spec["fault"].startswith("retry-header-") and "/pop/releases/latest" in url:
        value = spec["fault"].removeprefix("retry-header-")
        headers = ({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "bad"} if value == "reset"
                   else {"Retry-After": value})
        raise urllib.error.HTTPError(url, 503, "fixture transient API error", headers, None)
    if url not in spec["responses"]:
        raise AssertionError("unexpected fixture URL " + url)
    return io.BytesIO(bytes.fromhex(spec["responses"][url]))
sys.argv = [str(root / ".github/scripts/bump_casks.py"), *sys.argv[2:]]
with patch("urllib.request.urlopen", side_effect=urlopen), patch.object(Path, "read_text", read), \
     patch.object(Path, "write_text", write), patch.object(Path, "replace", replace), \
     patch("tempfile.NamedTemporaryFile", side_effect=temporary):
    runpy.run_path(sys.argv[0], run_name="__main__")
'''


class CandidateErrorTests(unittest.TestCase):
    def run_cli(self, *, bad_payload=None, both_bad=False, fault="", applying=False,
                dry_run=False, bad_sums=False, digest="valid", current=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root / ".github/scripts"
            scripts.mkdir(parents=True)
            shutil.copyfile(bump.__file__, scripts / "bump_casks.py")
            (root / "Casks").mkdir()
            plans, responses, originals = [], {}, {}
            for token in ["pop", "stox"]:
                plan = change(token)
                archive = ("fixture release archive " + token).encode()
                plan["sha256"] = hashlib.sha256(archive).hexdigest()
                path = root / "Casks" / f"{token}.rb"
                path.write_text(text(plan))
                path.chmod(0o640)
                originals[token] = path.read_bytes()
                plans.append(plan)
                sums_url = f"https://github.com/whrss9527/{token}/releases/download/v1.1/SHA256SUMS.txt"
                asset_name = token.title() + "-1.1.zip"
                asset = {"name": asset_name, "browser_download_url": plan["url"]}
                if digest == "valid":
                    asset["digest"] = "sha256:" + plan["sha256"]
                elif digest == "null":
                    asset["digest"] = None
                release = {"tag_name": "v1.0" if current else "v1.1", "draft": False,
                           "prerelease": False, "html_url": plan["release"],
                           "assets": [asset, {"name": "SHA256SUMS.txt", "browser_download_url": sums_url}]}
                payload = (bad_payload(release) if callable(bad_payload) else bad_payload)
                api_url = f"{bump.API}/repos/whrss9527/{token}/releases/latest"
                responses[api_url] = (payload if payload is not None and (token == "pop" or both_bad)
                                      else json.dumps(release).encode()).hex()
                responses[plan["url"]] = archive.hex()
                responses[sums_url] = (b"\xff" if bad_sums and token == "pop"
                                       else (plan["sha256"] + "  " + asset_name + "\n").encode()).hex()
            (root / "fixtures.json").write_text(json.dumps({"fault": fault, "responses": responses}))
            driver = root / "driver.py"
            driver.write_text(DRIVER)
            output, summary, plan_output = [root / name for name in ["outputs", "summary.md", "accepted.json"]]
            args = ["--output", str(plan_output)]
            if applying:
                plan_input = root / "plan.json"
                plan_input.write_text(json.dumps(plans))
                args += ["--apply", str(plan_input)]
            if dry_run:
                args.append("--dry-run")
            result = subprocess.run([sys.executable, str(driver), str(root), *args],
                                    env=dict(os.environ, GITHUB_OUTPUT=str(output),
                                             GITHUB_STEP_SUMMARY=str(summary), GITHUB_ACTIONS="true",
                                             PYTHONDONTWRITEBYTECODE="1"),
                                    capture_output=True, text=True, timeout=10)
            files = {token: (root / "Casks" / f"{token}.rb").read_bytes() for token in originals}
            modes = {token: (root / "Casks" / f"{token}.rb").stat().st_mode & 0o777 for token in originals}
            return {"result": result, "plan": json.loads(plan_output.read_text()) if plan_output.exists() else None,
                    "output": output.read_text() if output.exists() else "",
                    "summary": summary.read_text() if summary.exists() else "",
                    "files": files, "originals": originals, "modes": modes,
                    "temporary": list((root / "Casks").glob(".*.rb.*"))}

    def assert_independent_success(self, evidence, *, applying=False, dry_run=False):
        result = evidence["result"]
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("pop", result.stderr)
        self.assertEqual([item["token"] for item in evidence["plan"]], ["stox"])
        self.assertIn("changed=true\ncasks=stox\n", evidence["output"])
        self.assertNotIn("up to date", evidence["summary"])
        self.assertIn("1 replay changes were held" if applying else "1 casks could not be checked or updated", evidence["summary"])
        self.assertEqual(evidence["files"]["pop"], evidence["originals"]["pop"])
        self.assertEqual(evidence["modes"], {"pop": 0o640, "stox": 0o640})
        self.assertEqual(evidence["temporary"], [])
        if dry_run:
            self.assertEqual(evidence["files"]["stox"], evidence["originals"]["stox"])
        else:
            self.assertIn(b'version "1.1"', evidence["files"]["stox"])

    def test_malformed_json_and_response_schemas_isolate_one_candidate(self):
        def mutated(field, value):
            def payload(release):
                release = copy.deepcopy(release)
                release[field] = value
                return json.dumps(release).encode()
            return payload
        cases = [b"{", b"\xff", b"[]", b"null", b"1", b'{"unused":' + b"1" * 5000 + b"}",
                 b"[" * 50000 + b"]" * 50000,
                 lambda r: json.dumps({k: v for k, v in r.items() if k != "tag_name"}).encode(),
                 lambda r: json.dumps({k: v for k, v in r.items() if k != "draft"}).encode(),
                 lambda r: json.dumps({k: v for k, v in r.items() if k != "assets"}).encode(),
                 mutated("tag_name", 1), mutated("draft", "false"), mutated("prerelease", 0),
                 mutated("tag_name", "v" + "9" * 5000),
                 mutated("tag_name", "v\ud800"), mutated("html_url", "\ud800"),
                 mutated("assets", [{"name": "\ud800", "browser_download_url": "https://github.com/asset"}]),
                 mutated("assets", [{"name": "Pop-1.1.zip", "browser_download_url": "https://github.com/asset", "digest": "\ud800"}]),
                 mutated("html_url", None), mutated("assets", None), mutated("assets", {}),
                 mutated("assets", [1]), mutated("assets", [{"name": "Pop-1.1.zip"}]),
                 mutated("assets", [{"name": "Pop-1.1.zip", "browser_download_url": 1}]),
                 mutated("assets", [{"name": "SHA256SUMS.txt", "browser_download_url": "not-a-url"}]),
                 mutated("assets", [{"name": "SHA256SUMS.txt", "browser_download_url": "https://[invalid/asset"}]),
                 mutated("assets", [{"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com:bad/asset"}]),
                 mutated("assets", [{"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/a\n"}]),
                 mutated("assets", [{"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/\ud800"}]),
                 mutated("assets", [{"name": "Pop-1.1.zip", "browser_download_url": "https://github.com/asset", "digest": 1}]),
                 mutated("assets", [{"name": "Pop-1.1.zip", "browser_download_url": "https://github.com/asset", "digest": "sha256:bad"}]),
                 lambda r: json.dumps(dict(r, assets=[r["assets"][0], r["assets"][0]])).encode()]
        for number, payload in enumerate(cases):
            with self.subTest(case=number):
                self.assert_independent_success(self.run_cli(bad_payload=payload))

    def test_dry_run_bad_json_keeps_other_candidate_and_all_files_unchanged(self):
        self.assert_independent_success(self.run_cli(bad_payload=b"{", dry_run=True), dry_run=True)

    def test_invalid_checksum_encoding_is_isolated(self):
        self.assert_independent_success(self.run_cli(bad_sums=True))

    def test_malformed_retry_headers_are_isolated_without_sleeping(self):
        for value in ["bad", "nan", "inf", "reset"]:
            with self.subTest(value=value):
                self.assert_independent_success(self.run_cli(fault="retry-header-" + value))

    def test_initial_and_second_read_failures_are_isolated(self):
        for fault in ["read", "read-again"]:
            with self.subTest(fault=fault):
                self.assert_independent_success(self.run_cli(fault=fault))

    def test_partial_write_and_replace_failures_preserve_rejected_cask(self):
        for fault in ["write-partial", "replace"]:
            with self.subTest(fault=fault):
                self.assert_independent_success(self.run_cli(fault=fault))

    def test_replay_read_and_write_failures_keep_other_verified_candidate(self):
        for fault in ["read", "write-partial", "replace"]:
            with self.subTest(fault=fault):
                self.assert_independent_success(self.run_cli(fault=fault, applying=True), applying=True)

    def test_all_failed_candidates_write_empty_plan_and_accurate_summary(self):
        evidence = self.run_cli(bad_payload=b"{", both_bad=True)
        self.assertEqual(evidence["result"].returncode, 1)
        self.assertEqual(evidence["plan"], [])
        self.assertEqual(evidence["output"], "changed=false\ncasks=\n")
        self.assertIn("2 casks could not be checked or updated", evidence["summary"])
        self.assertNotIn("up to date", evidence["summary"])
        self.assertEqual(evidence["files"], evidence["originals"])

    def test_optional_null_or_missing_digest_keeps_checksum_verification(self):
        for digest in ["null", "missing"]:
            with self.subTest(digest=digest):
                evidence = self.run_cli(digest=digest)
                self.assertEqual(evidence["result"].returncode, 0, evidence["result"].stderr)
                self.assertEqual([item["token"] for item in evidence["plan"]], ["pop", "stox"])
                self.assertIn("SHA256SUMS.txt", evidence["result"].stderr)

    def test_actual_up_to_date_result_still_reports_success(self):
        evidence = self.run_cli(current=True)
        self.assertEqual(evidence["result"].returncode, 0)
        self.assertEqual(evidence["plan"], [])
        self.assertIn("All casks are up to date", evidence["summary"])
        self.assertEqual(evidence["files"], evidence["originals"])

    def test_unexpected_programming_errors_are_not_swallowed(self):
        for fault in ["runtime", "assertion"]:
            with self.subTest(fault=fault):
                evidence = self.run_cli(fault=fault)
                self.assertNotEqual(evidence["result"].returncode, 0)
                self.assertIn("Traceback", evidence["result"].stderr)
                self.assertIsNone(evidence["plan"])
                self.assertEqual(evidence["output"], "")

    def test_common_output_error_remains_fatal(self):
        evidence = self.run_cli(fault="output")
        self.assertNotEqual(evidence["result"].returncode, 0)
        self.assertIn("fixture common output failed", evidence["result"].stderr)
        self.assertIn("Traceback", evidence["result"].stderr)
        self.assertIsNone(evidence["plan"])
        self.assertEqual(evidence["output"], "")
        self.assertEqual(evidence["summary"], "")


if __name__ == "__main__":
    unittest.main()
