"""The census, and the one predicate over it.

**Does this consumer serve the registry's values?** That question is asked here
exactly once. G2 asks it of `closed` concepts, G3 asks it of `open` ones in one
direction only, and #208 asks it of the backend before letting the committed
contract advertise a value. Two implementations of one predicate is the shape
that already bit #203, whose agreement test was wrong until it was run — so the
gates import this rather than each walking the tree their own way.

The unit is a **value**, not a file. A consumer holds a value when it references
a generated name that carries it: the concept's whole-set name carries all of
them, and — where the language binds one — a per-value constant carries one. So
`ubb-platform/apps/platform/tenants/models.py` importing two of a concept's
three constants is measured as two of three, which is what it is, rather than as
a served consumer or an unserved one.

Two things this deliberately does NOT do, both stated because a reader would
otherwise assume them:

**It never reads a value.** Not from the registry into a matcher, not from the
consumer's source. The names come from the generator (:mod:`tools.vocabulary.
generate`), which is the one authority on what it binds, and the references come
from imports. #191 decision 3: a literal scan is a check a coincidence can
satisfy.

**A restatement is a fact about a FILE, never about a concept.** The census also
records where each consumer keeps its own enumerations — the `choices=` lists,
the `as const` arrays, the `Literal[...]` annotations — because "this consumer
keeps five of its own" and "this consumer keeps none and takes a bare string" are
different debts with different payments. What it does not do is say *which*
concept an enumeration belongs to, and it cannot: the only mechanical way to
attribute one is to compare its members against a registry value set, which is
the literal scan #191 decision 3 rules out. So the count sits beside the verdicts
rather than inside them, and no finding is ever derived from it.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from tools.vocabulary.generate import (
    BACKEND_CONSTANTS,
    CONSOLE_VOCABULARY,
    SDK_CONSTANTS,
)

from . import errors as codes
from .declarations import (
    django_choices,
    literal_annotations,
    typescript_enumerations,
)
from .errors import CensusError
from .references import (
    console_alias_roots,
    console_specifiers,
    python_references,
    resolve_alias_roots,
    typescript_references,
)


@dataclass(frozen=True)
class GeneratedSurface:
    """One registry surface that has an artifact its consumers can import.

    Everything language-specific about a surface lives on this record, so
    "which language is this consumer?" is answered once. Answering it in three
    places — once to pick a reference reader, once to pick a set of generated
    handles, once to pick an enumeration shape — is three chances to add a
    fourth surface and update two of them.
    """
    #: The `tools.vocabulary.generate` target that renders the artifact, and
    #: the authority on which names carry which values.
    target: object
    #: The module a Python consumer imports the artifact as, or ``None`` where
    #: the surface is not Python. Not derived from the path, because the two
    #: are genuinely different facts: `ubb-platform/core/vocabulary.py` is
    #: `core.vocabulary` only because `ubb-platform` is the interpreter's root,
    #: and `ubb-sdk/ubb/vocabulary.py` is `ubb.vocabulary` only because
    #: `ubb-sdk` is a distribution root.
    module: str | None
    #: How this surface spells an enumeration of its own (#227): Django
    #: `choices=`, a TypeScript `as const` array or union, an SDK `Literal[...]`.
    enumerations: object

    @property
    def is_python(self):
        return self.module is not None


#: The three surfaces with a generated artifact.
#:
#: `openapi` is deliberately absent. It has no importable artifact: a JSON
#: document cannot hold a value by reference, and its check is a different one —
#: G4's rule that an open concept never becomes a closed `enum` array, which
#: #208 installs. Asking `serves(concept, "openapi")` therefore raises rather
#: than answering, because both a True and a False would be a lie.
SURFACES = {
    "backend": GeneratedSurface(BACKEND_CONSTANTS, "core.vocabulary",
                                django_choices),
    "console": GeneratedSurface(CONSOLE_VOCABULARY, None,
                                typescript_enumerations),
    "sdk": GeneratedSurface(SDK_CONSTANTS, "ubb.vocabulary",
                            literal_annotations),
}

#: Where the console declares the path aliases its imports use.
TSCONFIG = "tsconfig.json"


def serving_surfaces():
    """The surfaces the census can answer for. The gates iterate this rather
    than restating the three names, so a surface added to :data:`SURFACES` is
    walked on the day it is added."""
    return frozenset(SURFACES)


@dataclass(frozen=True)
class Finding:
    """One registry value a declared consumer does not hold by reference."""
    concept: str
    surface: str
    path: str
    value: str

    @property
    def site(self):
        """The identity a ledger entry records — the file and the concept.

        Per (path, concept) rather than per value, for G7's reason: an entry per
        value would be 130 rows that churn whenever a value moves, and an entry
        per file would let a concept's debt hide behind a neighbour's. The
        VALUE count rides the entry as its extent, so partial payment is
        recorded rather than invisible.
        """
        return f"{self.path}::{self.concept}"


@dataclass(frozen=True)
class Verdict:
    """One concept, on one surface: what its declared consumer holds.

    ``held`` and ``missing`` partition the registry's declared values for this
    concept. Nothing here is a set of the consumer's own values — the census
    never learns those, and a value the registry has never seen cannot appear in
    either field. That is G3's asymmetry, expressed as a data structure rather
    than as a rule somebody has to remember not to break.
    """
    concept: str
    kind: str
    surface: str
    path: str
    held: frozenset
    missing: tuple

    @property
    def serves(self):
        return not self.missing

    @property
    def site(self):
        return f"{self.path}::{self.concept}"


@dataclass(frozen=True)
class Census:
    """Every verdict, the faults that stopped some being taken, and the
    enumerations each consumer keeps of its own.

    ``enumerations`` is keyed by PATH, not by concept, and that is the whole
    honesty of it: the census can see that a file declares five value sets and
    cannot see which concept any of them is. See the module docstring.
    """
    verdicts: tuple
    faults: tuple
    #: Every consumer file actually read, for the vacuity guard. A census that
    #: resolved the wrong root would otherwise report a serene absence of
    #: findings over a tree it never opened.
    read: frozenset
    enumerations: dict

    def serves(self, concept, surface):
        """**The predicate.** Does ``surface``'s consumer hold every value of
        ``concept`` by reference?

        Raises for a surface the census cannot answer for, and for a concept it
        has no verdict on. Returning ``False`` in either case would be the
        answer a caller acts on, and both would be wrong: #208 must not read
        "the backend does not serve it" from "nobody asked".
        """
        if surface not in SURFACES:
            raise KeyError(
                f"{surface!r} has no generated artifact for a consumer to "
                f"import, so 'serves' has no answer for it — the surfaces with "
                f"one are {', '.join(sorted(SURFACES))}")
        verdicts = [v for v in self.verdicts
                    if v.concept == concept and v.surface == surface]
        if not verdicts:
            raise KeyError(
                f"the registry declares no {surface} consumer for {concept!r}, "
                f"or the concept declares no values — either way there is "
                f"nothing here to serve")
        return all(verdict.serves for verdict in verdicts)

    def findings(self, kinds):
        """Every unheld value on a concept of one of ``kinds``, sorted.

        The two gates differ only in what they pass here, which is what makes
        them two readings of one census rather than two checks.
        """
        return tuple(sorted(
            (Finding(v.concept, v.surface, v.path, value)
             for v in self.verdicts if v.kind in kinds for value in v.missing),
            key=lambda f: (f.surface, f.path, f.concept, f.value)))

    def extents(self, kinds):
        """``{site: (held, total)}`` for every consumer that owes something.

        The shape a ledger entry's `found` records, so paying part of a debt
        changes a number rather than nothing at all.
        """
        return {v.site: (len(v.held), len(v.held) + len(v.missing))
                for v in self.verdicts if v.kind in kinds and v.missing}


#: Path fragments that are not living first-party code, and why. Read by
#: :func:`declared_value_sets` only — the census proper walks the consumers the
#: registry names and needs no such list.
NOT_LIVING_CODE = {
    "/migrations/": "historical schema; slice 8's squash deletes the category",
    "/tests/": "a test is not a surface a value set ships on",
    "/conformance/": "the non-gating schemathesis probe (#87)",
    "/_core/": "the SDK's generated transport, regenerated from the contract",
    "/node_modules/": "vendored dependencies UBB does not author",
}


def declared_value_sets(repo_root, registry, surface):
    """``{path: (Restatement, ...)}`` — every enumeration ``surface`` declares.

    The census proper asks whether the consumers the registry NAMES hold their
    values by reference. This asks a different and coarser question: across a
    whole surface's living code, where is a value set declared at all?

    It exists because the two answers differ, and the difference is the honest
    limit of G2 and G3. A `choices=` list for a concept the registry describes
    nothing for is invisible to the census — not by oversight but because
    attributing it to a concept means comparing its members against a value
    set, which is the literal scan #191 decision 3 rules out. Counting them
    keeps that gap visible and stops it growing in silence, which is the same
    thing #191 story 15 asks of one field and `gates/README.md` asks of every
    bounded check: say what was left out.

    What it does NOT do is decide anything. Nothing here is a finding, and no
    caller may turn a count into one.
    """
    root = registry.surfaces[surface].root.rstrip("/") + "/"
    generated = {s.target.path for s in SURFACES.values()}
    read = SURFACES[surface].enumerations

    found = {}
    for relative in _tracked(repo_root):
        if not relative.startswith(root) or relative in generated:
            continue
        if any(part in "/" + relative for part in NOT_LIVING_CODE):
            continue
        name = relative.rsplit("/", 1)[-1]
        if name.startswith("test_") or ".test." in name or name == "conftest.py":
            continue
        try:
            text = (repo_root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if items := read(text):
            found[relative] = items
    return found


def _tracked(repo_root):
    """The tree according to git.

    A raw listing rather than a directory walk, for the reason
    `tools/forbidden_terms` gives: an untracked scratch file is not a surface,
    and a `.gitignore`d directory is not one either.
    """
    listed = subprocess.run(["git", "-C", str(repo_root), "ls-files", "-z"],
                            capture_output=True, text=True, check=True)
    return tuple(sorted(p for p in listed.stdout.split("\0") if p))


def take_census(repo_root, registry):
    """Walk every declared consumer on every generated surface."""
    repo_root = Path(repo_root)
    verdicts, faults, read, enumerations = [], [], set(), {}

    alias_roots, alias_faults = _console_aliases(repo_root, registry)
    faults += list(alias_faults)

    for _, concept in sorted(registry.concepts.items()):
        if not concept.declared_values:
            # `tenant_defined` and `free_text` declare no values, so there is
            # nothing a consumer could hold by reference. Skipped rather than
            # reported: map #137 constraint 5 is why they enumerate nothing.
            continue
        for consumer in concept.consumers:
            if consumer.surface not in SURFACES:
                continue
            verdict, entry_faults, text = _verdict(
                repo_root, registry, concept, consumer, alias_roots)
            faults += list(entry_faults)
            if verdict is not None:
                verdicts.append(verdict)
                read.add(consumer.path)
                if consumer.path not in enumerations:
                    enumerations[consumer.path] = \
                        SURFACES[consumer.surface].enumerations(text)

    faults += list(_missing_artifacts(repo_root))
    return Census(tuple(verdicts), tuple(sorted(faults)), frozenset(read),
                  enumerations)


# ---------------------------------------------------------------------------
# One consumer
# ---------------------------------------------------------------------------

def _verdict(repo_root, registry, concept, consumer, alias_roots):
    """``(verdict or None, faults, the consumer's source or "")``."""
    surface = SURFACES[consumer.surface]
    location = f"{consumer.surface}::{consumer.path}::{concept.name}"
    path = repo_root / consumer.path

    if not path.is_file():
        return None, (CensusError(
            codes.CONSUMER_MISSING, location,
            "the registry declares this consumer and the file is not in the "
            "tree, so nothing here can be checked"),), ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, (CensusError(
            codes.CONSUMER_UNREADABLE, location,
            f"could not be read as UTF-8, so a reference in it would be "
            f"invisible: {exc}"),), ""

    if surface.is_python:
        names, faults = python_references(text, surface.module, location)
    else:
        specifiers = console_specifiers(consumer.path, surface.target.path,
                                        alias_roots)
        names, faults = typescript_references(text, specifiers, location)

    held = _held(surface.target, concept, names)
    missing = tuple(v for v in concept.declared_values if v not in held)
    return Verdict(
        concept=concept.name, kind=concept.kind, surface=consumer.surface,
        path=consumer.path, held=frozenset(held), missing=missing,
    ), faults, text


def _held(target, concept, names):
    """The concept's values this set of referenced names carries.

    `handles` comes from the target — the generator itself — so this file is
    not a second implementation of the naming rule, which would go on agreeing
    with the artifacts right up until one of them changed. Which names carry
    all the values, which carry one, and which carry none is entirely the
    target's business; see `generate._Target.handles`.
    """
    held = set()
    for name, values in target.handles(concept).items():
        if name in names:
            held |= values
    return held


def _console_aliases(repo_root, registry):
    surface = registry.surfaces.get("console")
    if surface is None:
        return {}, ()
    relative = f"{surface.root}/{TSCONFIG}"
    path = repo_root / relative
    if not path.is_file():
        return {}, (CensusError(
            codes.ALIAS_UNRESOLVED, relative,
            "is not in the tree, so the console's aliased imports of the "
            "generated artifact would be invisible to the census"),)
    paths, faults = console_alias_roots(path.read_text(encoding="utf-8"),
                                        relative)
    return resolve_alias_roots(paths, surface.root), faults


def _missing_artifacts(repo_root):
    """A surface whose generated artifact is absent.

    Not the same fault as a consumer that imports nothing, and reported
    separately for that reason: if the artifact is gone, every consumer on that
    surface is correctly unable to import it, and reporting them one by one
    would bury the one cause under its consequences.
    """
    for name, surface in sorted(SURFACES.items()):
        if not (repo_root / surface.target.path).is_file():
            yield CensusError(
                codes.ARTIFACT_MISSING, f"{name}::{surface.target.path}",
                "the generated artifact this surface's consumers import is "
                "not in the tree")
