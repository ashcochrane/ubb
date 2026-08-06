"""The console's label catalogue, read and held to the registry (#210).

ADR-0008 §4 draws one line: **the registry owns identity, the localisation layer
owns expression.** The registry generates value sets and stable label keys; the
console attaches the English. This module is the check that the two halves meet
exactly — in both directions, which is what §4 asks for and what a one-way
"every value has a label" check would leave half done.

    from tools.labels import read_catalogue, required_keys, coverage_faults
    catalogue, faults = read_catalogue(repo_root)
    findings = coverage_faults(required_keys(registry), catalogue, registry)

**The required keys are asked of the generator, never rebuilt beside it.**
``ConsoleVocabulary.label_key`` is the one place `<prefix>.<value>` is spelled,
and a second spelling here would be exactly the shape ADR-0006 §4 warns about:
two encodings of one fact, where the wrong one is always the one nobody is
looking at. #203's agreement test was wrong until it was run, for that reason.

**The catalogue is JSON rather than TypeScript, deliberately.** This suite is
Django-free and Node-free by design (`tests/contracts/pytest.ini`), so a gate
whose subject were a `.ts` module would have to parse TypeScript from Python to
read a value — a fragile oracle for the one artifact that must never drift.
#158 §4.1 already writes the catalogue as JSON in its worked example. The
console imports it directly; Vite and `resolveJsonModule` make that ordinary.

**Which locales are supported is read from the console's own index module**,
not from whatever files happen to sit in the directory. A catalogue file nobody
imports is dead weight that would satisfy "every supported locale carries the
key" while shipping to no user, and an import with no file is a build break the
gate should name rather than leave to `tsc`. Both directions are faults here.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from tools.labels import errors as codes
from tools.labels.errors import LabelError
from tools.vocabulary.generate import CONSOLE_VOCABULARY

#: Where the console keeps its catalogues, and the module that declares which
#: of them ship. Repository-relative, so a move shows up as a fault rather than
#: as an empty walk.
LOCALES_DIR = "apps/ui/src/locales"
INDEX_FILE = "index.ts"

#: The locale every other one is measured against. Its absence is a fault
#: rather than a finding: with no default there is nothing to render at all,
#: and every comparison below would pass over an empty catalogue.
DEFAULT_LOCALE = "en"

#: `import en from "./en.json";` — the one shape the index may declare a locale
#: in. Anchored to the start of a line so a mention inside a comment or a
#: string cannot register a locale that does not ship.
_IMPORT = re.compile(r'^import\s+(\w+)\s+from\s+"\./([A-Za-z0-9_-]+)\.json";',
                     re.MULTILINE)


@dataclass(frozen=True)
class Locale:
    """One shipped catalogue: `{label key: the words}`."""
    name: str
    path: str
    entries: dict

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class Catalogue:
    """Every locale the console declares, in declaration order."""
    locales: tuple

    def __bool__(self):
        return bool(self.locales)

    @property
    def keys(self):
        """Every key any locale carries.

        The union rather than the default locale's keys, so a key that exists
        only in a translation is still held to the registry. A key naming
        nothing is a defect wherever it is written.
        """
        return {key for locale in self.locales for key in locale.entries}

    def locale(self, name):
        for locale in self.locales:
            if locale.name == name:
                return locale
        return None


def read_catalogue(repo_root):
    """``(Catalogue, faults)`` — the shipped catalogues, or why they cannot be read.

    Faults are collected rather than raised at the first one: a catalogue with
    two problems should take one run to fix. A fault never means "no findings" —
    the caller must report faults and findings separately, because a walk that
    did not happen and a walk that found nothing are the opposite verdicts.
    """
    faults = []
    directory = Path(repo_root) / LOCALES_DIR
    if not directory.is_dir():
        return Catalogue(()), [LabelError(
            codes.LOCALES_MISSING, LOCALES_DIR,
            "the console's locales directory is not in the tree, so nothing "
            "attaches English to the registry's label keys")]

    index = directory / INDEX_FILE
    if not index.is_file():
        return Catalogue(()), [LabelError(
            codes.INDEX_MISSING, f"{LOCALES_DIR}/{INDEX_FILE}",
            "the module that declares which locales ship is absent, so "
            "`every supported locale carries the key` has no subject")]

    declared = [name for _, name in _IMPORT.findall(
        index.read_text(encoding="utf-8"))]
    present = sorted(path.stem for path in directory.glob("*.json"))

    for name in sorted(set(present) - set(declared)):
        faults.append(LabelError(
            codes.LOCALE_UNDECLARED, f"{LOCALES_DIR}/{name}.json",
            f"`{name}.json` is in the tree but {INDEX_FILE} imports no such "
            f"locale, so it ships to nobody while passing every check below"))

    locales = []
    for name in declared:
        path = directory / f"{name}.json"
        location = f"{LOCALES_DIR}/{name}.json"
        if not path.is_file():
            faults.append(LabelError(
                codes.LOCALE_MISSING, location,
                f"{INDEX_FILE} declares the `{name}` locale, and there is no "
                f"such catalogue"))
            continue
        entries, fault = _read_locale(name, path, location)
        if fault is not None:
            faults.append(fault)
            continue
        locales.append(Locale(name, location, entries))

    if not any(locale.name == DEFAULT_LOCALE for locale in locales):
        faults.append(LabelError(
            codes.DEFAULT_LOCALE_MISSING, LOCALES_DIR,
            f"no `{DEFAULT_LOCALE}` catalogue loaded, so there is no locale "
            f"every other one can be measured against"))

    return Catalogue(tuple(locales)), faults


def _read_locale(name, path, location):
    """``(entries, fault)`` for one catalogue file."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"),
                             object_pairs_hook=_no_duplicate_keys)
    except _DuplicateKey as duplicate:
        return None, LabelError(
            codes.LOCALE_MALFORMED, location,
            f"`{duplicate.key}` is written twice. JSON keeps the last silently, "
            f"so one of the two wordings ships and neither author knows which")
    except (json.JSONDecodeError, UnicodeDecodeError) as problem:
        return None, LabelError(codes.LOCALE_UNPARSEABLE, location, str(problem))

    if not isinstance(entries, dict):
        return None, LabelError(
            codes.LOCALE_MALFORMED, location,
            f"the `{name}` catalogue is a {type(entries).__name__}, not an "
            f"object of `label key -> words`")
    wrong = sorted(key for key, words in entries.items()
                   if not isinstance(words, str))
    if wrong:
        return None, LabelError(
            codes.LOCALE_MALFORMED, location,
            f"these keys do not carry a string: {', '.join(wrong)}")
    return entries, None


