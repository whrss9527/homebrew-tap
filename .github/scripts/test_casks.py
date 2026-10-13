import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from verified_plan import select_verified


MOCK = r'''#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path

tool, args = Path(sys.argv[0]).name, sys.argv[1:]
root = Path(os.environ["CASK_TEST_ROOT"])
settings = json.loads((root / "settings.json").read_text())
with (root / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([tool, *args]) + "\n")

def current():
    return (root / "current-token").read_text()

def config(token):
    return settings.get(token, {})

if tool == "brew":
    if args == ["--version"]:
        print("Homebrew test fixture")
    elif args[0] == "info":
        token = args[-1].split("/")[-1]
        print(json.dumps({"casks": [{"version": "1.0", "artifacts": [{"app": [token.title() + ".app"]}],
                                    "depends_on": {"macos": {">=": ["14"]}}}]}))
    elif args[0] == "install":
        token = args[-1].split("/")[-1]
        (root / "current-token").write_text(token)
        (root / "Applications" / (token.title() + ".app")).mkdir(parents=True)
    elif args[0] == "uninstall":
        token = args[-1].split("/")[-1]
        shutil.rmtree(root / "Applications" / (token.title() + ".app"))
    elif args[0] not in ["style", "audit"]:
        sys.exit("unexpected brew command")
elif tool == "sw_vers":
    print("26.0")
elif tool == "uname":
    print(os.environ["CASK_TEST_ARCHITECTURE"])
elif tool == "defaults":
    print("1.0" if args[-1] == "CFBundleShortVersionString" else Path(args[1]).parents[1].stem)
elif tool == "codesign":
    if "--verify" in args:
        sys.exit(config(current()).get("signature_exit", 0))
    print("Authority=Developer ID Application: Test\nTeamIdentifier=A56J9KFVGV\nflags=0x10000(runtime)", file=sys.stderr)
elif tool == "spctl":
    values = config(current())
    if args == ["--status"]:
        print(values.get("policy", "assessments enabled"))
        sys.exit(values.get("policy_exit", 0))
    print(values.get("assessment", "source=Notarized Developer ID"))
    sys.exit(values.get("assessment_exit", 0))
elif tool == "xcrun":
    assert args[:2] == ["stapler", "validate"]
    token = Path(args[-1]).stem.lower()
    count = root / (token + "-stapler-count")
    attempt = int(count.read_text()) if count.exists() else 0
    count.write_text(str(attempt + 1))
    exits = config(token).get("stapler_exits", [0])
    result = exits[min(attempt, len(exits) - 1)]
    if result:
        print("fixture stapler error " + str(result), file=sys.stderr)
    sys.exit(result)
elif tool == "pgrep":
    sys.exit(0 if (root / "Applications" / (args[-1] + ".app")).is_dir() else 1)
elif tool == "proxi":
    print("Proxi 1.0")
elif tool not in ["sleep", "open", "pkill"]:
    sys.exit("unexpected fixture tool")
'''


