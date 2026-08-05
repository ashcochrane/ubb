"""``python -m tools.gates`` — the manifest's verdict, and the ledger's ratchet.

Run from the git root:

    python -m tools.gates            # is every claim in the manifest true?
    python -m tools.gates ratchet    # does the ledger owe more than the base
                                     # branch's did?

Exit status 0 with a summary, or 1 with one line per reason it failed. CI runs
both — the first through `tests/contracts/`, the second as its own step, because
only the second needs git history. This exists so a human editing the manifest
or the ledger gets the same verdict without waiting for a workflow.
"""

import argparse
import sys
from pathlib import Path

from .compiler import load_programme
from .errors import GatesInvalid
from .ratchet import DEFAULT_BASE, run

DEFAULT_GATES = "gates"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tools.gates",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", default="check",
                        choices=("check", "ratchet"),
                        help="`check` verifies the manifest; `ratchet` compares "
                             "the ledger against the base branch")
    parser.add_argument("--gates", default=DEFAULT_GATES, type=Path,
                        help=f"the gates directory (default: {DEFAULT_GATES})")
    parser.add_argument("--repo-root", default=None, type=Path,
                        help="what the manifest's claims resolve against "
                             "(default: the gates directory's parent)")
    parser.add_argument("--base", default=DEFAULT_BASE,
                        help=f"ratchet only: the branch this change lands on "
                             f"(default: {DEFAULT_BASE})")
    args = parser.parse_args(argv)
    repo_root = args.repo_root if args.repo_root is not None else args.gates.parent

    try:
        programme = load_programme(args.gates, repo_root)
    except GatesInvalid as invalid:
        print(f"{args.gates} is INVALID — {len(invalid.errors)} error(s):",
              file=sys.stderr)
        for error in invalid.errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    if args.command == "ratchet":
        return _ratchet(programme, repo_root, args.base)

    installed = programme.installed_gates()
    owed = {name: row for name, row in programme.gates.items()
            if row.owner_slice is not None}
    print(f"{args.gates}: {len(programme.gates)} gates, "
          f"{len(installed)} installed and proven to run, {len(owed)} owed, "
          f"{len(programme.obligations)} deferred obligation(s).")
    for name, row in sorted(owed.items(), key=lambda item: _order(item[0])):
        print(f"  {name}: {row.status} (#{programme.slices[row.owner_slice].issue})")
    print(f"  migration ledger: {len(programme.entries)} entr(y/ies); "
          f"permanent exceptions: {len(programme.exceptions)}")
    return 0


def _ratchet(programme, repo_root, base):
    comparison = run(repo_root, programme.slices, base)
    if not comparison.ok:
        print(f"the migration ledger does not hold — "
              f"{len(comparison.faults)} problem(s):", file=sys.stderr)
        for fault in comparison.faults:
            print(f"  {fault}", file=sys.stderr)
        return 1
    print(f"the migration ledger only shrank: {len(comparison.removed)} entr"
          f"{'y' if len(comparison.removed) == 1 else 'ies'} removed, "
          f"{len(comparison.added)} added under review.")
    return 0


def _order(name):
    """`G7` sorts before `G14`, which alphabetically it does not."""
    return (name[:1], int(name[1:])) if name[1:].isdigit() else (name, 0)


if __name__ == "__main__":
    raise SystemExit(main())
