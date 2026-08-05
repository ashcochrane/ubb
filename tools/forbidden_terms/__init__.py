"""The forbidden-term sweep (#206, gate G7): the retirement table, enforced.

`domain-vocabulary/` says which words are retired. `gates/forbidden-term-sweep.yaml`
says where the sweep looks and — declared, enumerated and counted — where it
deliberately does not. This package is the walker between them.

    from tools.forbidden_terms import load_plan, run

`python -m tools.forbidden_terms` runs the same sweep from a shell.

The gate itself is `tests/contracts/test_forbidden_terms.py`, in the contract
suite, because the sweep's subject is agreement between the platform, the
console, the SDK, the committed contract and the living docs — and a check
hosted by one party to the agreement can only ever see its own side.
"""

from .errors import SweepError, SweepInvalid
from .plan import (
    PERMANENCES,
    PERMANENT,
    PLAN_PATH,
    UNTIL_SLICE_8,
    Area,
    ExclusionRule,
    Plan,
    load_plan,
)
from .sweep import (
    Occurrence,
    Result,
    excused,
    gate_faults,
    pattern,
    run,
    tracked_files,
)

__all__ = [
    "Area",
    "ExclusionRule",
    "Occurrence",
    "PERMANENCES",
    "PERMANENT",
    "PLAN_PATH",
    "Plan",
    "Result",
    "SweepError",
    "SweepInvalid",
    "UNTIL_SLICE_8",
    "excused",
    "gate_faults",
    "load_plan",
    "pattern",
    "run",
    "tracked_files",
]
