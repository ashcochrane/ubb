"""Read `domain-vocabulary/` and say, by name, why it is invalid.

This is the one implementation of the registry's semantics. It is deliberately
Django-free, database-free and settings-free, so the platform, the SDK and the
console tooling all read the same rules instead of growing three near-identical
parsers that agree until the day they do not.

The compiler's contract is narrow and total:

- :func:`load_registry` returns a :class:`Registry`, or raises
  :class:`~tools.vocabulary.errors.RegistryInvalid` carrying **every** reason it
  failed — each one a named code from ``errors.py``, not a sentence.
- It never repairs, defaults or normalises a registry into validity. A registry
  that loads is a registry that was written correctly.

What it does NOT check is whether the declarations are *right*. Consistency with
a wrong declaration is still consistency; that question belongs to the one owned
acceptance audit (ADR-0008 §1).
"""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from . import errors as E
from .errors import RegistryError, RegistryInvalid
from .loader import DuplicateKey, load_yaml

SCHEMA_FILE = "schema.yaml"
CONSUMERS_FILE = "consumers.yaml"
CONCEPTS_DIR = "concepts"


# ---------------------------------------------------------------------------
# The compiled model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KindRule:
    """One row of the schema's kind table."""
    name: str
    summary: str
    requires: frozenset
    forbids: frozenset


@dataclass(frozen=True)
class Schema:
    version: int
    token_pattern: str
    required_fields: tuple
    optional_fields: tuple
    kinds: dict


@dataclass(frozen=True)
class Surface:
    """A place a canonical value appears, and the subtree it lives in.

    ``root_exists`` is false when the declared root is not in the repository.
    The surface is still registered, so a concept naming it is not told the
    surface is undeclared — which would be a false statement — and its consumer
    paths are not re-reported one by one. One cause, one error.
    """
    name: str
    summary: str
    root: str
    root_exists: bool = True


@dataclass(frozen=True)
class Consumer:
    surface: str
    path: str


@dataclass(frozen=True)
class Concept:
    name: str
    kind: str
    summary: str
    source: str
    values: tuple = ()
    known_values: tuple = ()
    allow_unknown: bool = False
    label_key_prefix: str | None = None
    consumers: tuple = ()
    retired_aliases: tuple = ()

    @property
    def declared_values(self):
        """Every value UBB itself authored — a closed set, or an open one's
        known values. Empty for ``tenant_defined`` and ``free_text``, which is
        the whole point of those kinds."""
        return self.values or self.known_values


@dataclass(frozen=True)
class Registry:
    root: Path
    repo_root: Path
    schema: Schema
    surfaces: dict
    concepts: dict
    files: tuple

    def of_kind(self, kind):
        return tuple(c for c in self.concepts.values() if c.kind == kind)

    @property
    def concepts_without_consumers(self):
        """Legal, and reported by name.

        A concept nobody consumes yet is not an error — the registry is
        normative before the code catches up. But an *unreported* one would be
        silently exempt from every consumer check, so the compiler names them
        and the CLI prints them.
        """
        return tuple(sorted(n for n, c in self.concepts.items() if not c.consumers))

    @property
    def retired_terms(self):
        """``{retired term: the concept that retired it}`` — the declared input
        the forbidden-term sweep consumes instead of a list kept by memory."""
        return {
            alias: concept.name
            for concept in self.concepts.values()
            for alias in concept.retired_aliases
        }

    def describe(self):
        """Human-readable report lines. Shared by the CLI and its test, so what
        a reader sees is what the test asserts on."""
        by_kind = {}
        for concept in self.concepts.values():
            by_kind.setdefault(concept.kind, []).append(concept.name)
        lines = [
            f"registry: {self.root}",
            f"files: {len(self.files)} ({', '.join(self.files)})",
            f"concepts: {len(self.concepts)}",
        ]
        for kind in sorted(by_kind):
            lines.append(f"  {kind}: {len(by_kind[kind])} "
                         f"({', '.join(sorted(by_kind[kind]))})")
        lines.append(f"surfaces: {', '.join(sorted(self.surfaces))}")
        lines.append(f"retired terms: {len(self.retired_terms)}")
        without = self.concepts_without_consumers
        lines.append(f"concepts with no declared consumer: {len(without)}"
                     + (f" ({', '.join(without)})" if without else ""))
        return lines


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class _Errors:
    """Accumulator — the compiler reports every fault in one pass."""

    def __init__(self):
        self.items = []

    def add(self, code, location, message):
        self.items.append(RegistryError(code, location, message))

    def __bool__(self):
        return bool(self.items)


