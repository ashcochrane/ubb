"""The SDK operation gate: what the hand-written client calls, and what it misses.

Two properties, from ADR-0007 §4 and #155 §8.2, settled from one join:

- **Forward** — every hand-written SDK call targets a real published operation,
  matched on the complete identity (method AND normalised path).
- **Reverse** — every published operation carries an explicit disposition in a
  generated manifest that stays mechanically accurate.

The public surface is small on purpose:

    load_coverage(repo_root)   the join, raising SurfaceInvalid if anything is wrong
    assess(repo_root)          the same, returning (coverage, errors) instead

`gates/manifest.yaml` records these as G17 and G18. `tools/gates` is the
programme's bookkeeping; this is one of the checks it accounts for.
"""

from .coverage import Coverage, Row, assess, load_coverage
from .errors import SurfaceError, SurfaceInvalid

__all__ = ["Coverage", "Row", "SurfaceError", "SurfaceInvalid", "assess",
           "load_coverage"]
