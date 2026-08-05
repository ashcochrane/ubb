"""The webhook catalogue's shape: ADR-0006 §5, in one implementation.

G8 in `gates/manifest.yaml`. The catalogue the platform publishes is compared
against the vocabulary registry — not for membership, which is G2's question,
but for the SHAPE ADR-0006 §5 fixes: one domain owner, one state entered, cause
and mechanism in payload fields rather than in the name.

    from tools.webhook_catalogue import assess
    catalogue, errors = assess(repo_root)

`shape.py` carries the rules and the argument for them, `catalogue.py` reads the
live catalogue with `ast` and never imports it, and `assessment.py` joins the two
and subtracts the violations the migration ledger already owes — because the gate
is installed over a catalogue that today violates it twenty times, which is the
ordering #155 §3.1 asks for: a gate installed before the code complies is what
makes the vocabulary impossible to regress.

Its debts are read straight from `gates/migration-ledger.yaml`, with no second
encoding. That is the dividend of living in the contract suite rather than the
platform one — #203's model-naming gates have no PyYAML available where they run
and need `test_model_naming_ledger_agreement.py` to hold two copies of their
seeded sites together. There is exactly one copy here.
"""

from .assessment import (
    GATE,
    LEDGER_PATH,
    REGISTRY_DIR,
    Catalogue,
    Violation,
    assess,
    load_catalogue,
)
from .catalogue import Event
from .errors import CatalogueError, CatalogueInvalid

__all__ = [
    "Catalogue",
    "CatalogueError",
    "CatalogueInvalid",
    "Event",
    "Violation",
    "assess",
    "load_catalogue",
    "GATE",
    "LEDGER_PATH",
    "REGISTRY_DIR",
]
