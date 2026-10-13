import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import bump_casks as bump


def change(token="pop"):
    template = f"https://github.com/whrss9527/{token}/releases/download/v#{{version}}/{token.title()}-#{{version}}.zip"
    return {"schema": 2, "token": token, "old": "1.0", "old_sha256": "a" * 64,
            "url_template": template, "new": "1.1", "sha256": "b" * 64,
            "url": template.replace("#{version}", "1.1"),
            "release": f"https://github.com/whrss9527/{token}/releases/tag/v1.1"}


def text(plan, version=None, digest=None, template=None):
    return ('cask "' + plan["token"] + '" do\n  version "' + (version or plan["old"]) +
            '"\n  sha256 "' + (digest or plan["old_sha256"]) + '"\n  url "' +
            (template or plan["url_template"]) + '"\nend\n')


class PlanInputTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.casks = self.root / "Casks"
        self.casks.mkdir()
        self.plan = change()
        self.path = self.casks / "pop.rb"
        self.path.write_text(text(self.plan))

    def test_check_emits_exact_original_inputs_and_resolved_download_url(self):
        asset = {"name": "Pop-1.1.zip", "browser_download_url": self.plan["url"],
                 "digest": "sha256:" + self.plan["sha256"]}
        sums_url = "https://github.com/whrss9527/pop/releases/download/v1.1/SHA256SUMS.txt"
        release = {"tag_name": "v1.1", "draft": False, "prerelease": False,
                   "html_url": self.plan["release"],
                   "assets": [asset, {"name": "SHA256SUMS.txt", "browser_download_url": sums_url}]}
        def request(url, **_):
            return ((self.plan["sha256"] + "  Pop-1.1.zip\n").encode() if url == sums_url
                    else json.dumps(release).encode())
        with patch.object(bump, "request", side_effect=request), patch.object(bump, "sha256_of", return_value=self.plan["sha256"]):
            self.assertEqual(bump.check("pop", self.path), self.plan)

    def test_exact_original_inputs_apply_and_exact_target_is_idempotent(self):
        self.assertEqual(bump.apply([self.plan], self.casks), ([self.plan], []))
        self.assertEqual(self.path.read_text(), text(self.plan, self.plan["new"], self.plan["sha256"]))
        with patch.object(bump, "write_cask", side_effect=AssertionError("target must not be rewritten")):
            self.assertEqual(bump.apply([self.plan], self.casks), ([self.plan], []))

    def test_each_changed_original_input_is_held_without_rewriting(self):
        for field, value in [("version", "2.0"), ("digest", "c" * 64),
                             ("template", self.plan["url_template"].replace("Pop-", "Other-"))]:
            with self.subTest(field=field):
                self.path.write_text(text(self.plan, **{field: value}))
                original = self.path.read_bytes()
                approved, failures = bump.apply([self.plan], self.casks)
                self.assertEqual(approved, [])
                self.assertEqual(len(failures), 1)
                self.assertEqual(self.path.read_bytes(), original)

    def test_same_version_and_digest_with_different_url_is_not_idempotent(self):
        self.path.write_text(text(self.plan, self.plan["new"], self.plan["sha256"],
                                  self.plan["url_template"].replace("Pop-", "Other-")))
        original = self.path.read_bytes()
        self.assertEqual(bump.apply([self.plan], self.casks)[0], [])
        self.assertEqual(self.path.read_bytes(), original)

    def test_different_target_digest_at_new_version_is_not_idempotent(self):
        self.path.write_text(text(self.plan, self.plan["new"], "c" * 64))
        self.assertEqual(bump.apply([self.plan], self.casks)[0], [])

    def test_target_url_must_be_fully_resolved_and_exact(self):
        for target in [self.plan["url"] + "?download=1", self.plan["url"] + "#fragment",
                       self.plan["url"].replace("github.com", "example.invalid")]:
            with self.subTest(target=target):
                self.assertEqual(bump.apply([dict(self.plan, url=target)], self.casks)[0], [])
        for suffix in ["?download=1", "#fragment"]:
            candidate = dict(self.plan, url=self.plan["url"] + suffix,
                             url_template=self.plan["url_template"] + suffix)
            self.assertEqual(bump.apply([candidate], self.casks)[0], [])

    def test_legacy_or_incomplete_plan_is_explicitly_held(self):
        for field in bump.PLAN_FIELDS:
            with self.subTest(field=field):
                legacy = dict(self.plan)
                del legacy[field]
                approved, failures = bump.apply([legacy], self.casks)
                self.assertEqual(approved, [])
                self.assertEqual(len(failures), 1)
                self.assertEqual(self.path.read_text(), text(self.plan))

    def test_cli_outputs_only_accepted_casks_and_reports_rejection(self):
        stox = change("stox")
        (self.casks / "stox.rb").write_text(text(stox))
        self.path.write_text(text(self.plan, digest="c" * 64))
        plan = self.root / "plan.json"
        plan.write_text(json.dumps([self.plan, stox]))
        approved = self.root / "approved.json"
        result = subprocess.run(["python3", str(Path(bump.__file__)), "--apply", str(plan),
                                 "--casks-dir", str(self.casks), "--output", str(approved)],
                                capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(approved.read_text()), [stox])
        self.assertEqual(bump.read_cask(self.path)["version"], "1.0")
        self.assertEqual(bump.read_cask(self.casks / "stox.rb")["version"], "1.1")

    def test_all_held_replay_summary_does_not_claim_casks_are_up_to_date(self):
        plan = self.root / "plan.json"
        plan.write_text(json.dumps([dict(self.plan, schema=1)]))
        summary = self.root / "summary.md"
        result = subprocess.run(["python3", str(Path(bump.__file__)), "--apply", str(plan),
                                 "--casks-dir", str(self.casks)],
                                env=dict(os.environ, GITHUB_STEP_SUMMARY=str(summary)),
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("held", summary.read_text())
        self.assertNotIn("up to date", summary.read_text())


GIT_WRAPPER = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
real = os.environ["CASK_REAL_GIT"]
root = Path(os.environ["CASK_GIT_FIXTURE"])
with (root / "git-calls.jsonl").open("a") as stream:
    stream.write(json.dumps(args) + "\n")
if args and args[0] == "push" and not (root / "competed").exists():
    (root / "competed").touch()
    competitor = root / "seed"
    mode = os.environ["CASK_COMPETING_CHANGE"]
    path = competitor / "Casks/pop.rb"
    if mode != "none":
        content = path.read_text()
        if mode == "url": content = content.replace("Pop-", "Other-")
        elif mode == "sha": content = content.replace("a" * 64, "c" * 64)
        path.write_text(content)
        for command in [["add", "Casks/pop.rb"], ["commit", "-m", "concurrent cask update"], ["push", "origin", "main"]]:
            subprocess.run([real, "-C", str(competitor), *command], check=True, capture_output=True)
sys.exit(subprocess.run([real, *args]).returncode)
'''


class PushReplayTests(unittest.TestCase):
    def git(self, directory, *args):
        return subprocess.run([self.real_git, "-C", str(directory), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def run_replay(self, mode="none", dirty=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.real_git = shutil.which("git")
            remote, seed, checkout = [root / name for name in ["remote.git", "seed", "checkout"]]
            remote.mkdir()
            self.git(remote, "init", "--bare", "--initial-branch=main")
            seed.mkdir()
            self.git(seed, "init", "--initial-branch=main")
            self.git(seed, "config", "user.name", "Fixture")
            self.git(seed, "config", "user.email", "fixture@example.invalid")
            (seed / "Casks").mkdir()
            plans = [change(), change("stox")]
            for item in plans:
                (seed / "Casks" / (item["token"] + ".rb")).write_text(text(item))
            self.git(seed, "add", "Casks")
            self.git(seed, "commit", "-m", "original casks")
            self.git(seed, "remote", "add", "origin", str(remote))
            self.git(seed, "push", "origin", "main")
            self.git(root, "clone", str(remote), str(checkout))
            if dirty:
                (checkout / "Casks/pop.rb").write_text("uncommitted change")
            evidence = root / "evidence"
            evidence.mkdir()
            plan = evidence / "plan.json"
            plan.write_text(json.dumps(plans))
            output = evidence / "outputs"
            output.touch()
            (root / "git-calls.jsonl").touch()
            tools = root / "tools"
            tools.mkdir()
            wrapper = tools / "git"
            wrapper.write_text(GIT_WRAPPER)
            wrapper.chmod(0o755)
            sleep = tools / "sleep"
            sleep.write_text("#!/bin/sh\nexit 0\n")
            sleep.chmod(0o755)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                       CASK_REAL_GIT=self.real_git, CASK_GIT_FIXTURE=str(root), CASK_COMPETING_CHANGE=mode,
                       GITHUB_ACTIONS="true", CASK_DEFAULT_BRANCH="main", RUNNER_TEMP=str(evidence),
                       GITHUB_OUTPUT=str(output), PYTHONDONTWRITEBYTECODE="1")
            script = Path(__file__).with_name("commit-verified.sh")
            result = subprocess.run(["bash", str(script.resolve()), str(plan)], cwd=checkout,
                                    env=env, capture_output=True, text=True, timeout=15)
            final = {item["token"]: self.git(remote, "show", "main:Casks/" + item["token"] + ".rb") for item in plans}
            calls = [json.loads(line) for line in (root / "git-calls.jsonl").read_text().splitlines()]
            approved = [json.loads(path.read_text()) for path in sorted(evidence.glob("cask-plan-replay.*/approved-*.json"))]
            return result, final, output.read_text(), calls, approved

    def test_exact_plans_publish_normally_without_force_or_rebase(self):
        result, final, output, calls, approved = self.run_replay()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for token in ["pop", "stox"]:
            self.assertIn('version "1.1"', final[token])
        self.assertEqual(output.count("rejected=true"), 0)
        self.assertEqual(len(approved), 1)
        self.assertFalse(any("--force" in call or "--force-with-lease" in call or "--rebase" in call for call in calls))

    def test_concurrent_url_or_digest_change_is_held_and_other_cask_still_pushes(self):
        for mode in ["url", "sha"]:
            with self.subTest(mode=mode):
                result, final, output, calls, approved = self.run_replay(mode)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('version "1.0"', final["pop"])
                self.assertIn("Other-" if mode == "url" else "c" * 64, final["pop"])
                self.assertIn('version "1.1"', final["stox"])
                self.assertIn("rejected=true", output)
                self.assertEqual([item["token"] for item in approved[1]], ["stox"])
                self.assertEqual(sum(call[0] == "push" for call in calls), 2)
                self.assertFalse(any("--force" in call or "--force-with-lease" in call or "--rebase" in call for call in calls))

    def test_dirty_checkout_is_untouched_and_never_pushed(self):
        result, final, _, calls, approved = self.run_replay(dirty=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dirty checkout", result.stdout)
        self.assertFalse(any(call[0] == "push" for call in calls))
        self.assertEqual(approved, [])
        for token in ["pop", "stox"]:
            self.assertIn('version "1.0"', final[token])


if __name__ == "__main__":
    unittest.main()
