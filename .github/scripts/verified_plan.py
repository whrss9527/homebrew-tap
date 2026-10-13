#!/usr/bin/env python3
"""Select plans whose complete replay inputs were verified on every runner."""

import argparse
import json
from pathlib import Path

from bump_casks import BumpError, PLAN_FIELDS, validate_change


def select_verified(plan, receipts, runners):
    if not runners:
        raise ValueError("at least one verification runner is required")
    matching_receipts = []
    for receipt in receipts:
        try:
            validate_change(receipt)
        except BumpError:
            continue
        if isinstance(receipt.get("runner"), str):
            matching_receipts.append(receipt)
    approved = []
    for change in plan:
        try:
            validate_change(change)
        except BumpError as error:
            print(f"held: {error}")
            continue
        passed = {
            receipt.get("runner")
            for receipt in matching_receipts
            if all(receipt.get(key) == change[key] for key in PLAN_FIELDS)
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
