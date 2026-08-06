"""The named reasons the consumer census could not be taken.

Every code here is a **fault**: the walk did not happen. A surface whose
generated artifact is missing, a consumer file that will not parse, an import
shape that hides the answer. A fault is never a migration debt — it means the
census cannot see, and a gate that cannot see is not a gate that found nothing.

**A finding has no code, deliberately.** What the census finds is a
:class:`~tools.consumers.census.Finding` — a registry value a declared consumer
does not hold by reference — and it is fully described by the concept, the
surface and the value. A code would be one word for the only thing findings can
say, and a constant nothing distinguishes is the dead vocabulary
`gates/README.md` refuses in the manifest for the same reason.

The codes below are module constants rather than inline strings for the reason
``tools/gates/errors.py`` gives: a negative control asserts on the code, so a
reworded message never silently turns it into a test that passes for the wrong
reason. Each is asserted on by a control in
`tests/contracts/test_consumer_census.py` or
`tests/contracts/test_consumer_references.py`.
"""

from dataclasses import dataclass

ARTIFACT_MISSING = "artifact_missing"          # a surface's generated file is absent
CONSUMER_MISSING = "consumer_missing"          # a declared consumer path is not in the tree
CONSUMER_UNREADABLE = "consumer_unreadable"    # ... or present and undecodable
CONSUMER_UNPARSEABLE = "consumer_unparseable"  # ... or present and not the language it must be
STAR_IMPORT = "star_import"                    # `from x import *` — in scope, but unreadable
ALIAS_UNRESOLVED = "alias_unresolved"          # the console's `@/` path alias is undeclared


@dataclass(frozen=True, order=True)
class CensusError:
    """One reason the census could not be taken.

    ``location`` names the surface, the file and — where there is one — the
    concept, so a reader can open the right line without re-running anything.
    """
    code: str
    location: str
    message: str

    def __str__(self):
        return f"{self.code}: {self.location}: {self.message}"
