"""`python -m tools.forbidden_terms` — the sweep, from a shell.

Prints the same report the gate asserts on, and exits non-zero on anything the
gate would fail. With `--seed` it prints the migration-ledger entries a fresh
violation would need, which is how a seeding is written rather than typed.
"""

import argparse
import sys
from pathlib import Path

from tools.forbidden_terms.plan import load_plan
from tools.forbidden_terms.sweep import (
    excused, gate_faults, run, tracked_files, unaccounted,
)
from tools.gates import load_programme
from tools.gates.errors import GatesInvalid
from tools.vocabulary import load_registry
from tools.vocabulary.errors import RegistryInvalid


def _seed_lines(result, extents):
    """Ledger entries for every site nothing owes yet, ready to paste and edit.

    The owner slice is deliberately left as a placeholder. Which slice removes a
    word is a judgement about what that slice rebuilds, and a tool that guessed
    it would be inventing the one field the ledger exists to make somebody own.
    """
    lines = []
    for (area, term), occurrence in sorted(result.by_site().items()):
        if (area, term) in extents:
            continue
        slug = f"g7-{term}-{area}".replace(".", "-").replace("_", "-")
        lines += [
            f"  - id: {slug}",
            f"    gate: G7",
            f"    site: {area}::{term}",
            f"    expected: {occurrence.concept}",
            f"    found: {occurrence.extent} files",
            f"    owner_slice: SLICE?",
            f"    reason: >-",
            f"      TODO — why this word is still here, and what removes it.",
            "",
        ]
    return lines


def _arguments(argv):
    parser = argparse.ArgumentParser(
        prog="python -m tools.forbidden_terms",
        description="Sweep the tracked tree for the registry's retired terms.")
    parser.add_argument("repo_root", nargs="?", default=".",
                        help="the git root to sweep (default: the current "
                             "directory)")
    parser.add_argument("--seed", action="store_true",
                        help="print migration-ledger entries for every site "
                             "nothing owes yet")
    return parser.parse_args(argv[1:])


def main(argv):
    arguments = _arguments(argv)
    repo_root = Path(arguments.repo_root).resolve()
    seed = arguments.seed

    try:
        registry = load_registry(repo_root / "domain-vocabulary", repo_root)
    except RegistryInvalid as invalid:
        print(f"the registry is invalid, so the sweep has no oracle:\n{invalid}",
              file=sys.stderr)
        return 1
    try:
        programme = load_programme(repo_root / "gates", repo_root)
    except GatesInvalid as invalid:
        print(f"the gate programme is invalid, so the ledger cannot be "
              f"trusted:\n{invalid}", file=sys.stderr)
        return 1

    plan, plan_faults = load_plan(repo_root, registry.surfaces,
                                  programme.slices)
    if plan_faults:
        print("the sweep's declared plan is invalid:", file=sys.stderr)
        for fault in plan_faults:
            print(f"  {fault}", file=sys.stderr)
        return 1

    tracked, problem = tracked_files(repo_root)
    result = run(repo_root, registry, plan, paths=tracked or None)
    entries = [e for e in programme.entries if e.gate == "G7"]
    extents, extent_faults = excused(entries)
    faults = (result.faults + extent_faults + gate_faults(result, extents)
              + ((problem,) if problem is not None else
                 unaccounted(tracked, result.swept, result.excluded)))

    for line in result.describe():
        print(f"  {line}")
    if seed:
        print("\n# --- entries for sites nothing owes yet ---")
        for line in _seed_lines(result, extents):
            print(line)

    if faults:
        print(f"\n{len(faults)} finding(s):", file=sys.stderr)
        for fault in sorted(faults):
            print(f"  {fault}", file=sys.stderr)
        return 1
    print("\nno retired word appears on any living surface unaccounted for.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