class _DuplicateKey(Exception):
    def __init__(self, key):
        super().__init__(key)
        self.key = key


def _no_duplicate_keys(pairs):
    """`json.loads` hook that refuses a repeated key rather than keeping the last.

    The same default `tools/vocabulary/loader.py` refuses in YAML, for the same
    reason: a catalogue whose whole point is one wording per key must not have
    a second wording win in silence.
    """
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKey(key)
        seen[key] = value
    return seen


def required_keys(registry):
    """``{label key: (concept name, value)}`` — every key the console must carry.

    Driven by :attr:`Concept.declared_values`, which is the kind distinction
    expressed as data: a `closed` concept's whole set, an `open` concept's
    known values, and nothing at all for `tenant_defined` and `free_text`. The
    last is map #137 constraint 5 — UBB never enumerates what the tenant owns,
    so it has no wording to supply either.
    """
    required = {}
    for name, concept in sorted(registry.concepts.items()):
        if not concept.label_key_prefix:
            continue
        for value in concept.declared_values:
            required[CONSOLE_VOCABULARY.label_key(concept, value)] = (name, value)
    return required


def retired_tokens(registry):
    """``{retired token: the concept that retired it}``.

    ADR-0008 §4's third promise — *no retired token remains labelled* — is
    stated over the registry's own `retired_aliases`, which is the same input
    the forbidden-term sweep consumes (#206). `retired_senses` is deliberately
    not input, for the reason G7's row gives: eight words are retired in one
    sense while live in another, and ADR-0008 §1 keeps that human-judged.
    """
    return {token: name
            for name, concept in sorted(registry.concepts.items())
            for token in concept.retired_aliases}


