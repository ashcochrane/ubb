"""Compile and validate the gate programme: the manifest, the ledger, the
permanent exceptions and the slices they name.

Every rule ADR-0008 §8 and #201 state about these files is enforced here, and
the whole programme is loaded through one entry point — :func:`load_programme`
— so a test, the CLI and CI all reach the same verdict. Errors are collected
rather than raised at the first fault: a manifest with four mistakes should take
one run to fix.

The load is deliberately *not* pure. It reads the CI workflow and the test files
an `installed` row names, because the only interesting question this file
answers is whether a claim about the repository is true. A checker that read
only the manifest could confirm the manifest agreed with itself.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tools.gates import errors as codes
from tools.gates.enforcement import collection_faults, step_faults
from tools.gates.errors import GateError, GatesInvalid
# Borrowed rather than copied. `load_yaml` refuses a mapping key that appears
# twice, where PyYAML's `safe_load` silently keeps the last — the wrong default
# for a manifest whose whole point is that every gate is accounted for exactly
# once, just as it is for a registry where a term is defined exactly once.
from tools.vocabulary.loader import DuplicateKey, load_yaml

SCHEMA_FILE = "schema.yaml"
SLICES_FILE = "slices.yaml"
MANIFEST_FILE = "manifest.yaml"
LEDGER_FILE = "migration-ledger.yaml"
EXCEPTIONS_FILE = "permanent-exceptions.yaml"
REQUIRED_FILES = (SCHEMA_FILE, SLICES_FILE, MANIFEST_FILE, LEDGER_FILE,
                  EXCEPTIONS_FILE)
#: Not registry content, and not an error either — the reasoning has to live
#: somewhere, and beside the data is the right place.
READ_BY_HUMANS = ("README.md",)

WORKFLOW_PATH = ".github/workflows/ci.yml"

SLICE_FIELDS = {"issue": int, "title": str, "order": int, "landed": bool}

INSTALLED = "installed"
DEFERRED = "deferred_obligation"


@dataclass(frozen=True)
class Slice:
    key: str
    issue: int
    title: str
    order: int
    landed: bool


@dataclass(frozen=True)
class Suite:
    name: str
    summary: str
    job: str
    step: str
    root: str
    config: str | None


@dataclass(frozen=True)
class Site:
    """One place an `installed` row says its gate runs."""
    kind: str
    fields: tuple[tuple[str, str], ...]

    def __getitem__(self, key):
        return dict(self.fields)[key]

    def __str__(self):
        return " ".join(f"{key}={value!r}" for key, value in self.fields)


@dataclass(frozen=True)
class Row:
    """One gate or one obligation."""
    id: str
    section: str
    statement: str
    oracle: str
    status: str
    body: dict = field(repr=False)
    sites: tuple[Site, ...] = ()
    #: The `owned_by_` spelling this row was compiled against. Carried rather
    #: than assumed, so `owner_slice` cannot read a status the schema no longer
    #: declares that way.
    prefix: str = "owned_by_"

    @property
    def installed(self):
        return self.status == INSTALLED

    @property
    def owner_slice(self):
        """The slice key this row is owed to, or None."""
        return owner_slice_of(self.status, self.prefix)


@dataclass(frozen=True)
class LedgerEntry:
    id: str
    gate: str
    site: str
    expected: str
    owner_slice: str
    reason: str
    found: str | None = None

    @property
    def identity(self):
        """What makes two entries the same debt across two revisions.

        The id is a label a human chose; the debt is the gate and the place.
        Re-labelling an entry must not read as paying one off and taking
        another on, and moving one must not hide behind a stable id.
        """
        return (self.gate, self.site)


@dataclass(frozen=True)
class Authorisation:
    gate: str
    issue: int
    entries_added: int
    reason: str


@dataclass(frozen=True)
class PermanentException:
    id: str
    gate: str
    site: str
    reason: str

    @property
    def identity(self):
        """As :attr:`LedgerEntry.identity`, and for the same reason."""
        return (self.gate, self.site)


@dataclass(frozen=True)
class Programme:
    slices: dict
    suites: dict
    gates: dict
    obligations: dict
    entries: tuple
    authorisations: tuple
    exceptions: tuple

    @property
    def rows(self):
        return {**self.gates, **self.obligations}

    def installed_gates(self):
        return {name: row for name, row in self.gates.items() if row.installed}


def owner_slice_of(status, prefix="owned_by_"):
    """`owned_by_slice_4` -> `slice_4`; anything else -> None."""
    if isinstance(status, str) and status.startswith(prefix):
        return status[len(prefix):]
    return None


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_programme(gates_dir, repo_root):
    """Load and validate the whole programme, or raise :class:`GatesInvalid`."""
    gates_dir = Path(gates_dir)
    repo_root = Path(repo_root)

    errors = []
    documents = _read_documents(gates_dir, errors)
    if errors:
        raise GatesInvalid(errors)

    schema = _schema(documents[SCHEMA_FILE], errors)
    slices = _slices(documents[SLICES_FILE], errors)
    if errors:
        raise GatesInvalid(errors)

    workflow = _workflow(repo_root, errors)
    suites = _suites(documents[MANIFEST_FILE], repo_root, workflow, errors)
    gates, obligations = _rows(documents[MANIFEST_FILE], schema, slices, errors)
    _check_inventory(schema, gates, errors)
    _check_enforcement(gates, obligations, suites, repo_root, workflow, errors)

    entries, authorisations = _ledger(documents[LEDGER_FILE], schema, gates,
                                      slices, errors)
    exceptions = _exceptions(documents[EXCEPTIONS_FILE], schema, gates, errors)

    if errors:
        raise GatesInvalid(errors)
    return Programme(slices=slices, suites=suites, gates=gates,
                     obligations=obligations, entries=entries,
                     authorisations=authorisations, exceptions=exceptions)


def _read_documents(gates_dir, errors):
    documents = {}
    if not gates_dir.is_dir():
        errors.append(GateError(codes.GATES_MISSING, str(gates_dir),
                                "the gates directory does not exist"))
        return documents

    # No ignored category. A file here that nothing reads is either a document
    # somebody believes is enforced and is not, or a mislaid one — and either way
    # a directory that silently tolerates it is how a manifest acquires a second,
    # unread copy of itself.
    for path in sorted(gates_dir.iterdir()):
        if path.name in REQUIRED_FILES or path.name in READ_BY_HUMANS:
            continue
        errors.append(GateError(
            codes.UNEXPECTED_FILE, f"gates/{path.name}",
            f"nothing reads this. The gates directory holds exactly "
            f"{', '.join(REQUIRED_FILES)} and {', '.join(READ_BY_HUMANS)}."))

    for name in REQUIRED_FILES:
        path = gates_dir / name
        if not path.is_file():
            errors.append(GateError(codes.GATES_MISSING, f"gates/{name}",
                                    "a required file is missing"))
            continue
        try:
            document = load_yaml(path.read_text(encoding="utf-8"))
        except DuplicateKey as duplicate:
            errors.append(GateError(codes.DUPLICATE_KEY, f"gates/{name}",
                                    str(duplicate)))
            continue
        except (yaml.YAMLError, UnicodeDecodeError) as problem:
            errors.append(GateError(codes.YAML_INVALID, f"gates/{name}",
                                    str(problem).replace("\n", " ")))
            continue
        if not isinstance(document, dict):
            errors.append(GateError(codes.FILE_NOT_MAPPING, f"gates/{name}",
                                    f"expected a mapping, found "
                                    f"{type(document).__name__}"))
            continue
        documents[name] = document
    return documents


def _workflow(repo_root, errors):
    path = repo_root / WORKFLOW_PATH
    if not path.is_file():
        errors.append(GateError(codes.WORKFLOW_MISSING, WORKFLOW_PATH,
                                "the CI workflow is missing, so no `installed` "
                                "row can be verified"))
        return {}
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as problem:
        errors.append(GateError(codes.WORKFLOW_INVALID, WORKFLOW_PATH,
                                str(problem).replace("\n", " ")))
        return {}
    if not isinstance(document, dict):
        errors.append(GateError(codes.WORKFLOW_INVALID, WORKFLOW_PATH,
                                "the workflow is not a mapping"))
        return {}
    return document


# --- schema.yaml ------------------------------------------------------------

def _schema(document, errors):
    """The shape rules, with every list the compiler consumes made concrete."""
    where = f"gates/{SCHEMA_FILE}"

    def block(key):
        value = document.get(key)
        if not isinstance(value, dict):
            errors.append(GateError(codes.SCHEMA_INVALID, where,
                                    f"`{key}` must be a mapping"))
            return {}
        return value

    statuses = block("statuses")
    owned = block("owned_status")
    row_fields = block("row_fields")
    kinds = block("enforcement_kinds")

    # The schema is the oracle for what a status REQUIRES and FORBIDS. It is not
    # the oracle for what `installed` MEANS: `Row.installed` compares against the
    # constant above, and `_check_enforcement` acts on it. Renaming the status in
    # this file alone would leave every row silently un-installed while the shape
    # rules still validated — so the two names the compiler acts on must be here.
    for name in (INSTALLED, DEFERRED):
        if name not in statuses:
            errors.append(GateError(codes.SCHEMA_INVALID, where,
                                    f"`statuses` must declare `{name}`: the "
                                    f"compiler acts on it by name, so a schema "
                                    f"that renames it would disarm every row "
                                    f"carrying it rather than reject it"))

    prefix = owned.get("prefix")
    if not isinstance(prefix, str) or not prefix:
        errors.append(GateError(codes.SCHEMA_INVALID, where,
                                "`owned_status.prefix` must be a non-empty "
                                "string"))
        prefix = "owned_by_"

    def names(source, key):
        value = source.get(key) or []
        if not isinstance(value, list) or any(not isinstance(item, str)
                                              for item in value):
            errors.append(GateError(codes.SCHEMA_INVALID, where,
                                    f"`{key}` must be a list of field names"))
            return ()
        return tuple(value)

    shapes = {}
    for name, body in list(statuses.items()) + [(prefix, owned)]:
        if not isinstance(body, dict):
            errors.append(GateError(codes.SCHEMA_INVALID, where,
                                    f"status `{name}` must be a mapping"))
            continue
        shapes[name] = (names(body, "requires"), names(body, "forbids"))

    enforcement = {}
    for name, body in kinds.items():
        if not isinstance(body, dict) or not isinstance(body.get("fields"),
                                                        list):
            errors.append(GateError(codes.SCHEMA_INVALID, where,
                                    f"enforcement kind `{name}` must declare a "
                                    f"list of fields"))
            continue
        enforcement[name] = frozenset(body["fields"])

    inventory = document.get("gate_inventory")
    if not isinstance(inventory, list) or not inventory:
        errors.append(GateError(codes.SCHEMA_INVALID, where,
                                "`gate_inventory` must list ADR-0008 §8's gates"))
        inventory = []

    conditional = {name for shape in shapes.values() for group in shape
                   for name in group}
    return {
        "prefix": prefix,
        "shapes": shapes,
        "row_required": names(row_fields, "required"),
        "row_allowed": (frozenset(names(row_fields, "required"))
                        | frozenset(names(row_fields, "optional"))
                        | conditional),
        "enforcement_kinds": enforcement,
        "inventory": tuple(inventory),
        "ledger_entry": _field_rules(document, "ledger_entry_fields", where,
                                     errors),
        "authorisation": _field_rules(document, "seeding_authorisation_fields",
                                      where, errors),
        "exception": _field_rules(document, "exception_fields", where, errors),
    }


def _field_rules(document, key, where, errors):
    body = document.get(key)
    if not isinstance(body, dict):
        errors.append(GateError(codes.SCHEMA_INVALID, where,
                                f"`{key}` must be a mapping"))
        return ((), frozenset())
    required = tuple(body.get("required") or ())
    optional = tuple(body.get("optional") or ())
    if any(not isinstance(name, str) for name in required + optional):
        errors.append(GateError(codes.SCHEMA_INVALID, where,
                                f"`{key}` must list field names"))
        return ((), frozenset())
    return required, frozenset(required) | frozenset(optional)


# --- slices.yaml ------------------------------------------------------------

def _slices(document, errors):
    where = f"gates/{SLICES_FILE}"
    declared = document.get("slices")
    if not isinstance(declared, dict) or not declared:
        errors.append(GateError(codes.SLICES_INVALID, where,
                                "`slices` must be a non-empty mapping"))
        return {}

    slices, issues, orders = {}, {}, {}
    for key, body in declared.items():
        at = f"{where}: {key}"
        if not isinstance(body, dict):
            errors.append(GateError(codes.SLICE_NOT_MAPPING, at,
                                    f"expected a mapping, found "
                                    f"{type(body).__name__}"))
            continue
        values, faulty = {}, False
        for name, expected in SLICE_FIELDS.items():
            if name not in body:
                errors.append(GateError(codes.SLICE_MISSING_FIELD, at,
                                        f"`{name}` is required"))
                faulty = True
                continue
            value = body[name]
            # `bool` is a subclass of `int`: an `order: true` must not pass as
            # a position in the chain.
            if (not isinstance(value, expected)
                    or (expected is int and isinstance(value, bool))
                    or (expected is str and not value.strip())):
                errors.append(GateError(codes.SLICE_INVALID_FIELD_TYPE, at,
                                        f"`{name}` must be a non-empty "
                                        f"{expected.__name__}, found "
                                        f"{value!r}"))
                faulty = True
                continue
            values[name] = value
        if faulty:
            continue

        for registry, name, label, code in (
                (issues, "issue", "issue", codes.DUPLICATE_SLICE_ISSUE),
                (orders, "order", "position in the chain",
                 codes.DUPLICATE_SLICE_ORDER)):
            if values[name] in registry:
                errors.append(GateError(code, at,
                                        f"{label} {values[name]} is already "
                                        f"declared by `{registry[values[name]]}`"))
            registry[values[name]] = key
        slices[key] = Slice(key=key, **values)
    return slices


# --- manifest.yaml ----------------------------------------------------------

SUITE_FIELDS = {"summary": True, "job": True, "step": True, "root": True,
                "config": False}


def _suites(document, repo_root, workflow, errors):
    where = f"gates/{MANIFEST_FILE}"
    declared = document.get("suites")
    if declared is None:
        return {}
    if not isinstance(declared, dict):
        errors.append(GateError(codes.SUITE_NOT_MAPPING, where,
                                "`suites` must be a mapping"))
        return {}

    suites = {}
    for name, body in declared.items():
        at = f"{where}: suites.{name}"
        if not isinstance(body, dict):
            errors.append(GateError(codes.SUITE_NOT_MAPPING, at,
                                    f"expected a mapping, found "
                                    f"{type(body).__name__}"))
            continue
        values, faulty = {}, False
        for field_name, required in SUITE_FIELDS.items():
            value = body.get(field_name)
            if value is None:
                if required:
                    errors.append(GateError(codes.SUITE_MISSING_FIELD, at,
                                            f"`{field_name}` is required"))
                    faulty = True
                values[field_name] = None
                continue
            if not isinstance(value, str) or not value.strip():
                errors.append(GateError(codes.SUITE_INVALID_FIELD_TYPE, at,
                                        f"`{field_name}` must be a non-empty "
                                        f"string, found {value!r}"))
                faulty = True
                continue
            values[field_name] = value
        for unknown in sorted(set(body) - set(SUITE_FIELDS)):
            errors.append(GateError(codes.SUITE_UNKNOWN_FIELD, at,
                                    f"`{unknown}` is not a suite field"))
            faulty = True
        if faulty:
            continue

        if not (repo_root / values["root"]).is_dir():
            errors.append(GateError(codes.SUITE_ROOT_MISSING, at,
                                    f"the suite's root `{values['root']}` is "
                                    f"not a directory in this repository"))
        if values["config"] and not (repo_root / values["config"]).is_file():
            errors.append(GateError(codes.SUITE_CONFIG_MISSING, at,
                                    f"the declared pytest configuration "
                                    f"`{values['config']}` does not exist"))
        # A declared suite is verified whether a gate names it or not, so
        # declaring one is a claim that gets checked rather than a convenience.
        for fault in step_faults(workflow, values["job"], values["step"]):
            errors.append(GateError(codes.GATE_NOT_RUNNING, at,
                                    f"the suite does not run: {fault}"))
        suites[name] = Suite(name=name, **values)
    return suites


def _rows(document, schema, slices, errors):
    where = f"gates/{MANIFEST_FILE}"
    sections = {}
    for section in ("gates", "obligations"):
        declared = document.get(section)
        if declared is None:
            sections[section] = {}
            continue
        if not isinstance(declared, dict):
            errors.append(GateError(codes.ROW_NOT_MAPPING, where,
                                    f"`{section}` must be a mapping"))
            sections[section] = {}
            continue
        sections[section] = {
            name: row for name, row in (
                (name, _row(name, section, body, schema, slices, where, errors))
                for name, body in declared.items())
            if row is not None
        }
    return sections["gates"], sections["obligations"]


def _row(name, section, body, schema, slices, where, errors):
    at = f"{where}: {name}"
    if not isinstance(body, dict):
        errors.append(GateError(codes.ROW_NOT_MAPPING, at,
                                f"expected a mapping, found "
                                f"{type(body).__name__}"))
        return None

    for unknown in sorted(set(body) - schema["row_allowed"]):
        errors.append(GateError(codes.UNKNOWN_FIELD, at,
                                f"`{unknown}` is not a field the schema "
                                f"declares"))
    for required in schema["row_required"]:
        if required not in body:
            errors.append(GateError(codes.MISSING_FIELD, at,
                                    f"`{required}` is required of every row"))

    status = body.get("status")
    shape_key = _shape_key(status, schema, slices)
    if shape_key is None:
        # The row is still returned. Whether a gate is ACCOUNTED FOR is a
        # different question from whether its status parses, and reporting an
        # unknown status as a missing gate as well would send a reader looking
        # for a row that is right in front of them.
        errors.append(GateError(codes.UNKNOWN_STATUS, at,
                                f"{status!r} is not a status: expected "
                                f"`{INSTALLED}`, `{DEFERRED}`, or "
                                f"`{schema['prefix']}<slice>` naming a slice "
                                f"declared in {SLICES_FILE} "
                                f"({', '.join(sorted(slices)) or 'none'})"))
    else:
        requires, forbids = schema["shapes"].get(shape_key, ((), ()))
        for required in requires:
            if required not in body:
                errors.append(GateError(
                    codes.MISSING_FIELD, at,
                    f"status `{status}` requires `{required}`"))
        for forbidden in forbids:
            if forbidden in body:
                errors.append(GateError(
                    codes.FORBIDDEN_FIELD, at,
                    f"status `{status}` forbids `{forbidden}`"))

    for field_name, value in body.items():
        if field_name == "enforced_by":
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(GateError(codes.INVALID_FIELD_TYPE, at,
                                    f"`{field_name}` must be a non-empty "
                                    f"string, found {value!r}"))

    owner = owner_slice_of(status, schema["prefix"])
    if owner in slices and slices[owner].landed:
        errors.append(GateError(
            codes.LANDED_SLICE_OWNS_GATE, at,
            f"`{owner}` (#{slices[owner].issue}) has landed, so it can no "
            f"longer install this gate. Either the gate was installed and this "
            f"row was not flipped, or the slice landed owing work it did not "
            f"do."))

    sites = _sites(name, body, schema, at, errors)
    return Row(id=name, section=section,
               statement=str(body.get("statement", "")),
               oracle=str(body.get("oracle", "")), status=str(status),
               body=body, sites=sites, prefix=schema["prefix"])


def _shape_key(status, schema, slices):
    """Which shape rule governs ``status``, or None if it is not a status."""
    if status in schema["shapes"] and status != schema["prefix"]:
        return status
    owner = owner_slice_of(status, schema["prefix"])
    if owner is not None and owner in slices:
        return schema["prefix"]
    return None


def _sites(name, body, schema, at, errors):
    declared = body.get("enforced_by")
    if declared is None:
        return ()
    if not isinstance(declared, list) or not declared:
        errors.append(GateError(codes.ENFORCEMENT_EMPTY, at,
                                "`enforced_by` must be a non-empty list of "
                                "sites — an installed gate that names nowhere "
                                "it runs is the claim this manifest exists to "
                                "refuse"))
        return ()

    sites = []
    for index, entry in enumerate(declared):
        if not isinstance(entry, dict) or not entry:
            errors.append(GateError(codes.ENFORCEMENT_NOT_MAPPING,
                                    f"{at}.enforced_by[{index}]",
                                    f"expected a mapping, found {entry!r}"))
            continue
        if any(not isinstance(value, str) or not value.strip()
               for value in entry.values()):
            errors.append(GateError(codes.ENFORCEMENT_NOT_MAPPING,
                                    f"{at}.enforced_by[{index}]",
                                    f"every value must be a non-empty string, "
                                    f"found {entry!r}"))
            continue
        kinds = [kind for kind, fields in schema["enforcement_kinds"].items()
                 if fields == frozenset(entry)]
        if not kinds:
            errors.append(GateError(
                codes.UNKNOWN_ENFORCEMENT_KIND, f"{at}.enforced_by[{index}]",
                f"{sorted(entry)} matches no enforcement kind; expected one of "
                f"{[sorted(fields) for fields in schema['enforcement_kinds'].values()]}"))
            continue
        sites.append(Site(kind=kinds[0],
                          fields=tuple(sorted(entry.items()))))
    return tuple(sites)


def _check_inventory(schema, gates, errors):
    """ADR-0008 §8 lists twenty-seven gates. All of them are accounted for."""
    expected, present = set(schema["inventory"]), set(gates)
    where = f"gates/{MANIFEST_FILE}"
    for missing in sorted(expected - present):
        errors.append(GateError(codes.INVENTORY_MISMATCH, where,
                                f"`{missing}` is in the declared inventory and "
                                f"has no row"))
    for extra in sorted(present - expected):
        errors.append(GateError(codes.INVENTORY_MISMATCH, where,
                                f"`{extra}` is not in the declared inventory"))


def _check_enforcement(gates, obligations, suites, repo_root, workflow, errors):
    """Every `installed` row's sites are armed, and actually collected."""
    where = f"gates/{MANIFEST_FILE}"
    for name, row in {**gates, **obligations}.items():
        if not row.installed:
            continue
        for site in row.sites:
            at = f"{where}: {name} ({site})"
            if site.kind == "workflow_step":
                faults = step_faults(workflow, site["job"], site["step"])
            else:
                suite = suites.get(site["suite"])
                if suite is None:
                    errors.append(GateError(
                        codes.UNKNOWN_SUITE, at,
                        f"`{site['suite']}` is not a suite this manifest "
                        f"declares ({', '.join(sorted(suites)) or 'none'})"))
                    continue
                # Only the node. Whether the suite RUNS was settled once when it
                # was declared, and blaming a `continue-on-error` job again for
                # every gate that names it turns one cause into N errors.
                faults = collection_faults(repo_root, suite.root, suite.config,
                                           site["node"])
            for fault in faults:
                errors.append(GateError(
                    codes.GATE_NOT_RUNNING, at,
                    f"claims to be installed, but {fault}"))


