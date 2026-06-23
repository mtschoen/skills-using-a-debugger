#!/usr/bin/env python3
"""Detect-then-install the debuggers this skill drives (netcoredbg/gdb/lldb/cdb).

Idempotent and platform-gated: it installs only the debuggers relevant to the
current OS and skips any already on PATH (or otherwise discoverable). See
references/tooling-setup.md for the per-platform detail.

    python scripts/setup-debuggers.py            # ensure all relevant debuggers
    python scripts/setup-debuggers.py --dry-run  # show what it would do
    python scripts/setup-debuggers.py --only netcoredbg,lldb
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "dbgsession"))

from setup import run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the debuggers used by using-a-debugger"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the install actions without running them",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated subset of {netcoredbg,gdb,lldb,cdb} to act on",
    )
    args = parser.parse_args()

    only = [kind for kind in args.only.split(",") if kind] if args.only else None
    print("Debugger setup (detect, then install what is missing):")
    results = run(only=only, dry_run=args.dry_run)

    failed = [result for result in results if result.status == "failed"]
    manual = [result for result in results if result.status == "manual"]
    if manual:
        print("\nManual follow-up needed:")
        for result in manual:
            print(f"  {result.kind}: {result.detail}")
    if failed:
        print("\nFailed:")
        for result in failed:
            print(f"  {result.kind}: {result.detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
