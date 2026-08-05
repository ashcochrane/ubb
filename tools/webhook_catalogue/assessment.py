"""Join the catalogue, the rules and the ledger into one verdict.

`shape.py` carries ADR-0006 §5's rules and the argument for them; `catalogue.py`
reads the live catalogue with `ast`. This module runs the one over the other and
subtracts the violations the migration ledger already owes.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from tools.vocabulary import load_registry
from tools.vocabulary.errors import RegistryInvalid

from . import errors as E
from .catalogue import read_catalogue
from .errors import CatalogueError, CatalogueInvalid, listed
from .shape import Vocabulary, faults, load_vocabulary


REGISTRY_DIR = "domain-vocabulary"
LEDGER_PATH = "gates/migration-ledger.yaml"

#: The gate these debts are recorded against.
GATE = "G8"

#: How a ledger entry names more than one end-state event. `task.limit_exceeded`
#: is replaced by TWO events rather than renamed to one — #140 §4.3 splits a
#: spend kill from a Task nobody ever closed, because a subscriber alerting on
#: spend incidents must stop being paged when a worker dies. A debt whose
#: payment is a split has to be able to say so.
EXPECTED_SEPARATOR = " and "


@dataclass(frozen=True, order=True)
class Violation:
    """One live event that disagrees with ADR-0006 §5, and every way it does."""
    site: str
    found: str
    faults: tuple

    @property
    def key(self):
        """This violation's identity in the ledger: the site AND the name.

        Both, following #204. A ledger entry keyed on the site alone would stay
        green if the declaring class kept its debt and changed which wrong name
        it published — a suppression the ratchet cannot see, because removing an
        entry is always allowed.
        """
        return (self.site, self.found)


@dataclass(frozen=True)
class Catalogue:
    """The live catalogue, judged."""
    path: str
    events: tuple
    violations: tuple
    #: The `(site, found)` pairs the ledger owes and this run matched.
    excused: frozenset
    vocabulary: Vocabulary


def assess(repo_root):
    """Judge the tree at ``repo_root``; return ``(catalogue, errors)``.

    ``errors`` carries every reason the tree does not comply — the faults of
    every unexcused violation, plus anything wrong with the oracle, the read or
    the ledger's own entries. ``catalogue`` is None only when the assessment
    could not be made at all, which is deliberately distinguished from an
    assessment that found nothing wrong.
    """
    repo_root = Path(repo_root)
    errors = []

    try:
        registry = load_registry(repo_root / REGISTRY_DIR, repo_root)
    except RegistryInvalid as invalid:
        return None, [CatalogueError(
            E.REGISTRY_UNREADABLE, REGISTRY_DIR,
            f"the registry this gate reads as its oracle is itself invalid, so "
            f"nothing can be judged against it: {invalid}")]

    vocabulary, problems = load_vocabulary(registry)
    errors.extend(problems)
    if vocabulary is None:
        return None, errors

    events, problems = read_catalogue(repo_root, vocabulary.catalogue_path)
    errors.extend(problems)
    # A catalogue that yielded NO events holds no debts either, so every seeded
    # entry would look paid. Reporting twenty "this debt is no longer owed"
    # errors beside the one that says why buries the cause under twenty
    # consequences, all of them false.
    #
    # The condition is the empty result, not "the read reported something". A
    # single computed EVENT_TYPE is a problem AND leaves every other event
    # readable, and suppressing the staleness check on it would disable the
    # ledger's own guard for the whole run.
    read_yielded_nothing = not events

    violations = []
    for event in events:
        site = event.site(vocabulary.catalogue_path)
        found = faults(event.name, site, vocabulary)
        if found:
            violations.append(Violation(site=site, found=event.name,
                                        faults=tuple(found)))

    # The END STATE is held to the same rules by the same function. Two of the
    # three conjuncts are satisfied by construction there — the owners and the
    # transitions are derived FROM these values — but the Task one is not, so a
    # future `task.limit_reached` would be refused at the moment it is declared
    # rather than at the moment it is published. These are never excusable: the
    # registry is the agreed end state, so a disagreement here is a mistake to
    # correct, not a debt to record.
    for value in sorted(vocabulary.declared_events):
        errors.extend(faults(
            value, f"{REGISTRY_DIR}/{vocabulary.declared_in}::{value}",
            vocabulary))

    excuses, problems = _read_excuses(repo_root, vocabulary)
    errors.extend(problems)

    owed = {violation.key for violation in violations}
    for key in (() if read_yielded_nothing else sorted(excuses - owed)):
        errors.append(CatalogueError(
            E.EXCUSE_NOT_A_VIOLATION, key[0],
            f"the ledger owes `{key[1]}` here under {GATE} and this run found "
            f"no such violation. A seeded debt cannot outlive the violation it "
            f"records — paying it and deleting its entry are one act"))

    for violation in violations:
        if violation.key not in excuses:
            errors.extend(violation.faults)

    return Catalogue(
        path=vocabulary.catalogue_path,
        events=events,
        violations=tuple(violations),
        excused=frozenset(excuses & owed),
        vocabulary=vocabulary,
    ), errors


def load_catalogue(repo_root):
    """:func:`assess`, raising :class:`CatalogueInvalid` on any disagreement.

    The entry point a caller wants when "it complies" is the only acceptable
    answer. Every error is carried, not just the first.
    """
    catalogue, errors = assess(repo_root)
    if errors:
        raise CatalogueInvalid(errors)
    return catalogue


def _read_excuses(repo_root, vocabulary):
    """The `(site, found)` pairs the migration ledger owes under G8.

    A ledger that is not there excuses nothing, which is the correct reading for
    a synthetic repository and for a checkout that has not got one — it is the
    ledger's own suite that asserts the shipped one exists.
    """
    path = repo_root / LEDGER_PATH
    if not path.is_file():
        return set(), []

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as problem:
        return set(), [CatalogueError(
            E.EXCUSE_UNREADABLE, LEDGER_PATH, f"it does not parse: {problem}")]
    if not isinstance(document, dict):
        return set(), [CatalogueError(
            E.EXCUSE_UNREADABLE, LEDGER_PATH, "it is not a mapping")]

    excuses, errors = set(), []
    for entry in document.get("entries") or ():
        if not isinstance(entry, dict) or entry.get("gate") != GATE:
            continue
        site, found = entry.get("site"), entry.get("found")
        if not isinstance(site, str) or not isinstance(found, str):
            errors.append(CatalogueError(
                E.EXCUSE_UNREADABLE, LEDGER_PATH,
                f"a {GATE} entry carries no `site` and `found` pair, which is "
                f"the identity this gate matches an excuse on: {entry!r}"))
            continue
        excuses.add((site, found))

        expected = entry.get("expected")
        named = (expected.split(EXPECTED_SEPARATOR)
                 if isinstance(expected, str) else [])
        unknown = [name for name in named
                   if name not in vocabulary.declared_events]
        if not named or unknown:
            errors.append(CatalogueError(
                E.EXCUSE_EXPECTED_NOT_DECLARED, site,
                f"`expected` is {expected!r}, which names "
                f"{'nothing' if not named else listed(unknown)} the registry "
                f"declares. A webhook debt is paid by taking an end-state name, "
                f"so `expected` names one or more of them, joined by "
                f"`{EXPECTED_SEPARATOR.strip()}` where one event becomes two"))

    return excuses, errors
