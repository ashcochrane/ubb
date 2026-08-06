"""The console's label catalogue, and what still invents English without one.

ADR-0008 §4 splits one file in two. `domain-vocabulary/` owns **identity** — the
concepts, their values, and the stable key each value's wording hangs on. The
console owns **expression** — the words themselves, per locale, because wording,
capitalisation and translation change far more often than the token underneath.

This package is G6: the check that the two halves meet exactly, and that nothing
in the console still manufactures a name out of a token behind their backs.

    from tools.labels import read_catalogue, required_keys, coverage_faults
    from tools.labels import scan_legacy

    catalogue, faults = read_catalogue(repo_root)
    findings = coverage_faults(required_keys(registry), catalogue, registry)
    legacy, more_faults = scan_legacy(repo_root)

Two modules, because they answer two different questions and only one of them
is about the registry:

    catalogue.py   does every registry value have wording, in every shipped
                   locale, and does every wording name a live registry value?
    legacy.py      what still humanises, and is every one of those a debt the
                   migration ledger records with an owner slice?

`tests/contracts/test_label_catalogue.py` is where both are enforced.
"""

from .catalogue import (
    Catalogue,
    Locale,
    coverage_faults,
    read_catalogue,
    required_keys,
    retired_labels,
    retired_tokens,
    split_key,
)
from .errors import LabelError
from .legacy import Legacy, scan_legacy

__all__ = [
    "Catalogue",
    "LabelError",
    "Legacy",
    "Locale",
    "coverage_faults",
    "read_catalogue",
    "required_keys",
    "retired_labels",
    "retired_tokens",
    "scan_legacy",
    "split_key",
]
