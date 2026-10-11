#!/usr/bin/env python3
"""Select bumps verified for the exact version and digest on every runner."""

import argparse
import json
from pathlib import Path


def select_verified(plan, receipts, runners):
    if not runners:
        raise ValueError("at least one verification runner is required")
    approved = []
    for change in plan:
        passed = {
            receipt.get("runner")
            for receipt in receipts
            if all(receipt.get(key) == change[key] for key in ("token", "new", "sha256"))
        }
        if set(runners) <= passed:
            approved.append(change)
    return approved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("receipts", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("runners", nargs="+")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    receipts = [json.loads(path.read_text()) for path in args.receipts.glob("**/receipt.json")]
    approved = select_verified(plan, receipts, args.runners)
    args.output.write_text(json.dumps(approved, indent=2) + "\n")
    selected = {change["token"] for change in approved}
    for change in plan:
        status = "verified" if change["token"] in selected else "held: missing successful runner checks"
        print(f"{change['token']} {change['new']}: {status}")


if __name__ == "__main__":
    main()