def split_key(key):
    """``(prefix, value)`` for a label key, or ``None`` if it is not one.

    The inverse of ``ConsoleVocabulary.label_key``, which joins a single-token
    prefix to a value that may itself contain dots. Splitting on the FIRST dot
    is therefore exact rather than a guess — the docstring there calls the key
    "losslessly reversible", and this is where that is spent.
    """
    prefix, dot, value = key.partition(".")
    return (prefix, value) if dot and value else None


def coverage_faults(required, catalogue, registry):
    """Every way the registry and the catalogue fail to say the same thing.

    A real predicate rather than four inline comparisons, so the controls can
    push synthetic pairs through the function the gate actually calls. Returns
    findings, in ADR-0008 §4's order:

    1. every required registry value has a label — in **every** locale, not
       just the default one;
    2. every console label refers to a valid registry value;
    3. no retired token remains labelled;
    4. a key whose wording is blank is none of the above and is still a defect —
       a value must never reach a tenant as an empty string (#155 §9.2).
    """
    findings = []
    retired = retired_tokens(registry)

    for locale in catalogue.locales:
        for key in sorted(set(required) - set(locale.entries)):
            concept, value = required[key]
            findings.append(LabelError(
                codes.UNLABELLED_VALUE, f"{locale.path}: {key}",
                f"{concept}.{value} has no wording in `{locale}`. A missing "
                f"label fails here rather than being humanised at runtime "
                f"(ADR-0008 §4.3)"))
        for key in sorted(key for key, words in locale.entries.items()
                          if not words.strip()):
            findings.append(LabelError(
                codes.BLANK_LABEL, f"{locale.path}: {key}",
                "the wording is blank, which renders as nothing at all"))

    for key in sorted(catalogue.keys - set(required)):
        where = _where(catalogue, key)
        parts = split_key(key)
        if parts and parts[1] in retired:
            findings.append(LabelError(
                codes.RETIRED_KEY, f"{where}: {key}",
                f"`{parts[1]}` is retired by `{retired[parts[1]]}`. A retired "
                f"token that keeps its wording keeps its life"))
        elif parts and parts[0] in retired:
            findings.append(LabelError(
                codes.RETIRED_KEY, f"{where}: {key}",
                f"the `{parts[0]}` prefix is retired by "
                f"`{retired[parts[0]]}`"))
        else:
            findings.append(LabelError(
                codes.UNKNOWN_KEY, f"{where}: {key}",
                "no concept in the registry declares this value, so nothing "
                "renders through this key"))

    return findings


def retired_labels(catalogue, registry):
    """The retired tokens the catalogue still carries wording for.

    Stated over the catalogue's own keys rather than derived from
    :func:`coverage_faults`'s equality, so ADR-0008 §4's third promise stands on
    its own evidence. It is *implied* by the first two today — a retired token
    is not a registry value, so it is already an unknown key — but that is a
    property of the current registry, not of the rule. Narrowing the equality
    later must not silently drop this.
    """
    retired = retired_tokens(registry)
    found = []
    for key in sorted(catalogue.keys):
        parts = split_key(key)
        if not parts:
            continue
        for token in parts:
            if token in retired:
                found.append((key, token, retired[token]))
                break
    return found


def _where(catalogue, key):
    """The locales carrying a key, for a finding's location."""
    return ", ".join(locale.path for locale in catalogue.locales
                     if key in locale.entries) or LOCALES_DIR
