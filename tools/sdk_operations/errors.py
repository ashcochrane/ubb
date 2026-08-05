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
CALL_NOT_LITERAL = "call_not_literal"          # a method or path this gate cannot resolve
CALL_MALFORMED = "call_malformed"              # a request call with no path argument at all
STRAY_ROUTE_LITERAL = "stray_route_literal"    # a route spelled outside any call this gate reads
NO_SUCH_OPERATION = "no_such_operation"        # method + path matches nothing published

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
