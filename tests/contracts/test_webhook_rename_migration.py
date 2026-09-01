"""The rename migration's map agrees with the registry and the ledger (#222).

`0007_rename_thirteen_webhook_event_types.RENAMES` is a second encoding of names
the registry already declares — necessarily so, because a Django migration must
not import application code: it has to keep working when the code has moved on.
The repository's rule for a second encoding is #203's, stated in gates/README.md:
the two copies exist, and a contract test holds them to each other.

**What the platform-side tests cannot catch.** They check that no `RENAMES` key
is still published and that every value is, which a *typo* satisfies for the
wrong reason — `billing.balance_lo` is not published either, so the migration
would rewrite nothing at all and every assertion there would stay green. That is
the #75 shape the migration exists to refuse, reappearing inside its own guard.
The registry closes it: a key must be a name the registry RETIRED, which a typo
is not.

**Why here.** The registry is YAML and the platform suite has no PyYAML
(gates/README.md, deliberately); this suite has PyYAML and no Django. The
migration is read with `ast` and never imported — #204's rule — so nothing here
needs Django settings, a database, or the app registry.

**The one-to-two map is NOT here**, and that was a decision rather than an
oversight. `test_webhook_split_migration.py` beside this module holds the
terminal-event split, whose map takes one retired name to TWO successors — a
shape `test_the_map_is_one_to_one` below refuses BY DESIGN, because a 1:1 map
is what lets THIS migration ship an exact reverse. Two maps with two shapes and
two reverse guarantees are two modules; the readers they share are in
`_helpers`.
"""

import pytest

from _helpers import (
    LEDGER_PATH, REPO_ROOT, module_literal, names_a_gate_still_owes)
from tools.vocabulary import load_registry

MIGRATION_PATH = ("ubb-platform/apps/platform/events/migrations/"
                  "0007_rename_thirteen_webhook_event_types.py")
GATE = "G8"


@pytest.fixture(scope="module")
def renames():
    return module_literal(MIGRATION_PATH, "RENAMES")


@pytest.fixture(scope="module")
def events():
    return load_registry(REPO_ROOT / "domain-vocabulary").concepts[
        "webhook_event_type"]


@pytest.fixture(scope="module")
def still_owed():
    """The names G8's remaining ledger entries say are still published wrong."""
    return names_a_gate_still_owes(GATE)


def test_every_name_being_migrated_from_is_one_the_registry_retired(
        renames, events):
    """The check the platform suite cannot make, and the one a typo fails.

    A key that is not a retired alias is either a misspelling — in which case the
    migration silently rewrites nothing — or a name UBB never agreed to retire.
    """
    unknown = sorted(set(renames) - set(events.retired_aliases))
    assert not unknown, (
        f"{unknown} are not retired names in {events.source}. A key that names "
        f"nothing the registry retired rewrites no row and no test would say so")


def test_every_name_being_migrated_to_is_one_the_registry_declares(
        renames, events):
    unknown = sorted(set(renames.values()) - set(events.values))
    assert not unknown, f"{unknown} are not events the registry declares"


def test_the_migration_renames_nothing_the_ledger_still_owes(
        renames, still_owed):
    """The two halves of the twenty may not overlap.

    A debt is paid by renaming AND deleting its entry, in one act. A migration
    that moved a name the ledger still records would leave the entry excusing a
    violation that no longer exists — a suppression the ratchet cannot see,
    because removing an entry is always allowed and adding one back is not.
    """
    both = sorted(set(renames) & still_owed)
    assert not both, (
        f"{both} are renamed here and still recorded as owed in {LEDGER_PATH}")


def test_the_map_is_one_to_one(renames):
    """Two names collapsing onto one would make the reverse ambiguous, and the
    migration ships a real reverse rather than a noop."""
    targets = list(renames.values())
    assert len(targets) == len(set(targets))