#: Returned by :func:`_read` when a file could not be parsed at all — distinct
#: from a file that parsed to ``None``, which is an EMPTY file and a different
#: fault. Collapsing the two is how an empty registry file gets skipped in
#: silence instead of reported.
_UNREADABLE = object()


def _read(path, location, errors):
    """Parse one YAML file, or record why it could not be parsed."""
    try:
        return load_yaml(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        # The registry is UTF-8. A file that is not decodes to nothing useful,
        # and must fail with a code like every other fault rather than as a
        # traceback out of the compiler.
        errors.add(E.YAML_INVALID, location, f"is not valid UTF-8: {exc}")
        return _UNREADABLE
    except DuplicateKey as exc:
        errors.add(E.DUPLICATE_KEY, f"{location}:{exc.line}",
                   f"{exc.key!r} is defined twice in this file — a term is "
                   f"defined exactly once, and YAML would otherwise keep the "
                   f"last one silently")
        return _UNREADABLE
    except yaml.YAMLError as exc:
        errors.add(E.YAML_INVALID, location, str(exc).replace("\n", " "))
        return _UNREADABLE


def load_registry(registry_dir, repo_root=None):
    """Load and validate a registry directory.

    ``repo_root`` is what declared consumer paths resolve against; it defaults
    to the registry's parent, which for the checked-in ``domain-vocabulary/`` is
    the git root. Tests point both at a temporary directory.
    """
    registry_dir = Path(registry_dir)
    repo_root = Path(repo_root) if repo_root is not None else registry_dir.parent
    errors = _Errors()

    # Structure first, and fatally: without a schema there is nothing to check
    # a concept against, so continuing would report a cascade of consequences
    # instead of the cause.
    if not (registry_dir / SCHEMA_FILE).is_file():
        errors.add(E.REGISTRY_MISSING, str(registry_dir),
                   f"{SCHEMA_FILE} is missing from the registry directory")
    if not (registry_dir / CONSUMERS_FILE).is_file():
        errors.add(E.REGISTRY_MISSING, str(registry_dir),
                   f"{CONSUMERS_FILE} is missing from the registry directory")
    if not (registry_dir / CONCEPTS_DIR).is_dir():
        errors.add(E.REGISTRY_MISSING, str(registry_dir),
                   f"{CONCEPTS_DIR}/ is missing from the registry directory, or "
                   f"is not a directory")
    if errors:
        raise RegistryInvalid(errors.items)

    schema = _load_schema(registry_dir / SCHEMA_FILE, errors)
    if schema is None:
        raise RegistryInvalid(errors.items)

    surfaces = _load_surfaces(registry_dir / CONSUMERS_FILE, repo_root, errors)
    if surfaces is None:
        # No usable surface table means every declared consumer would be
        # reported as naming an undeclared surface. Blame the cause, once.
        raise RegistryInvalid(errors.items)

    _check_for_unread_files(registry_dir, errors)
    concept_paths = _concept_paths(registry_dir, errors)
    if not concept_paths:
        errors.add(E.REGISTRY_EMPTY, f"{registry_dir}/{CONCEPTS_DIR}",
                   "no domain files — a registry with nothing in it would pass "
                   "every consumer check vacuously")

    concepts = {}
    seen_raw = {}
    files = []
    for path in concept_paths:
        source = f"{CONCEPTS_DIR}/{path.name}"
        files.append(path.name)
        document = _read(path, source, errors)
        if document is _UNREADABLE:
            continue
        if not isinstance(document, dict):
            errors.add(E.FILE_NOT_MAPPING, source,
                       "a domain file is a mapping of concept name to concept"
                       + (" — this one is empty" if document is None else ""))
            continue
        for name, body in document.items():
            first = seen_raw.get(name)
            if first is not None:
                first_source, first_body = first
                if first_body == body:
                    errors.add(E.DUPLICATE_TERM, f"{source}:{name}",
                               f"already defined in {first_source} — one term, "
                               f"one definition, one place")
                else:
                    errors.add(E.CONFLICTING_DEFINITION, f"{source}:{name}",
                               f"defined differently in {first_source} — two "
                               f"definitions of one term means the registry is "
                               f"not an oracle")
                continue
            seen_raw[name] = (source, body)
            concept = _build_concept(name, body, source, schema, surfaces,
                                     repo_root, errors)
            if concept is not None:
                concepts[name] = concept

    _check_retired_aliases(concepts, errors)

    if errors:
        raise RegistryInvalid(errors.items)

    return Registry(
        root=registry_dir,
        repo_root=repo_root,
        schema=schema,
        surfaces=surfaces,
        concepts=concepts,
        files=tuple(files),
    )


# ---------------------------------------------------------------------------
# Directory contents: everything in the registry is read, or named
# ---------------------------------------------------------------------------
#
# A file nobody reads is the failure mode this repository has already shipped:
# `.gitignore`'s unanchored `lib/` silently dropped twenty-two modules for
# weeks and a clean checkout could not build. So the registry has no "ignored"
# category. Every entry at either level is loaded or is a named error.

#: What may sit beside the concepts directory. `README.md` is documentation for
#: humans, not registry content, and is the one thing here the compiler skips.
_REGISTRY_ROOT_ENTRIES = frozenset({SCHEMA_FILE, CONSUMERS_FILE, CONCEPTS_DIR,
                                    "README.md"})


def _check_for_unread_files(registry_dir, errors):
    """Refuse anything at the registry root the compiler would not read."""
    for entry in sorted(registry_dir.iterdir()):
        if entry.name in _REGISTRY_ROOT_ENTRIES:
            continue
        errors.add(E.UNEXPECTED_FILE, entry.name,
                   f"the compiler does not read this — domain files live in "
                   f"{CONCEPTS_DIR}/, and a vocabulary file nothing reads is a "
                   f"vocabulary that silently is not enforced")


def _concept_paths(registry_dir, errors):
    """The domain files, with anything else in `concepts/` named as an error.

    Globbing `*.yaml` alone would let a `webhooks.yml` sit in the directory
    contributing nothing, with CI green.
    """
    paths = []
    for entry in sorted((registry_dir / CONCEPTS_DIR).iterdir()):
        if entry.is_file() and entry.suffix == ".yaml":
            paths.append(entry)
        else:
            errors.add(E.UNEXPECTED_FILE, f"{CONCEPTS_DIR}/{entry.name}",
                       "only .yaml domain files live here — anything else is "
                       "content the registry silently would not carry")
    return paths


# ---------------------------------------------------------------------------
# The schema
# ---------------------------------------------------------------------------

def _load_schema(path, errors):
    """Build the :class:`Schema`, or record why ``schema.yaml`` is unusable.

    The compiler does not know what kinds exist — the schema declares them. That
    is deliberate: hard-coding the four kinds here would make ``schema.yaml``
    documentation that CI does not read, which is exactly the shape of thing
    this whole slice exists to abolish. What pins the four kinds to ADR-0008 §2
    is a contract test over the real registry, not this loader.
    """
    document = _read(path, SCHEMA_FILE, errors)
    if document is _UNREADABLE:
        return None
    before = len(errors.items)

    def bad(message):
        errors.add(E.SCHEMA_INVALID, SCHEMA_FILE, message)

    if not isinstance(document, dict):
        bad("the schema is a mapping"
            + (" — this one is empty" if document is None else ""))
        return None

    version = document.get("version")
    # `isinstance(True, int)` is true in Python, so `version: true` would pass a
    # bare int check and compile into a schema versioned `True`.
    if not isinstance(version, int) or isinstance(version, bool):
        bad("`version` is a required integer")

    pattern = document.get("token_pattern")
    if not isinstance(pattern, str) or not _compiles(pattern):
        bad("`token_pattern` is a required regular expression")
        return None

    fields = document.get("concept_fields")
    if not isinstance(fields, dict):
        bad("`concept_fields` is a required mapping of required/optional")
        return None
    required = fields.get("required")
    optional = fields.get("optional", [])
    if not _is_str_list(required) or not required:
        bad("`concept_fields.required` is a required non-empty list of names")
        return None
    if not _is_str_list(optional):
        bad("`concept_fields.optional` is a list of names")
        return None

    raw_kinds = document.get("kinds")
    if not isinstance(raw_kinds, dict) or not raw_kinds:
        bad("`kinds` is a required non-empty mapping")
        return None

    kinds = {}
    for name, rule in raw_kinds.items():
        if not isinstance(rule, dict):
            bad(f"kind {name!r} is a mapping")
            continue
        summary = rule.get("summary")
        requires = rule.get("requires", [])
        forbids = rule.get("forbids", [])
        if not isinstance(summary, str) or not summary.strip():
            bad(f"kind {name!r} needs a `summary` saying what it obliges a "
                f"consumer to do")
        if not _is_str_list(requires) or not _is_str_list(forbids):
            bad(f"kind {name!r}: `requires` and `forbids` are lists of names")
            continue
        overlap = set(requires) & set(forbids)
        if overlap:
            bad(f"kind {name!r} both requires and forbids "
                f"{', '.join(sorted(overlap))}")
            continue
        kinds[name] = KindRule(name, summary or "", frozenset(requires),
                               frozenset(forbids))

    if len(errors.items) > before:
        return None

    return Schema(
        version=version,
        token_pattern=pattern,
        required_fields=tuple(required),
        optional_fields=tuple(optional),
        kinds=kinds,
    )


# ---------------------------------------------------------------------------
# Consumer surfaces
# ---------------------------------------------------------------------------

def _load_surfaces(path, repo_root, errors):
    """Build the surface table from ``consumers.yaml``, or ``None`` if the file
    is unusable — which is fatal, because with no surface table every declared
    consumer in the registry would be blamed for naming an undeclared one.

    A surface whose root has vanished is reported here, once, rather than as a
    consumer failure on every concept that names it.
    """
    document = _read(path, CONSUMERS_FILE, errors)
    if document is _UNREADABLE:
        return None
    if not isinstance(document, dict) or not isinstance(document.get("surfaces"), dict):
        errors.add(E.CONSUMERS_INVALID, CONSUMERS_FILE,
                   "`surfaces` is a required mapping of surface name to "
                   "{summary, root}")
        return None

    surfaces = {}
    for name, body in document["surfaces"].items():
        location = f"{CONSUMERS_FILE}:{name}"
        if not isinstance(body, dict):
            errors.add(E.CONSUMERS_INVALID, location, "a surface is a mapping")
            continue
        summary, root = body.get("summary"), body.get("root")
        if not isinstance(summary, str) or not summary.strip():
            errors.add(E.CONSUMERS_INVALID, location, "`summary` is required")
        if not isinstance(root, str) or not root.strip():
            errors.add(E.CONSUMERS_INVALID, location,
                       "`root` is a required path relative to the repository root")
            continue
        root_exists = (repo_root / root).is_dir() or (repo_root / root).is_file()
        if not root_exists:
            errors.add(E.SURFACE_ROOT_MISSING, location,
                       f"root {root!r} does not exist — a surface that resolves "
                       f"to nothing exempts every concept naming it")
        surfaces[name] = Surface(name, summary or "", root, root_exists)
    return surfaces


# ---------------------------------------------------------------------------
# Concepts
# ---------------------------------------------------------------------------

def _build_concept(name, body, source, schema, surfaces, repo_root, errors):
    location = f"{source}:{name}"

    def add(code, message):
        errors.add(code, location, message)

    if not isinstance(body, dict):
        add(E.CONCEPT_NOT_MAPPING, "a concept is a mapping of field to value")
        return None

    # A concept NAME always uses the registry-wide pattern. Only its values may
    # override it — a webhook event name carries a dot, the concept naming that
    # catalogue does not.
    if not re.fullmatch(schema.token_pattern, name):
        add(E.INVALID_TOKEN,
            f"concept name {name!r} does not match {schema.token_pattern}")

    kind = body.get("kind")
    rule = schema.kinds.get(kind) if isinstance(kind, str) else None
    if rule is None:
        add(E.UNKNOWN_KIND,
            f"kind {kind!r} is not one of: {', '.join(sorted(schema.kinds))}")
        return None

    # Shape: what this kind requires, what it forbids, and what the schema has
    # never heard of (which is how `value:` for `values:` gets caught rather
    # than silently producing a concept with no value set).
    allowed = set(schema.required_fields) | set(schema.optional_fields) | rule.requires
    for required in sorted(set(schema.required_fields) | rule.requires):
        if required not in body:
            add(E.MISSING_FIELD, f"kind {kind!r} requires `{required}`")
    for present in body:
        if present in rule.forbids:
            add(E.FORBIDDEN_FIELD,
                f"kind {kind!r} forbids `{present}` — {rule.summary.strip()}")
        elif present not in allowed:
            add(E.UNKNOWN_FIELD, f"`{present}` is declared nowhere in the schema")

    summary = body.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        add(E.INVALID_FIELD_TYPE, "`summary` is a non-empty sentence saying "
                                  "what the concept means")

    # Per-concept token pattern override, for value sets that legitimately
    # carry more structure than a bare token.
    value_pattern = schema.token_pattern
    if "token_pattern" in body:
        override = body["token_pattern"]
        if not isinstance(override, str) or not _compiles(override):
            add(E.INVALID_TOKEN_PATTERN,
                f"`token_pattern` {override!r} is not a regular expression")
        else:
            value_pattern = override

    values = _value_list(body, "values", value_pattern, add)
    known_values = _value_list(body, "known_values", value_pattern, add)

    allow_unknown = body.get("allow_unknown", False)
    if "allow_unknown" in body and not isinstance(allow_unknown, bool):
        add(E.INVALID_FIELD_TYPE, "`allow_unknown` is a boolean")
        allow_unknown = False
    if kind == "open" and allow_unknown is not True:
        add(E.OPEN_MUST_ALLOW_UNKNOWN,
            "an `open` concept accepts values UBB has not seen, so "
            "`allow_unknown` must be true — if it is not, the concept is "
            "`closed`")

    label_key_prefix = body.get("label_key_prefix")
    if "label_key_prefix" in body:
        if (not isinstance(label_key_prefix, str)
                or not re.fullmatch(schema.token_pattern, label_key_prefix)):
            add(E.INVALID_TOKEN,
                f"label_key_prefix {label_key_prefix!r} does not match "
                f"{schema.token_pattern}")
            label_key_prefix = None

    # Collisions between a retired alias and a live value are checked once,
    # across the whole registry, by _check_retired_aliases — a term retired in
    # one concept and live in another is the same fault as one retired and live
    # in the same concept, and the sweep cannot tell them apart either.
    retired = _value_list(body, "retired_aliases", value_pattern, add,
                          allow_empty=True)

    consumers = _consumers(body.get("consumers"), surfaces, repo_root, add)

    return Concept(
        name=name,
        kind=kind,
        summary=summary if isinstance(summary, str) else "",
        source=source,
        values=values,
        known_values=known_values,
        allow_unknown=bool(allow_unknown),
        label_key_prefix=label_key_prefix,
        consumers=consumers,
        retired_aliases=retired,
    )


def _value_list(body, field, pattern, add, allow_empty=False):
    """Read a list-of-tokens field, reporting each way it can be wrong."""
    if field not in body:
        return ()
    raw = body[field]
    if not _is_str_list(raw):
        add(E.INVALID_FIELD_TYPE, f"`{field}` is a list of tokens")
        return ()
    if not raw and not allow_empty:
        add(E.EMPTY_VALUE_SET,
            f"`{field}` is empty — a concept UBB declares no values for is "
            f"`tenant_defined` or `free_text`, not an empty value set")
    seen = set()
    for value in raw:
        if not re.fullmatch(pattern, value):
            add(E.INVALID_TOKEN, f"`{field}` value {value!r} does not match {pattern}")
        if value in seen:
            add(E.DUPLICATE_VALUE, f"`{field}` lists {value!r} twice")
        seen.add(value)
    return tuple(raw)


def _consumers(raw, surfaces, repo_root, add):
    """Resolve the declared consumers, or say which one does not resolve."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        add(E.INVALID_FIELD_TYPE,
            "`consumers` is a list of {surface, path} — empty is legal and "
            "means nothing consumes this concept yet")
        return ()

    resolved = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"surface", "path"}:
            add(E.CONSUMER_NOT_MAPPING,
                f"consumer {entry!r} is a mapping of exactly surface and path")
            continue
        surface_name, path = entry["surface"], entry["path"]
        if not isinstance(path, str) or not path.strip():
            add(E.CONSUMER_NOT_MAPPING, f"consumer {entry!r} needs a path")
            continue
        surface = surfaces.get(surface_name)
        if surface is None:
            add(E.UNKNOWN_CONSUMER_SURFACE,
                f"consumer surface {surface_name!r} is not declared in "
                f"{CONSUMERS_FILE} (declared: {', '.join(sorted(surfaces))})")
            continue
        posix = PurePosixPath(path)
        if posix.is_absolute() or ".." in posix.parts or "\\" in path:
            add(E.CONSUMER_PATH_OUTSIDE_SURFACE,
                f"consumer path {path!r} is a relative POSIX path inside "
                f"{surface.root!r}")
            continue
        if not posix.is_relative_to(PurePosixPath(surface.root)):
            add(E.CONSUMER_PATH_OUTSIDE_SURFACE,
                f"consumer path {path!r} is outside surface {surface_name!r} "
                f"(root {surface.root!r})")
            continue
        if not surface.root_exists:
            # The surface's root is already reported against the surface. Saying
            # so again for every path under it buries the one cause in its own
            # consequences.
            continue
        if not (repo_root / posix).exists():
            add(E.CONSUMER_PATH_MISSING,
                f"consumer path {path!r} does not exist — a consumer that "
                f"resolves to nothing is a consumer nothing can be checked "
                f"against")
            continue
        resolved.append(Consumer(surface_name, path))
    return tuple(resolved)


def _check_retired_aliases(concepts, errors):
    """A retired term must be retired everywhere, and retired exactly once.

    The forbidden-term sweep works over text, so it cannot forbid a word in one
    file and require it in another. A term retired by one concept while live in
    a second is therefore not a naming preference — it is a term the sweep
    cannot be given an answer about.

    The same word retired by two concepts is refused for the same reason
    ``loader.py`` refuses a repeated YAML key: ``Registry.retired_terms`` maps a
    term to the concept that retired it, and a second claim would silently win.
    "What replaced this word?" must have one answer.
    """
    live = set(concepts)
    for concept in concepts.values():
        live.update(concept.declared_values)

    claimed = {}
    for concept in concepts.values():
        location = f"{concept.source}:{concept.name}"
        for alias in concept.retired_aliases:
            if alias in live:
                errors.add(
                    E.RETIRED_ALIAS_COLLISION, location,
                    f"{alias!r} is retired here but is a live value or concept "
                    f"name elsewhere in the registry — the forbidden-term sweep "
                    f"cannot both forbid and require one word",
                )
            if alias in claimed:
                errors.add(
                    E.DUPLICATE_RETIRED_ALIAS, location,
                    f"{alias!r} is already retired by {claimed[alias]} — one "
                    f"retired term names one concept that replaced it",
                )
            else:
                claimed[alias] = concept.name


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _compiles(pattern):
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True