# --- migration-ledger.yaml and permanent-exceptions.yaml --------------------

#: Which codes :func:`_records` reports, per list. Named rather than positional:
#: four bare strings in a tuple is exactly the argument a caller gets wrong.
@dataclass(frozen=True)
class RecordCodes:
    not_mapping: str
    missing: str
    unknown: str
    bad_type: str


ENTRY_CODES = RecordCodes(codes.ENTRY_NOT_MAPPING, codes.ENTRY_MISSING_FIELD,
                          codes.ENTRY_UNKNOWN_FIELD,
                          codes.ENTRY_INVALID_FIELD_TYPE)
AUTHORISATION_CODES = RecordCodes(codes.AUTHORISATION_NOT_MAPPING,
                                  codes.AUTHORISATION_MISSING_FIELD,
                                  codes.AUTHORISATION_UNKNOWN_FIELD,
                                  codes.AUTHORISATION_INVALID_FIELD_TYPE)


def _ledger(document, schema, gates, slices, errors):
    where = f"gates/{LEDGER_FILE}"
    entries = _records(document, "entries", schema["ledger_entry"], where,
                       LedgerEntry, errors, ENTRY_CODES, integers=())
    _check_identity(entries, where, errors)
    for entry in entries:
        at = f"{where}: {entry.id}"
        _check_gate_reference(entry.gate, gates, at, errors)
        if entry.owner_slice not in slices:
            errors.append(GateError(codes.UNKNOWN_SLICE, at,
                                    f"`{entry.owner_slice}` is not a slice "
                                    f"declared in {SLICES_FILE}"))
        elif slices[entry.owner_slice].landed:
            errors.append(GateError(
                codes.OWNER_SLICE_LANDED, at,
                f"`{entry.owner_slice}` (#{slices[entry.owner_slice].issue}) "
                f"has already landed, so this debt is owed by nobody. It "
                f"either goes away or it moves to a slice that has not landed "
                f"— which is a reviewed decision, not a default."))

    authorisations = _records(document, "seeding_authorisations",
                              schema["authorisation"], where, Authorisation,
                              errors, AUTHORISATION_CODES,
                              integers=("issue", "entries_added"))
    for authorisation in authorisations:
        _check_gate_reference(authorisation.gate, gates,
                              f"{where}: authorisation for "
                              f"{authorisation.gate}", errors)
    return entries, authorisations


