"""``python -m tools.vocabulary`` — validate a registry, and keep what it
generates current.

Run from the git root:

    python -m tools.vocabulary            # check: is the registry valid, and
                                          # is every generated artifact current?
    python -m tools.vocabulary --write     # regenerate the stale ones

Exit status 0 with a summary, or 1 with one line per reason it failed. CI runs
the same checks through `tests/contracts/`; this exists so a human editing the
registry gets the same verdict without waiting for a workflow — including the
one that is easiest to forget, which is that editing the registry alone leaves
every generated consumer a commit behind.
"""

import argparse
import sys
from pathlib import Path

from .compiler import load_registry
from .errors import RegistryInvalid
from .generate import TARGETS, GenerationFailed, stale_targets, write_targets

DEFAULT_REGISTRY = "domain-vocabulary"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tools.vocabulary",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, type=Path,
                        help=f"registry directory (default: {DEFAULT_REGISTRY})")
    parser.add_argument("--repo-root", default=None, type=Path,
                        help="what declared consumer paths resolve against, and "
                             "where generated artifacts are written "
                             "(default: the registry's parent directory)")
    parser.add_argument("--write", action="store_true",
                        help="regenerate every stale artifact instead of "
                             "reporting it")
    args = parser.parse_args(argv)
    # Derived once, so consumer resolution and artifact writing can never be
    # rooted at two different directories.
    repo_root = args.repo_root if args.repo_root is not None else args.registry.parent

    try:
        registry = load_registry(args.registry, repo_root)
    except RegistryInvalid as invalid:
        # Nothing is written from an invalid registry. A half-broken registry
        # still renders *something*, and overwriting a correct artifact with it
        # is the one mistake a generator does not get to make twice.
        print(f"{args.registry} is INVALID — {len(invalid.errors)} error(s):",
              file=sys.stderr)
        for error in invalid.errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    if args.write:
        try:
            written = write_targets(registry, repo_root)
        except GenerationFailed as failure:
            return _report_generation_failure(failure)
        if not written:
            print(f"generated artifacts: {len(TARGETS)} already up to date.")
        else:
            print(f"wrote {len(written)} of {len(TARGETS)} generated artifact(s):")
            for path in written:
                print(f"  {path}")
        return 0

    print(f"{args.registry} is valid.")
    for line in registry.describe():
        print(f"  {line}")

    try:
        stale = stale_targets(registry, repo_root)
    except GenerationFailed as failure:
        return _report_generation_failure(failure)
    if stale:
        print(f"{len(stale)} generated artifact(s) are NOT what the registry "
              f"produces:", file=sys.stderr)
        for entry in stale:
            print(f"  {entry.path}: {entry.reason}", file=sys.stderr)
        print("Run `python -m tools.vocabulary --write` and commit the result.",
              file=sys.stderr)
        return 1
    print(f"  generated artifacts: {len(TARGETS)} up to date")
    return 0


def _report_generation_failure(failure):
    """A valid registry that no artifact can be rendered from, reported like
    every other fault rather than as a traceback out of the tool.

    The registry passed every rule it declares, so `is INVALID` would be a
    false statement — this is a surface that cannot express what the registry
    legitimately says, and the message has to distinguish the two or the author
    goes looking for a registry error that is not there.
    """
    print("the registry is valid but cannot be generated from:", file=sys.stderr)
    print(f"  {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
