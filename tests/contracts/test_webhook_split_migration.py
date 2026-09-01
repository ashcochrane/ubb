"""The split migration's map agrees with the registry and the ledger (#140 §4.3).

`0008_the_two_terminal_task_events_become_four.SPLIT` is a second encoding of
names the registry already declares — necessarily so, because a Django
migration must not import application code: it has to keep working when the
code has moved on. The repository's rule for a second encoding is #203's,
stated in gates/README.md: the two copies exist, and a contract test holds them
to each other.

**A SIBLING RATHER THAN AN EXTENSION, and the reason is in one assertion.**
`test_webhook_rename_migration.py` ends with `test_the_map_is_one_to_one`,
whose stated force is that a 1:1 map is what lets `0007` ship a real reverse
instead of a noop. This map is deliberately one-to-TWO and its reverse is a
lossy collapse, so the two migrations make two different promises about the
same field of the same gate — and a module parameterised over both would have
to take the shape as an argument to every assertion, which is the same
collapse the migration itself refused when it wrote two functions for two
tables. The readers the two modules share live in `_helpers`.

**What the platform suite cannot catch**, exactly as for `0007`: it checks that
no key is still published and that every successor is, which a TYPO satisfies
for the wrong reason — a misspelled key is not published either, so the
migration would rewrite nothing at all and every assertion there would stay
green. That is the #75 shape the migration exists to refuse, reappearing inside
its own guard. The registry closes it: a key must be a name the registry
RETIRED, which a typo is not.

**Nothing here spells either retired name.** They are read off the map, which
is also the comparison worth making: a hard-coded pair would agree with both
the map and the registry right up until one of them moved.
"""

import pytest

from _helpers import (
    LEDGER_PATH, REPO_ROOT, module_literal, names_a_gate_still_owes)
from tools.vocabulary import load_registry

MIGRATION_PATH = ("ubb-platform/apps/platform/events/migrations/"
                  "0008_the_two_terminal_task_events_become_four.py")
GATE = "G8"


@pytest.fixture(scope="module")
def split():
    return module_literal(MIGRATION_PATH, "SPLIT")


@pytest.fixture(scope="module")
def events():
    return load_registry(REPO_ROOT / "domain-vocabulary").concepts[
        "webhook_event_type"]


@pytest.fixture(scope="module")
def still_owed():
    """The names G8's remaining ledger entries say are still published wrong."""
    return names_a_gate_still_owes(GATE)


def test_every_name_being_split_is_one_the_registry_retired(split, events):
    """The check the platform suite cannot make, and the one a typo fails."""
    unknown = sorted(set(split) - set(events.retired_aliases))
    assert not unknown, (
        f"{unknown} are not retired names in {events.source}. A key that names "
        f"nothing the registry retired rewrites no row and no test would say so")


def test_every_successor_is_one_the_registry_declares(split, events):
    successors = {name for pair in split.values() for name in pair}
    unknown = sorted(successors - set(events.values))
    assert not unknown, f"{unknown} are not events the registry declares"


def test_the_migration_splits_nothing_the_ledger_still_owes(split, still_owed):
    """A debt is paid by rewriting the name AND deleting its entry, in one act.

    A migration that moved a name the ledger still records would leave the
    entry excusing a violation that no longer exists — a suppression the
    ratchet cannot see, because removing an entry is always allowed and adding
    one back is not.
    """
    both = sorted(set(split) & still_owed)
    assert not both, (
        f"{both} are split here and still recorded as owed in {LEDGER_PATH}")


def test_the_map_is_one_to_two(split):
    """The shape this migration exists for, and the reason it is not `0007`'s.

    A one-to-two map cannot be expressed as a rename, which is the whole of
    why `0007` excluded these two names and said so in its own docstring.
    """
    assert split, "an empty map would satisfy every other check here"
    for retired, successors in split.items():
        assert len(successors) == 2, (
            f"{retired} names {len(successors)} successors; the split is into "
            f"two states, and a different arity is a different migration")
        assert len(set(successors)) == 2, (
            f"{retired} names the same successor twice, so one of the two "
            f"states it is supposed to distinguish has no event")


def test_no_two_retired_names_share_a_successor(split):
    """Each successor comes from exactly ONE retired name, or the reverse would
    be ambiguous in a way the migration does not document.

    The collapse it DOES document is the two successors of one name going back
    to that name. Two DIFFERENT names sharing a successor would make even that
    undecidable, and the reverse would silently pick one.
    """
    seen = {}
    for retired, successors in split.items():
        for successor in successors:
            assert successor not in seen, (
                f"{successor} is a successor of both {seen[successor]} and "
                f"{retired}, so the reverse cannot say which it came from")
            seen[successor] = retired


def test_the_domain_owner_survives_the_split(split):
    """ADR-0006 §5's name is `<domain owner>.<past-tense state entered>`, and a
    split changes the SECOND half only.

    The lifecycle that moved belongs to the same resource before and after —
    the whole change is that the state entered is now said out loud — so a
    successor under a different owner would be a different event wearing this
    migration's map.
    """
    for retired, successors in split.items():
        owner = retired.split(".", 1)[0]
        wrong = sorted(n for n in successors if n.split(".", 1)[0] != owner)
        assert not wrong, (
            f"{wrong} do not belong to `{owner}`, the owner whose lifecycle "
            f"{retired} announced")


# ⚠ THE REVERSE MAP IS NOT CHECKED HERE, and the reason is this suite's own
# rule rather than an omission. `COLLAPSE` is DERIVED from `SPLIT` in the
# migration — which is what stops the two directions drifting — and a
# comprehension is not a literal, so the reader above (`ast.literal_eval`, #204,
# no Django in this suite) cannot evaluate it. Writing it out as a literal to
# make it readable here would reintroduce exactly the drift the derivation
# removes. It is asserted where a module may IMPORT the migration:
# `apps/platform/events/tests/test_the_two_terminal_events_become_four.py`,
# which drives both directions over real rows.
