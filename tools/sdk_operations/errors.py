"""The named reasons the SDK's call surface can disagree with the contract.

Every failure carries one of the codes below. They are module constants rather
than inline strings for one reason: a test asserts on the code, so a reworded
message never silently turns a negative control into a test that passes for the
wrong reason. Same discipline as ``tools/gates/errors.py`` and
``tools/vocabulary/errors.py``, and deliberately the same shape.
"""

from dataclasses import dataclass

# --- Reading the committed contract -----------------------------------------
SPEC_MISSING = "spec_missing"                  # openapi/v1.json is not there
SPEC_UNREADABLE = "spec_unreadable"            # ... or is not the document it must be
SPEC_EMPTY = "spec_empty"                      # it parsed, and declares no operations
OPERATION_ID_MISSING = "operation_id_missing"  # an operation with no `operationId`
DUPLICATE_OPERATION_ID = "duplicate_operation_id"
TEMPLATE_COLLISION = "template_collision"      # two paths this gate cannot tell apart
ROUTE_MARKER_STALE = "route_marker_stale"      # the contract publishes outside the
                                               # root the stray-literal sweep reads
GENERATED_CLIENT_EMPTY = "generated_client_empty"  # `_core` has no operation modules

# --- Reading the hand-written call surface ----------------------------------
SHELL_MISSING = "shell_missing"                # ubb-sdk/ubb/ is not there
SHELL_EMPTY = "shell_empty"                    # ... or holds no modules to walk
SHELL_UNREADABLE = "shell_unreadable"          # a module does not parse
UNSCANNED_PACKAGE = "unscanned_package"        # a sub-package neither walked nor generated
CALL_NOT_AN_OPERATION = "call_not_an_operation"    # a request naming its target any way
                                               # but a registry constant — a literal, a
                                               # variable, a path built in place
CALL_MALFORMED = "call_malformed"              # a request call with no path argument at all
NO_SUCH_OPERATION_CONSTANT = "no_such_operation_constant"  # `ops.X` where the registry
                                               # declares no `X` — what a rename leaves
PARAMETER_COUNT_WRONG = "parameter_count_wrong"    # ... or the right constant filled with
                                               # the wrong number of values
STRAY_ROUTE_LITERAL = "stray_route_literal"    # a route spelled anywhere in the hand
                                               # shell, which is now the registry's job
STALE_DOCUMENTED_ROUTE = "stale_documented_route"  # a docstring naming a route that is
                                               # neither published nor excused
NO_SUCH_OPERATION = "no_such_operation"        # method + path matches nothing published

# --- The generated operation registry (#209, #155 §8.3) ----------------------
#
# The single file under `ubb-sdk/ubb/` allowed to spell a path. Everything a
# wrapper could once get wrong in a string it now gets wrong in a name, and a
# name is a thing that can be looked up.
REGISTRY_MISSING = "registry_missing"
REGISTRY_DIFFERS = "registry_differs"          # ... or is not what the contract renders
REGISTRY_UNREADABLE = "registry_unreadable"    # ... or is not the file it must be
REGISTRY_INCOMPLETE = "registry_incomplete"    # a published operation it does not name
REGISTRY_ENTRY_UNKNOWN = "registry_entry_unknown"  # an entry naming nothing published and
                                               # nothing the ledger excuses
REGISTRY_ENTRY_WRONG = "registry_entry_wrong"  # an entry whose method or path is not its
                                               # operation's — ADR-0007 §4's `GET` against
                                               # `POST`, at the one place it can still happen
OPERATION_ID_NOT_A_NAME = "operation_id_not_a_name"  # an operationId that is no constant
REGISTRY_NAME_COLLISION = "registry_name_collision"  # two operations under one constant

# There are deliberately no `disposition_*` codes. An earlier shape of this gate
# had a human declare each unwrapped operation's disposition in a checked-in
# file, which needed a family of codes for a mis-declared one. The shipped gate
# DERIVES all three dispositions from the tree instead, so there is nothing to
# mis-declare — see `coverage.py`. The codes went with the design; a constant
# nothing raises is a rule nothing enforces.

# --- The excused invalid calls, read from the migration ledger ---------------
EXCUSE_UNREADABLE = "excuse_unreadable"        # gates/migration-ledger.yaml will not parse
EXCUSE_NOT_A_VIOLATION = "excuse_not_a_violation"  # a seeded debt that is no longer owed

# --- The generated coverage manifest ----------------------------------------
MANIFEST_MISSING = "manifest_missing"
MANIFEST_DIFFERS = "manifest_differs"

# --- The ratchet, which compares against a base ref -------------------------
UNWRAPPED_ROSE = "unwrapped_rose"              # a rise nobody signed for
AUTHORISATION_COUNT_WRONG = "authorisation_count_wrong"  # ... or one that miscounts it
AUTHORISATION_INERT = "authorisation_inert"    # a new authorisation that licensed nothing
BASE_UNREADABLE = "base_unreadable"            # the base ref's manifest could not be read


@dataclass(frozen=True, order=True)
class SurfaceError:
    """One reason the SDK's call surface does not agree with the contract.

    ``location`` names the file and, where there is one, the call — enough for
    a reader to open the right line without re-running anything.
    """
    code: str
    location: str
    message: str

    def __str__(self):
        return f"{self.code}: {self.location}: {self.message}"


class SurfaceInvalid(Exception):
    """Raised with EVERY error found, not just the first.

    A surface with four mistakes should take one run to fix, not four.
    """

    def __init__(self, errors):
        self.errors = tuple(sorted(errors))
        super().__init__(
            f"{len(self.errors)} SDK operation error(s):\n"
            + "\n".join(f"  {error}" for error in self.errors)
        )

    def codes(self):
        """The set of codes reported — what negative controls assert on."""
        return {error.code for error in self.errors}