class CaskNotarizationTests(unittest.TestCase):
    def run_casks(self, settings=None, tokens=("pop",), architecture="arm64"):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script_dir = root / ".github" / "scripts"
            script_dir.mkdir(parents=True)
            source = Path(__file__).with_name("test-casks.sh").read_text()
            # The entry point hardcodes /Applications. Only relocate that path
            # in the disposable fixture; all validation/control flow is real.
            script = script_dir / "test-casks.sh"
            script.write_text(source.replace("/Applications", str(root / "Applications")))
            (root / "settings.json").write_text(json.dumps(settings or {}))
            (root / "calls.jsonl").touch()
            tools = root / "bin"
            tools.mkdir()
            mock = tools / "mock.py"
            mock.write_text(MOCK)
            mock.chmod(0o755)
            for tool in ["brew", "sw_vers", "uname", "defaults", "codesign", "spctl", "xcrun",
                         "pgrep", "proxi", "sleep", "open", "pkill"]:
                (tools / tool).symlink_to(mock)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                       CASK_TEST_ROOT=str(root), CASK_TEST_ARCHITECTURE=architecture)
            result = subprocess.run(["bash", str(script), *tokens], env=env,
                                    capture_output=True, text=True, timeout=15)
            calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
            return result, calls

    def test_notarized_install_on_each_architecture_succeeds(self):
        for architecture in ["arm64", "x86_64"]:
            with self.subTest(architecture=architecture):
                result, calls = self.run_casks(architecture=architecture)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(["spctl", "--status"], calls)
                verification = next(call for call in calls if call[:2] == ["codesign", "--verify"])
                self.assertIn("--all-architectures", verification)
                self.assertTrue(any(call[:2] == ["brew", "uninstall"] for call in calls))

    def test_disabled_unknown_or_unavailable_policy_fails(self):
        for values in [{"policy": "assessments disabled"}, {"policy": "unknown"}, {"policy_exit": 1}]:
            with self.subTest(values=values):
                result, _ = self.run_casks({"pop": values})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Gatekeeper", result.stdout)

    def test_overridden_unknown_and_rejected_assessments_fail(self):
        cases = [
            {"assessment": "override=security disabled\nsource=Notarized Developer ID"},
            {"assessment": "override=custom\nsource=Notarized Developer ID"},
            {"assessment": "source=Unknown"},
            {"assessment": "source=Unnotarized Developer ID", "assessment_exit": 3},
            {"assessment": "source=Notarized Developer ID", "assessment_exit": 1},
        ]
        for values in cases:
            with self.subTest(values=values):
                result, _ = self.run_casks({"pop": values})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("spctl", result.stdout)

    def test_only_network_68_retries_and_eventually_succeeds(self):
        result, calls = self.run_casks({"pop": {"stapler_exits": [68, 68, 0]}})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sum(call[:3] == ["xcrun", "stapler", "validate"] for call in calls), 3)
        self.assertEqual(calls.count(["sleep", "5"]), 2)

    def test_exhausted_network_retry_fails_and_cleans_up(self):
        result, calls = self.run_casks({"pop": {"stapler_exits": [68]}})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(call[:3] == ["xcrun", "stapler", "validate"] for call in calls), 3)
        self.assertEqual(calls.count(["sleep", "5"]), 2)
        self.assertIn("exit 68", result.stdout)
        self.assertTrue(any(call[:2] == ["brew", "uninstall"] for call in calls))

    def test_permanent_stapler_error_fails_without_retry(self):
        result, calls = self.run_casks({"pop": {"stapler_exits": [65]}})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(call[:3] == ["xcrun", "stapler", "validate"] for call in calls), 1)
        self.assertNotIn(["sleep", "5"], calls)
        self.assertIn("exit 65", result.stdout)

    def test_signature_failure_still_prevents_success(self):
        result, _ = self.run_casks({"pop": {"signature_exit": 1}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("codesign --verify failed", result.stdout)

    def test_one_failed_cask_does_not_stop_installing_and_checking_the_other(self):
        result, calls = self.run_casks({"pop": {"stapler_exits": [65]}}, tokens=("pop", "stox"))
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(call[:2] == ["brew", "install"] and call[-1].endswith("/stox") for call in calls))
        self.assertTrue(any(call[:3] == ["xcrun", "stapler", "validate"] and call[-1].endswith("Stox.app") for call in calls))
        self.assertEqual(sum(call[:2] == ["brew", "uninstall"] for call in calls), 2)

    def test_only_successful_cask_jobs_can_supply_both_required_receipts(self):
        runners = {"arm64": "macos-latest", "x86_64": "macos-15-intel"}
        plan = [{"token": token, "old": "0.9", "new": "1.0", "sha256": "a" * 64} for token in ["pop", "stox"]]
        receipts = []
        for architecture, runner in runners.items():
            for change in plan:
                values = {"pop": {"stapler_exits": [65]}} if architecture == "arm64" else {}
                result, _ = self.run_casks(values, tokens=(change["token"],), architecture=architecture)
                # Update's receipt step has the default success() condition.
                if result.returncode == 0:
                    receipts.append(dict(change, runner=runner))
        self.assertEqual(select_verified(plan, receipts, list(runners.values())), [plan[1]])


if __name__ == "__main__":
    unittest.main()