def _exceptions(document, schema, gates, errors):
    where = f"gates/{EXCEPTIONS_FILE}"
    exceptions = _records(document, "exceptions", schema["exception"], where,
                          PermanentException, errors, ENTRY_CODES, integers=())
    _check_identity(exceptions, where, errors)
    for exception in exceptions:
        _check_gate_reference(exception.gate, gates, f"{where}: {exception.id}",
                              errors)
    return exceptions


def _records(document, key, rules, where, factory, errors, record_codes,
             integers):
    not_mapping = record_codes.not_mapping
    missing, unknown = record_codes.missing, record_codes.unknown
    bad_type = record_codes.bad_type
    required, allowed = rules
    declared = document.get(key)
    if declared is None:
        declared = []
    if not isinstance(declared, list):
        errors.append(GateError(not_mapping, where,
                                f"`{key}` must be a list, found "
                                f"{type(declared).__name__}"))
        return ()

    records = []
    for index, body in enumerate(declared):
        at = f"{where}: {key}[{index}]"
        if not isinstance(body, dict):
            errors.append(GateError(not_mapping, at,
                                    f"expected a mapping, found {body!r}"))
            continue
        faulty = False
        for name in required:
            if name not in body:
                errors.append(GateError(missing, at, f"`{name}` is required"))
                faulty = True
        for name in sorted(set(body) - allowed):
            errors.append(GateError(unknown, at,
                                    f"`{name}` is not a field the schema "
                                    f"declares here"))
            faulty = True
        for name, value in body.items():
            if name in integers:
                if not isinstance(value, int) or isinstance(value, bool):
                    errors.append(GateError(bad_type, at,
                                            f"`{name}` must be an integer, "
                                            f"found {value!r}"))
                    faulty = True
            elif not isinstance(value, str) or not value.strip():
                errors.append(GateError(bad_type, at,
                                        f"`{name}` must be a non-empty string, "
                                        f"found {value!r}"))
                faulty = True
        if not faulty:
            records.append(factory(**body))
    return tuple(records)


