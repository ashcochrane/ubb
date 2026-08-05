"""``python -m tools.vocabulary`` — validate a registry and report on it.

Run from the git root:

    python -m tools.vocabulary

Exit status 0 with a summary, or 1 with one line per reason it failed. CI runs
the same check through `tests/contracts/`; this exists so a human editing the
registry gets the same verdict without waiting for a workflow.
"""

import argparse
import sys
from pathlib import Path

from .compiler import load_registry
from .errors import RegistryInvalid

DEFAULT_REGISTRY = "domain-vocabulary"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tools.vocabulary",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, type=Path,
                        help=f"registry directory (default: {DEFAULT_REGISTRY})")
    parser.add_argument("--repo-root", default=None, type=Path,
                        help="what declared consumer paths resolve against "
                             "(default: the registry's parent directory)")
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry, args.repo_root)
    except RegistryInvalid as invalid:
        print(f"{args.registry} is INVALID — {len(invalid.errors)} error(s):",
              file=sys.stderr)
        for error in invalid.errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print(f"{args.registry} is valid.")
    for line in registry.describe():
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
