"""``python -m tools.sdk_operations`` — the SDK's agreement with the contract.

Run from the git root:

    python -m tools.sdk_operations           # do all the calls resolve, and is
                                             # the coverage manifest current?
    python -m tools.sdk_operations --write   # regenerate the manifest
    python -m tools.sdk_operations ratchet   # did the unwrapped count rise?

Exit status 0 with a summary, or 1 with one line per reason it failed. CI runs
the first two through `tests/contracts/` and a worktree-diff step, and the third
as its own step, because only the third needs git history. This exists so a
human editing the SDK gets the same verdict without waiting for a workflow.
"""

import argparse
import sys
from pathlib import Path

from .coverage import assess
from .manifest import MANIFEST_PATH, compare, write
from .ratchet import DEFAULT_BASE, run


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tools.sdk_operations",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", default="check",
                        choices=("check", "ratchet"),
                        help="`check` resolves every call and compares the "
                             "manifest; `ratchet` compares the unwrapped count "
                             "against the base branch")
    parser.add_argument("--repo-root", default=Path("."), type=Path,
                        help="the git root (default: the current directory)")
    parser.add_argument("--write", action="store_true",
                        help="regenerate the coverage manifest rather than "
                             "only reporting that it is stale")
    parser.add_argument("--base", default=DEFAULT_BASE,
                        help=f"ratchet only: the branch this change lands on "
                             f"(default: {DEFAULT_BASE})")
    args = parser.parse_args(argv)

    if args.command == "ratchet":
        return _ratchet(args.repo_root, args.base)
    return _check(args.repo_root, args.write)


def _check(repo_root, rewrite):
    coverage, errors = assess(repo_root)
    if errors:
        print(f"the SDK does not agree with the contract — "
              f"{len(errors)} problem(s):", file=sys.stderr)
        for error in sorted(errors):
            print(f"  {error}", file=sys.stderr)
        return 1

    if rewrite:
        rewritten = write(coverage, repo_root)
        print(f"{MANIFEST_PATH}: "
              f"{'rewritten' if rewritten else 'already current'}.")
    else:
        stale, _ = compare(coverage, repo_root)
        if stale is not None:
            print(f"the coverage manifest is stale:\n  {stale}", file=sys.stderr)
            return 1

    counts = coverage.counts()
    print(f"{len(coverage.rows)} published operations: "
          + ", ".join(f"{count} {name}" for name, count in counts.items())
          + f" ({coverage.unwrapped} unwrapped).")
    if coverage.excused:
        print(f"  {len(coverage.excused)} invalid call(s) excused by the "
              f"migration ledger:")
        for site, route in coverage.excused:
            print(f"    {site} -> {route}")
    return 0


def _ratchet(repo_root, base):
    comparison = run(repo_root, base)
    if not comparison.ok:
        print(f"the coverage ratchet does not hold — "
              f"{len(comparison.faults)} problem(s):", file=sys.stderr)
        for fault in comparison.faults:
            print(f"  {fault}", file=sys.stderr)
        return 1
    if comparison.rise:
        print(f"the unwrapped count rose from {comparison.was} to "
              f"{comparison.now}, under an authorisation licensing "
              f"{comparison.licensed}.")
    else:
        print(f"the unwrapped count did not rise: {comparison.was} -> "
              f"{comparison.now}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
