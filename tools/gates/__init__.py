"""The gate programme: the manifest, the ledger, and the rules over both.

`gates/` at the git root is the checked-in account of every gate ADR-0008 §8
establishes — what each asserts, what oracle settles it, and whether it is
running today or owed by a named slice. This package reads it, and checks the
claims against the repository rather than taking them.

    from tools.gates import load_programme
    programme = load_programme("gates", ".")

`python -m tools.gates` runs the same check from a shell, and
`python -m tools.gates ratchet` runs the ledger's shrink-only comparison against
the base branch. It has no Django, no database and no settings: the gates it
accounts for live in the platform, the SDK, the console and the workflow, and a
checker hosted by one of them could only see its own side.
"""

from .compiler import (
    Authorisation,
    LedgerEntry,
    PermanentException,
    Programme,
    Row,
    Site,
    Slice,
    Suite,
    load_programme,
    owner_slice_of,
)
from .errors import GateError, GatesInvalid

__all__ = [
    "Authorisation",
    "GateError",
    "GatesInvalid",
    "LedgerEntry",
    "PermanentException",
    "Programme",
    "Row",
    "Site",
    "Slice",
    "Suite",
    "load_programme",
    "owner_slice_of",
]
