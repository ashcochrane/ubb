"""``python -m tools.consumers`` — who serves the registry's values, and who does not.

Run from the git root:

    python -m tools.consumers            # the census, by surface
    python -m tools.consumers --owed     # only what is still restated

Exit status 0 when every declared consumer holds every value by reference, 1
otherwise — and 2 when the census could not be taken at all, because "the walk
failed" and "the tree is clean" must never share an exit code.

This exists so a contributor converting a consumer gets the same verdict G2 and
G3 give, on the file they are editing, without waiting for a workflow.
"""

import argparse
import sys
from pathlib import Path

from tools.vocabulary import load_registry
from tools.vocabulary.errors import RegistryInvalid

from .census import take_census

DEFAULT_REGISTRY = "domain-vocabulary"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tools.consumers",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, type=Path,
                        help=f"the registry directory (default: "
                             f"{DEFAULT_REGISTRY})")
    parser.add_argument("--repo-root", default=None, type=Path,
                        help="what consumer paths resolve against (default: "
                             "the registry directory's parent)")
    parser.add_argument("--owed", action="store_true",
                        help="print only the consumers that still restate")
    args = parser.parse_args(argv)
    repo_root = (args.repo_root if args.repo_root is not None
                 else args.registry.parent)

    try:
        registry = load_registry(args.registry, repo_root)
    except RegistryInvalid as invalid:
        print(f"{args.registry} is INVALID, so no census can be taken:",
              file=sys.stderr)
        for error in invalid.errors:
            print(f"  {error}", file=sys.stderr)
        return 2

    census = take_census(repo_root, registry)
    if census.faults:
        print(f"the census could not be taken — {len(census.faults)} fault(s):",
              file=sys.stderr)
        for fault in census.faults:
            print(f"  {fault}", file=sys.stderr)
        return 2

    owed = [v for v in census.verdicts if not v.serves]
    for verdict in sorted(census.verdicts,
                          key=lambda v: (v.surface, v.path, v.concept)):
        if args.owed and verdict.serves:
            continue
        total = len(verdict.held) + len(verdict.missing)
        mark = "ok  " if verdict.serves else "OWED"
        print(f"  {mark} {verdict.surface:8s} {len(verdict.held)}/{total}  "
              f"{verdict.site}")

    served = len(census.verdicts) - len(owed)
    values = sum(len(v.missing) for v in owed)
    print(f"{len(census.verdicts)} declared consumer(s) of a valued concept: "
          f"{served} serve the registry, {len(owed)} restate — "
          f"{values} value(s) not held by reference.")
    for path, found in sorted(census.enumerations.items()):
        if found:
            print(f"  {path} keeps {len(found)} enumeration(s) of its own: "
                  + ", ".join(str(item) for item in found[:4])
                  + (" ..." if len(found) > 4 else ""))
    return 1 if owed else 0


if __name__ == "__main__":
    raise SystemExit(main())
