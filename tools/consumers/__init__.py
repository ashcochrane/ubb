"""The consumer census: does a declared consumer serve the registry's values?

`domain-vocabulary/consumers.yaml` says a declared consumer is an **end-state**
consumer — the place a canonical value will live once its slice has run, not a
claim that the file already carries it. This package is the check that closes
that sentence: it asks, of every concept the registry gives values to and every
consumer the registry declares for it, whether the consumer holds those values
**by reference** to the generated artifact, or restates them.

    from tools.consumers import take_census
    census = take_census(repo_root, registry)
    census.serves("task_status", "backend")   # the predicate #208 consumes

One mechanism, two gates over it (#158 §3.2 and §3.3):

- **G2** asks it of `closed` concepts — UBB owns the whole value set, so a
  consumer restating one has a second copy that can drift.
- **G3** asks it of `open` ones, and asks it in one direction only. A
  registry-known value a consumer does not hold is a defect; a value the
  registry has never seen is legal and is never reported, because ADR-0003
  exists to stop UBB learning a new value from being a CI failure.

`python -m tools.consumers` runs the same census from a shell.
"""

from .census import (
    Census,
    Finding,
    Verdict,
    declared_value_sets,
    serving_surfaces,
    take_census,
)
from .errors import CensusError

__all__ = [
    "Census",
    "CensusError",
    "Finding",
    "Verdict",
    "declared_value_sets",
    "serving_surfaces",
    "take_census",
]