def _check_identity(records, where, errors):
    by_id, by_site = {}, {}
    for record in records:
        if record.id in by_id:
            errors.append(GateError(codes.DUPLICATE_ENTRY_ID, where,
                                    f"`{record.id}` is used twice"))
        by_id[record.id] = record
        identity = record.identity
        if identity in by_site:
            errors.append(GateError(
                codes.DUPLICATE_ENTRY_SITE, f"{where}: {record.id}",
                f"the same debt is already recorded as "
                f"`{by_site[identity].id}`: {record.gate} at {record.site}"))
        by_site[identity] = record


def _check_gate_reference(gate, gates, at, errors):
    """An entry may only name a gate that exists AND is installed.

    An entry against a gate nothing runs is a note, not a debt: nothing would
    ever prove it right, wrong or paid. It also cannot shrink, because no gate
    would go green when the site is fixed.
    """
    if gate not in gates:
        errors.append(GateError(codes.UNKNOWN_GATE, at,
                                f"`{gate}` is not a gate in the manifest"))
    elif not gates[gate].installed:
        errors.append(GateError(
            codes.GATE_NOT_INSTALLED, at,
            f"`{gate}` is `{gates[gate].status}`, not installed. A debt "
            f"recorded against a gate that cannot fail anything is a note "
            f"nothing will ever prove or clear — record it in the pull request "
            f"that installs the gate."))
