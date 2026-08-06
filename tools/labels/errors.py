"""The named reasons the label catalogue could not be read, or is wrong.

Two families, and the split matters as much here as it does in
``tools/consumers/errors.py``:

- a **fault** means the check could not be taken — the locales directory is
  gone, a catalogue will not parse, the adapter module has moved. A gate that
  cannot see is not a gate that found nothing;
- a **finding** is a real disagreement between the registry and the console —
  a value with no wording, a key naming nothing, a retired token still labelled.

Both carry codes rather than prose alone, for the reason ``tools/gates/errors``
gives: a negative control asserts on the code, so a reworded message never
turns a control into a test that passes for the wrong reason. Every code below
is asserted on by a control in `tests/contracts/test_label_catalogue.py`.
"""

from dataclasses import dataclass

# --- faults: the check could not be taken -----------------------------------

LOCALES_MISSING = "locales_missing"            # the locales directory is absent
INDEX_MISSING = "index_missing"                # ... or carries no index module
LOCALE_UNDECLARED = "locale_undeclared"        # a catalogue file no index imports
LOCALE_MISSING = "locale_missing"              # ... or an import with no file
LOCALE_UNPARSEABLE = "locale_unparseable"      # a catalogue that is not JSON
LOCALE_MALFORMED = "locale_malformed"          # ... or is JSON of the wrong shape
DEFAULT_LOCALE_MISSING = "default_locale_missing"  # no `en` to fall back to
ADAPTER_MISSING = "adapter_missing"            # the legacy module is not where it was
ADAPTER_ESCAPED = "adapter_escaped"            # a second humaniser outside it

# --- findings: the two sides disagree ---------------------------------------

UNLABELLED_VALUE = "unlabelled_value"          # a registry value with no wording
UNKNOWN_KEY = "unknown_key"                    # a key naming no registry value
RETIRED_KEY = "retired_key"                    # a key naming a retired token
BLANK_LABEL = "blank_label"                    # a key whose wording is empty


@dataclass(frozen=True, order=True)
class LabelError:
    """One fault or one finding.

    ``location`` names the file and — where there is one — the locale or the
    concept, so a reader can open the right line without re-running anything.
    """
    code: str
    location: str
    message: str

    def __str__(self):
        return f"{self.code}: {self.location}: {self.message}"
