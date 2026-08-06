"""The SDK operation gate: what the hand-written client calls, and what it misses.

Three properties, from ADR-0007 §4 and #155 §8.2 and §8.3, settled from one join:

- **Forward** — every hand-written SDK call targets a real published operation,
  matched on the complete identity (method AND normalised path).
- **Reverse** — every published operation carries an explicit disposition in a
  generated manifest that stays mechanically accurate.
- **Confined** — a call *names* an operation rather than spelling a route, and
  the one file allowed to spell one is `ubb-sdk/ubb/_operations.py`, generated
  here from the contract and the ledger.

The third is what makes the first durable. Checking 81 hand-written routes
against the contract catches a wrong one; leaving no way to write a route
catches the next one too, and the parameter counts an f-string never could.

The public surface is small on purpose:

    load_coverage(repo_root)   the join, raising SurfaceInvalid if anything is wrong
    assess(repo_root)          the same, returning (coverage, errors) instead
    rebuild_registry(root)     regenerate the registry alone, before either

`gates/manifest.yaml` records these as G17 and G18. `tools/gates` is the
programme's bookkeeping; this is one of the checks it accounts for.
"""

from .coverage import Coverage, Row, assess, load_coverage, rebuild_registry
from .errors import SurfaceError, SurfaceInvalid

__all__ = ["Coverage", "Row", "SurfaceError", "SurfaceInvalid", "assess",
           "load_coverage", "rebuild_registry"]
