"""The named reasons the webhook catalogue can disagree with ADR-0006 §5.

Every failure carries one of the codes below. They are module constants rather
than inline strings for one reason: a test asserts on the code, so a reworded
message never silently turns a negative control into a test that passes for the
wrong reason. Same discipline as ``tools/gates/errors.py``,
``tools/vocabulary/errors.py`` and ``tools/sdk_operations/errors.py``, and
deliberately the same shape.
"""

from dataclasses import dataclass

# --- Reading the registry, which is this gate's oracle -----------------------
REGISTRY_UNREADABLE = "registry_unreadable"    # domain-vocabulary/ does not compile
CONCEPT_MISSING = "concept_missing"            # a concept the rules are stated in terms of
CATALOGUE_UNDECLARED = "catalogue_undeclared"  # webhook_event_type declares no backend consumer
NON_TERMINAL_STATUS_UNKNOWN = "non_terminal_status_unknown"  # `active` is no longer a status

# --- Reading the live catalogue ---------------------------------------------
CATALOGUE_UNREADABLE = "catalogue_unreadable"  # the declared consumer does not read
                                               # or does not parse. There is no
                                               # separate "missing" code: the
                                               # registry refuses a consumer path
                                               # that is not in the repository, so
                                               # a deleted catalogue is a broken
                                               # oracle and reported as one
CATALOGUE_EMPTY = "catalogue_empty"            # it parsed, and declares no event at all
EVENT_TYPE_NOT_LITERAL = "event_type_not_literal"  # an EVENT_TYPE this gate cannot read
DUPLICATE_EVENT_TYPE = "duplicate_event_type"  # two payload classes claiming one name

# --- ADR-0006 §5's shape, over one event name -------------------------------
NAME_MALFORMED = "name_malformed"              # not `<owner>.<transition>` at all
OWNER_NOT_A_DOMAIN_OWNER = "owner_not_a_domain_owner"  # a product or a mechanism
TRANSITION_NOT_A_DECLARED_STATE = "transition_not_a_declared_state"  # a cause, or a coinage
TASK_EVENT_WITHOUT_A_STATUS = "task_event_without_a_status"  # names no `task_status` value

# --- The excused violations, read from the migration ledger -----------------
EXCUSE_UNREADABLE = "excuse_unreadable"        # gates/migration-ledger.yaml will not parse
EXCUSE_NOT_A_VIOLATION = "excuse_not_a_violation"  # a seeded debt that is no longer owed
EXCUSE_EXPECTED_NOT_DECLARED = "excuse_expected_not_declared"  # it points at no end-state name


@dataclass(frozen=True, order=True)
class CatalogueError:
    """One reason the catalogue does not agree with ADR-0006 §5.

    ``location`` names the file and, where there is one, the declaring class —
    enough for a reader to open the right line without re-running anything.
    """
    code: str
    location: str
    message: str

    def __str__(self):
        return f"{self.code}: {self.location}: {self.message}"


def listed(names):
    """Names, quoted and comma-joined, for a message a reader can act on."""
    return ", ".join(f"`{name}`" for name in names)


class CatalogueInvalid(Exception):
    """Raised with EVERY error found, not just the first.

    A catalogue with four mistakes should take one run to fix, not four.
    """

    def __init__(self, errors):
        self.errors = tuple(sorted(errors))
        super().__init__(
            f"{len(self.errors)} webhook catalogue error(s):\n"
            + "\n".join(f"  {error}" for error in self.errors)
        )
