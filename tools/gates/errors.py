"""The named reasons the gate programme can be invalid.

Every failure the compiler reports carries one of the codes below. They are
module constants rather than inline strings for one reason: a test asserts on
the code, so a reworded message never silently turns a negative control into a
test that passes for the wrong reason. Same discipline as
``tools/vocabulary/errors.py``, and deliberately the same shape.
"""

from dataclasses import dataclass

# --- Structure: the directory and the files in it ---------------------------
GATES_MISSING = "gates_missing"                # the directory or a required file is absent
UNEXPECTED_FILE = "unexpected_file"            # something in gates/ nothing reads
YAML_INVALID = "yaml_invalid"                  # a file does not parse
DUPLICATE_KEY = "duplicate_key"                # the same key twice in one mapping
FILE_NOT_MAPPING = "file_not_mapping"          # a file is not the mapping it must be
SCHEMA_INVALID = "schema_invalid"              # schema.yaml does not describe a usable schema
WORKFLOW_MISSING = "workflow_missing"          # the CI workflow is absent
WORKFLOW_INVALID = "workflow_invalid"          # ... or present and unreadable

# --- The slices -------------------------------------------------------------
SLICES_INVALID = "slices_invalid"              # slices.yaml declares no usable slices
SLICE_NOT_MAPPING = "slice_not_mapping"        # a slice body is not a mapping
SLICE_MISSING_FIELD = "slice_missing_field"    # issue / title / order / landed
SLICE_INVALID_FIELD_TYPE = "slice_invalid_field_type"  # present but the wrong shape
DUPLICATE_SLICE_ISSUE = "duplicate_slice_issue"        # two slices, one issue number
DUPLICATE_SLICE_ORDER = "duplicate_slice_order"        # two slices, one position in the chain

# --- The declared pytest suites ---------------------------------------------
SUITE_NOT_MAPPING = "suite_not_mapping"
SUITE_MISSING_FIELD = "suite_missing_field"
SUITE_UNKNOWN_FIELD = "suite_unknown_field"    # a field a suite may not carry
SUITE_INVALID_FIELD_TYPE = "suite_invalid_field_type"
SUITE_ROOT_MISSING = "suite_root_missing"      # the suite's root is not in the repository
SUITE_CONFIG_MISSING = "suite_config_missing"  # a declared pytest config file is absent

# --- Manifest rows ----------------------------------------------------------
ROW_NOT_MAPPING = "row_not_mapping"            # a gate/obligation body is not a mapping
MISSING_FIELD = "missing_field"                # a field this status requires
FORBIDDEN_FIELD = "forbidden_field"            # a field this status forbids
UNKNOWN_FIELD = "unknown_field"                # a field the schema declares nowhere
INVALID_FIELD_TYPE = "invalid_field_type"      # a field present but the wrong shape or blank
UNKNOWN_STATUS = "unknown_status"              # not `installed`, `deferred_obligation`, or
                                               # `owned_by_<a slice declared in slices.yaml>`
INVENTORY_MISMATCH = "inventory_mismatch"      # the gates are not exactly ADR-0008 §8's twenty-seven
LANDED_SLICE_OWNS_GATE = "landed_slice_owns_gate"  # a landed slice still owes an installation

# --- Enforcement: an `installed` row's claim that a check actually runs ------
ENFORCEMENT_NOT_MAPPING = "enforcement_not_mapping"
ENFORCEMENT_EMPTY = "enforcement_empty"            # `installed` naming no site at all
UNKNOWN_ENFORCEMENT_KIND = "unknown_enforcement_kind"  # neither suite_node nor workflow_step
UNKNOWN_SUITE = "unknown_suite"                    # a suite the manifest does not declare
GATE_NOT_RUNNING = "gate_not_running"              # the named site is not armed, or not collected

# --- The migration ledger and the permanent exceptions ----------------------
#
# One family for both lists. They are separate LISTS with different shapes, but
# "a required field is missing" is the same fault wherever it happens, and the
# error's `location` names the file. A parallel EXCEPTION_* family would say
# nothing the location does not.
ENTRY_NOT_MAPPING = "entry_not_mapping"
ENTRY_MISSING_FIELD = "entry_missing_field"
ENTRY_UNKNOWN_FIELD = "entry_unknown_field"
ENTRY_INVALID_FIELD_TYPE = "entry_invalid_field_type"
DUPLICATE_ENTRY_ID = "duplicate_entry_id"          # the same id twice
DUPLICATE_ENTRY_SITE = "duplicate_entry_site"      # the same (gate, site) twice
UNKNOWN_GATE = "unknown_gate"                      # an entry naming a gate the manifest lacks
GATE_NOT_INSTALLED = "gate_not_installed"          # ... or one that cannot fail anything yet
UNKNOWN_SLICE = "unknown_slice"                    # an owner slice slices.yaml does not declare
OWNER_SLICE_LANDED = "owner_slice_landed"          # a debt owed by a slice that already landed
AUTHORISATION_NOT_MAPPING = "authorisation_not_mapping"
AUTHORISATION_MISSING_FIELD = "authorisation_missing_field"
AUTHORISATION_UNKNOWN_FIELD = "authorisation_unknown_field"
AUTHORISATION_INVALID_FIELD_TYPE = "authorisation_invalid_field_type"

# --- The ratchet, which compares against a base ref -------------------------
LEDGER_GREW = "ledger_grew"                    # an entry added with no authorisation for its gate
AUTHORISATION_COUNT_WRONG = "authorisation_count_wrong"  # ... or one that miscounts the additions
AUTHORISATION_INERT = "authorisation_inert"    # a new authorisation that licensed no addition
DEBT_DEFERRED = "debt_deferred"                # an entry's owner slice moved later
BASE_UNREADABLE = "base_unreadable"            # the base ref's ledger could not be read


@dataclass(frozen=True, order=True)
class GateError:
    """One reason the programme is invalid.

    ``location`` names the file and, where there is one, the row — enough for a
    reader to open the right line without re-running anything.
    """
    code: str
    location: str
    message: str

    def __str__(self):
        return f"{self.code}: {self.location}: {self.message}"


class GatesInvalid(Exception):
    """Raised with EVERY error found, not just the first.

    A manifest with four mistakes should take one run to fix, not four.
    """

    def __init__(self, errors):
        self.errors = tuple(sorted(errors))
        super().__init__(
            f"{len(self.errors)} gate programme error(s):\n"
            + "\n".join(f"  {error}" for error in self.errors)
        )

    def codes(self):
        """The set of codes reported — what negative controls assert on."""
        return {error.code for error in self.errors}
