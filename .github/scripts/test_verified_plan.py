import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from verified_plan import select_verified


class VerifiedPlanTests(unittest.TestCase):
    runners = ["macos-latest", "macos-15-intel"]

    def change(self, token="pop"):
        return {"token": token, "old": "1.0", "new": "1.1", "sha256": "a" * 64}

    def receipts(self, change):
        return [dict(change, runner=runner) for runner in self.runners]

    def test_failure_of_one_cask_does_not_hold_back_other_casks(self):
        pop, proxi = self.change(), self.change("proxi")
        receipts = self.receipts(pop) + self.receipts(proxi)[:1]
        self.assertEqual(select_verified([pop, proxi], receipts, self.runners), [pop])

    def test_no_receipts_never_approves_a_change(self):
        self.assertEqual(select_verified([self.change()], [], self.runners), [])

    def test_exact_version_and_digest_must_pass_on_both_runners(self):
        change = self.change()
        for field, value in [("new", "1.2"), ("sha256", "b" * 64), ("token", "proxi")]:
            with self.subTest(field=field):
                receipts = self.receipts(change)
                receipts[1][field] = value
                self.assertEqual(select_verified([change], receipts, self.runners), [])

    def test_duplicate_or_unknown_runner_does_not_replace_missing_runner(self):
        change = self.change()
        receipts = self.receipts(change)[:1] * 2 + [dict(change, runner="unrelated")]
        self.assertEqual(select_verified([change], receipts, self.runners), [])

    def test_all_successful_changes_keep_the_original_plan(self):
        plan = [self.change(), self.change("stox")]
        receipts = [receipt for change in plan for receipt in self.receipts(change)]
        self.assertEqual(select_verified(plan, receipts, self.runners), plan)

    def test_empty_runner_list_is_rejected(self):
        with self.assertRaises(ValueError):
            select_verified([self.change()], [], [])

    def test_cli_reads_nested_artifacts_and_writes_only_verified_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            change = self.change()
            plan = root / "plan.json"
            plan.write_text(json.dumps([change, self.change("proxi")]))
            receipts = root / "receipts"
            for receipt in self.receipts(change):
                path = receipts / ("verified-pop-" + receipt["runner"]) / "receipt.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(receipt))
            output = root / "approved.json"
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("verified_plan.py")),
                 str(plan), str(receipts), str(output), *self.runners],
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(json.loads(output.read_text()), [change])
            self.assertIn("proxi 1.1: held", result.stdout)


if __name__ == "__main__":
    unittest.main()
