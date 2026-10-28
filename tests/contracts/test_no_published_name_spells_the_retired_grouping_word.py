"""No published name spells the word a Grouping Field was first called (#541).

ADR-0006 retired the first noun for a Grouping Field, and the registry records
it on `grouping_field_value` as two retired aliases. The forbidden-term sweep
(G7) holds every living surface to them — but it matches the token exactly as
the registry spells it, lower case and whole, and G7's row states the limit
that follows: a Pascal-cased spelling is not a hit, and neither is the word
joined to a suffix by `_`. From #131 to #541 four OpenAPI components lived in
that gap, every SDK model generated off their names lived there with them, and
the declare route wrote the word into the tenant-readable audit feed as a
`resource_type` the sweep never saw as a token.

**SO THIS GATE IS TARGETED, NOT A WORD BAN.** It reads exactly the three places
a name is published as a NAME rather than written as prose, and matches the
word case-insensitively there and nowhere else:

1. **Every component the two published documents carry** — the committed
   contract and the console's snapshot of it — by its key and by its own
   `title`, which is the name every generated client gives the type.
2. **Every generated SDK model** — the module's file name and each class it
   defines, which is where an inline value set nested in a component surfaces
   under a name of its own.
3. **Every audit `resource_type` the backend writes** — a `resource_type=`
   keyword anywhere in living backend code (tests and migrations are not
   writers), or an assignment to a `.resource_type` attribute. The value is
   read as a string literal, a module-level string constant, or a constant of
   the generated `core.vocabulary` (imported by name or read off the module).
   A parameter of the enclosing function is a PASS-THROUGH: the caller decides
   the value, and its call is itself a site — by keyword wherever it is, and
   by position where the helper is defined in the same module. Anything else is
   reported as UNREADABLE rather than assumed clean, so a writer cannot leave
   the gate's sight by computing its value.

Descriptions, comments, property names, locals, and the English word in any
other sense are deliberately left alone, and
`test_positive_control_the_word_elsewhere_is_not_this_gates_subject` puts that
under test: the owner's ruling on #541 keeps this a targeted contract gate and
refuses an indiscriminate ban.

**THE WORD IS THE REGISTRY'S, NOT THIS MODULE'S.** It is read off the concept's
`retired_aliases`, folded the way the match folds a name, so this file spells
the word nowhere — the sweep reads it like any other living module — and a
change to the registry's retirement is felt here rather than drifting from a
copy.

STATED LIMITS, recorded rather than discovered. A pass-through called
POSITIONALLY from another module is not followed (every audit writer is
keyword-only today, and the one positional helper family lives beside its
callers). A value spread in through `**{...}` is not read. And the three
historical database constraint names that still carry the word
(`uq_<word>_def_key`, `uq_<word>_def_slot`, `uq_<word>_value`) are not names
this gate reads at all: the owner handed them to W6, whose migration squash
creates their final names.
"""

import ast
import functools
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from _helpers import REAL_REGISTRY, REPO_ROOT
from tools.vocabulary import load_registry

#: The concept whose retired aliases are this gate's whole oracle.
CONCEPT = "grouping_field_value"

#: The two published documents: the committed contract and the console's
#: tracked snapshot of it, which every console type is generated from.
DOCUMENTS = ("openapi/v1.json", "apps/ui/src/api/schema.json")

#: The generated SDK models, one module per named schema.
SDK_MODELS = "ubb-sdk/ubb/_core/models"

#: The backend, and the generated module a writer may hold a value by
#: reference to.
BACKEND = "ubb-platform"
VOCABULARY = "ubb-platform/core/vocabulary.py"
VOCABULARY_MODULE = "core.vocabulary"

#: The keyword (and attribute) an audit record's subject travels under.
KEYWORD = "resource_type"

#: Directories that hold no writer: a test plants what it asserts, and a
#: historical migration is frozen.
NOT_WRITERS = frozenset({"tests", "migrations", "node_modules"})


# ---------------------------------------------------------------------------
# The oracle
# ---------------------------------------------------------------------------

def folded(name):
    """A name with case and separators taken out: `Foo_Bar-baz` → `foobarbaz`.

    Separators go too, because the word reaches a published name in three
    casings — Pascal in a component, snake in a module or a value, and a
    title-cased phrase in a generated title.
    """
    return re.sub(r"[^0-9a-z]", "", name.casefold())


@functools.cache
def retired_words(registry_root=REAL_REGISTRY):
    """The concept's retired aliases, folded. Empty would be vacuous, and
    `test_the_oracle_is_the_registrys_retirement` refuses that."""
    concept = load_registry(registry_root, REPO_ROOT).concepts[CONCEPT]
    return frozenset(folded(alias) for alias in concept.retired_aliases)


def spells(name, words):
    """Whether ``name`` carries any of ``words``, case- and separator-blind."""
    return any(word in folded(name) for word in words)


@dataclass
class Finding:
    """One published name that spells the word, or one the gate could not read."""
    where: str
    name: str
    surface: str

    def __str__(self):
        return f"{self.surface}: `{self.name}` at {self.where}"


# ---------------------------------------------------------------------------
# 1. The published documents
# ---------------------------------------------------------------------------

def component_names(document):
    """``(pointer, name)`` for every component: its key, and its own title."""
    schemas = document.get("components", {}).get("schemas", {})
    for key, schema in schemas.items():
        yield f"/components/schemas/{key}", key
        title = schema.get("title") if isinstance(schema, dict) else None
        if isinstance(title, str):
            yield f"/components/schemas/{key}/title", title


def document_findings(root, words):
    findings, read = [], {}
    for relative in DOCUMENTS:
        path = root / relative
        if not path.is_file():
            findings.append(Finding(relative, "(missing)", "unreadable document"))
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        names = list(component_names(document))
        read[relative] = len(document.get("components", {}).get("schemas", {}))
        findings.extend(Finding(f"{relative}#{pointer}", name, "component")
                        for pointer, name in names if spells(name, words))
    return findings, read


# ---------------------------------------------------------------------------
# 2. The generated SDK models
# ---------------------------------------------------------------------------

def model_names(models_dir):
    """``(where, name)`` for every generated model module and every class in it."""
    for path in sorted(models_dir.glob("*.py")):
        yield path.name, path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                yield f"{path.name}:{node.lineno}", node.name


def model_findings(root, words):
    models_dir = root / SDK_MODELS
    modules = sorted(models_dir.glob("*.py")) if models_dir.is_dir() else []
    if not modules:
        return [Finding(SDK_MODELS, "(no modules)", "unreadable SDK")], 0
    return ([Finding(f"{SDK_MODELS}/{where}", name, "SDK model")
             for where, name in model_names(models_dir) if spells(name, words)],
            len(modules))


# ---------------------------------------------------------------------------
# 3. The audit resource types the backend writes
# ---------------------------------------------------------------------------

def _string_constants(tree):
    """Module-level ``NAME = "text"``, for names bound exactly once."""
    bound, values = {}, {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                bound[target.id] = bound.get(target.id, 0) + 1
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    values[target.id] = value.value
    return {name: text for name, text in values.items() if bound[name] == 1}


def _vocabulary_imports(tree):
    """``(names, modules)`` — what this module imports FROM the generated
    vocabulary, and the spellings under which it holds the module itself."""
    names, modules = {}, set()
    package, _, leaf = VOCABULARY_MODULE.rpartition(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == VOCABULARY_MODULE:
            for alias in node.names:
                names[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module == package:
            modules.update(alias.asname or alias.name
                           for alias in node.names if alias.name == leaf)
        elif isinstance(node, ast.Import):
            modules.update(alias.asname or alias.name
                           for alias in node.names
                           if alias.name == VOCABULARY_MODULE)
    return names, modules


def _positional_index(function):
    """Where ``resource_type`` sits among a function's positional parameters,
    or None when it is keyword-only or absent."""
    positional = [*function.args.posonlyargs, *function.args.args]
    for index, argument in enumerate(positional):
        if argument.arg == KEYWORD:
            return index
    return None


@dataclass
class Reading:
    """What the walk found: the values written, the pass-throughs it followed
    to their callers, and the values it could not read."""
    written: list = field(default_factory=list)
    passed_through: list = field(default_factory=list)
    unreadable: list = field(default_factory=list)
    modules: list = field(default_factory=list)


class _Writers(ast.NodeVisitor):
    def __init__(self, relative, tree, vocabulary, reading):
        self.relative = relative
        self.reading = reading
        self.constants = _string_constants(tree)
        self.vocabulary = vocabulary
        self.from_vocabulary, self.vocabulary_modules = _vocabulary_imports(tree)
        #: The same module's helpers that take the value positionally.
        self.helpers = {
            node.name: index for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for index in [_positional_index(node)] if index is not None}
        self.parameters = [frozenset()]

    def _scope(self, node):
        arguments = node.args
        names = {argument.arg for argument in (
            *arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)}
        names.update(extra.arg for extra in (arguments.vararg, arguments.kwarg)
                     if extra is not None)
        self.parameters.append(self.parameters[-1] | names)
        self.generic_visit(node)
        self.parameters.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _scope

    def visit_Call(self, node):
        for keyword in node.keywords:
            if keyword.arg == KEYWORD:
                self._site(keyword.value)
        callee = node.func.id if isinstance(node.func, ast.Name) else None
        index = self.helpers.get(callee)
        if index is not None and len(node.args) > index:
            self._site(node.args[index])
        self.generic_visit(node)

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr == KEYWORD:
                self._site(node.value)
        self.generic_visit(node)

    def _site(self, value):
        where = f"{self.relative}:{value.lineno}"
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            self.reading.written.append((where, value.value))
            return
        if isinstance(value, ast.Name):
            if value.id in self.constants:
                self.reading.written.append((where, self.constants[value.id]))
                return
            if value.id in self.from_vocabulary:
                self._from_vocabulary(where, self.from_vocabulary[value.id])
                return
            if value.id in self.parameters[-1]:
                self.reading.passed_through.append((where, value.id))
                return
        if (isinstance(value, ast.Attribute)
                and ast.unparse(value.value) in self.vocabulary_modules):
            self._from_vocabulary(where, value.attr)
            return
        self.reading.unreadable.append((where, ast.unparse(value)))

    def _from_vocabulary(self, where, name):
        if name in self.vocabulary:
            self.reading.written.append((where, self.vocabulary[name]))
        else:
            self.reading.unreadable.append(
                (where, f"{VOCABULARY_MODULE}.{name}, which it does not define"))


def backend_modules(root):
    """Every living backend module — tests, migrations, hidden directories
    (the virtualenv among them) and caches left out."""
    for directory, subdirectories, files in os.walk(root / BACKEND):
        subdirectories[:] = sorted(
            name for name in subdirectories
            if name not in NOT_WRITERS and not name.startswith((".", "__")))
        for name in sorted(files):
            if (name.endswith(".py") and name != "conftest.py"
                    and not name.startswith("test_")):
                yield Path(directory) / name


def read_resource_types(root):
    vocabulary_path = root / VOCABULARY
    vocabulary = (_string_constants(ast.parse(
        vocabulary_path.read_text(encoding="utf-8")))
        if vocabulary_path.is_file() else {})
    reading = Reading()
    for path in backend_modules(root):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        if KEYWORD not in source:
            continue
        reading.modules.append(relative)
        tree = ast.parse(source, filename=relative)
        _Writers(relative, tree, vocabulary, reading).visit(tree)
    return reading


def resource_type_findings(reading, words):
    return ([Finding(where, value, "audit resource_type")
             for where, value in reading.written if spells(value, words)]
            + [Finding(where, value, "unreadable audit resource_type")
               for where, value in reading.unreadable])


# ---------------------------------------------------------------------------
# The verdict, over a whole repository
# ---------------------------------------------------------------------------

def verdict(root, words):
    """Every finding in the repository at ``root``, all three surfaces."""
    documents, _ = document_findings(root, words)
    models, _ = model_findings(root, words)
    return documents + models + resource_type_findings(
        read_resource_types(root), words)


@pytest.fixture(scope="module")
def words():
    return retired_words()


@pytest.fixture(scope="module")
def reading():
    return read_resource_types(REPO_ROOT)


def _listed(findings):
    return "\n".join(f"  {finding}" for finding in findings)


# ---------------------------------------------------------------------------
# The gate, on the committed tree
# ---------------------------------------------------------------------------

def test_no_component_name_spells_the_retired_grouping_word(words):
    """THE GATE'S FIRST SURFACE. A component's key and title are the name the
    contract publishes and every generated client takes for the type."""
    findings, _ = document_findings(REPO_ROOT, words)
    assert not findings, (
        "a published component still spells the retired grouping word — take "
        "the Grouping Field's own name (ADR-0006):\n" + _listed(findings))


def test_no_generated_sdk_model_spells_the_retired_grouping_word(words):
    """THE SECOND. The generated core names its modules and classes after the
    contract's schemas, so this is what a Python integration imports."""
    findings, _ = model_findings(REPO_ROOT, words)
    assert not findings, (
        "a generated SDK model still spells the retired grouping word — "
        "rename the component and regenerate:\n" + _listed(findings))


def test_no_audit_resource_type_spells_the_retired_grouping_word(words, reading):
    """THE THIRD. The audit feed is tenant-readable, so a record's
    `resource_type` is as published as a response field."""
    findings = [finding for finding in resource_type_findings(reading, words)
                if finding.surface == "audit resource_type"]
    assert not findings, (
        "the backend writes an audit resource_type spelling the retired "
        "grouping word:\n" + _listed(findings))


def test_every_audit_resource_type_is_read_rather_than_assumed(reading):
    """A value the walk cannot read is not a value it can vouch for. Hold it
    by a literal, a module constant or a `core.vocabulary` constant — or
    extend this reader, which is where the next shape belongs."""
    assert not reading.unreadable, (
        "these audit resource_type values are neither literals nor constants "
        "this gate can resolve:\n"
        + "\n".join(f"  {where}: {text}" for where, text in reading.unreadable))


# ---------------------------------------------------------------------------
# Vacuity guards — the gate read what it claims to
# ---------------------------------------------------------------------------

def test_the_oracle_is_the_registrys_retirement(words):
    """The word comes off the registry, and it is one word: every alias the
    concept retires carries the shortest, so matching the shortest is matching
    them all."""
    assert words, f"`{CONCEPT}` retires no alias, so this gate matches nothing"
    stem = min(words, key=len)
    assert all(stem in word for word in words), sorted(words)


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_each_document_was_read_whole(words, relative):
    _, read = document_findings(REPO_ROOT, words)
    assert read.get(relative, 0) > 100, (
        f"`{relative}` yielded {read.get(relative, 0)} components; the contract "
        f"carries over two hundred, so the walk did not read it")


def test_the_generated_models_were_read(words):
    _, modules = model_findings(REPO_ROOT, words)
    assert modules > 100, f"only {modules} generated model modules were read"


def test_the_backend_walk_reached_the_writers(reading):
    """The ledger's own module is the one writer every audit record passes
    through; reaching it, and finding the literal sites the endpoints write,
    is what proves the walk read the backend rather than an empty directory."""
    assert "ubb-platform/apps/platform/audit/ledger.py" in reading.modules
    assert len(reading.written) > 50, (
        f"only {len(reading.written)} resource_type values were read")
    assert not any("/tests/" in where or "/migrations/" in where
                   for where, _ in reading.written)


# ---------------------------------------------------------------------------
# Negative controls — each surface, planted, is reported
# ---------------------------------------------------------------------------

def _stem():
    return min(retired_words(), key=len)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _component(title):
    return {"title": title, "type": "object",
            "properties": {"key": {"title": "Key", "type": "string"}}}


def write_repository(root, *, schemas=None, planted_in=DOCUMENTS, models=None,
                     backend=None, vocabulary="", sdk=True):
    """A complete, clean synthetic repository: both documents, one generated
    model and one backend writer. Each control plants exactly one thing."""
    clean = {"GroupingFieldOut": _component("GroupingFieldOut")}
    for relative in DOCUMENTS:
        chosen = {**clean, **(schemas or {})} if relative in planted_in else clean
        _write(root / relative, json.dumps({
            "openapi": "3.1.0", "info": {"title": "Synthetic", "version": "1"},
            "paths": {}, "components": {"schemas": chosen}}))
    if sdk:
        for name, source in {"grouping_field_out.py":
                             "class GroupingFieldOut:\n    pass\n",
                             **(models or {})}.items():
            _write(root / SDK_MODELS / name, source)
    for relative, source in {
            "apps/example/views.py":
            'record(resource_type="grouping_field_registry")\n',
            **(backend or {})}.items():
        _write(root / BACKEND / relative, source)
    _write(root / VOCABULARY, vocabulary)
    return root


def test_positive_control_the_clean_repository_passes(tmp_path):
    """Every control below differs from this by its one plant."""
    assert verdict(write_repository(tmp_path), retired_words()) == []


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_negative_control_a_planted_component_is_reported(tmp_path, relative):
    """A `<Word>FooOut` component, planted in ONE of the two documents."""
    planted = f"{_stem().capitalize()}FooOut"
    write_repository(tmp_path, schemas={planted: _component(planted)},
                     planted_in=(relative,))
    found = verdict(tmp_path, retired_words())
    assert [(f.surface, f.name) for f in found] == [
        ("component", planted), ("component", planted)]
    assert {f.where for f in found} == {
        f"{relative}#/components/schemas/{planted}",
        f"{relative}#/components/schemas/{planted}/title"}


def test_negative_control_a_title_alone_is_reported(tmp_path):
    """A clean key whose title spells the word still publishes it: the
    generated clients name the type after the title."""
    planted = f"{_stem().capitalize()}FooOut"
    write_repository(tmp_path, schemas={"FooOut": _component(planted)})
    found = verdict(tmp_path, retired_words())
    assert {f.where.split("#")[1] for f in found} == {
        "/components/schemas/FooOut/title"}


def test_negative_control_a_planted_sdk_model_is_reported(tmp_path):
    stem = _stem()
    planted = f"{stem.capitalize()}FooOut"
    write_repository(tmp_path, models={
        f"{stem}_foo_out.py": f"class {planted}:\n    pass\n"})
    found = verdict(tmp_path, retired_words())
    assert [(f.surface, f.name) for f in found] == [
        ("SDK model", f"{stem}_foo_out"), ("SDK model", planted)]


def test_negative_control_a_planted_resource_type_is_reported(tmp_path):
    """The `<word>_x` resource type, as a literal at the call."""
    planted = f"{_stem()}_x"
    write_repository(tmp_path, backend={
        "apps/example/services.py": f'record(resource_type="{planted}")\n'})
    found = verdict(tmp_path, retired_words())
    assert [(f.surface, f.name, f.where) for f in found] == [
        ("audit resource_type", planted, "ubb-platform/apps/example/services.py:1")]


def test_negative_control_a_value_held_by_a_module_constant_is_read(tmp_path):
    planted = f"{_stem()}_x"
    write_repository(tmp_path, backend={"apps/example/services.py": (
        f'SUBJECT = "{planted}"\n\n\n'
        "def declare():\n"
        "    record(resource_type=SUBJECT)\n")})
    assert [f.name for f in verdict(tmp_path, retired_words())] == [planted]


def test_negative_control_a_value_held_by_the_vocabulary_is_read(tmp_path):
    """Both ways a module holds a generated constant: imported by name, and
    read off the module."""
    planted = f"{_stem()}_x"
    write_repository(
        tmp_path, vocabulary=f'AUDIT_RESOURCE_TYPE_X = "{planted}"\n',
        backend={
            "apps/example/by_name.py": (
                "from core.vocabulary import AUDIT_RESOURCE_TYPE_X\n"
                "record(resource_type=AUDIT_RESOURCE_TYPE_X)\n"),
            "apps/example/by_module.py": (
                "from core import vocabulary\n"
                "record(resource_type=vocabulary.AUDIT_RESOURCE_TYPE_X)\n")})
    found = verdict(tmp_path, retired_words())
    assert sorted(f.where for f in found) == [
        "ubb-platform/apps/example/by_module.py:2",
        "ubb-platform/apps/example/by_name.py:2"]


def test_negative_control_a_helper_taking_the_value_positionally_is_followed(
        tmp_path):
    """The helper's own write is a pass-through; the value its caller hands it
    by POSITION is the site, and it is read."""
    planted = f"{_stem()}_x"
    write_repository(tmp_path, backend={"apps/example/services.py": (
        "def _audited(model, resource_type):\n"
        "    record(resource_type=resource_type)\n\n\n"
        f'_audited(object(), "{planted}")\n')})
    found = verdict(tmp_path, retired_words())
    assert [(f.name, f.where) for f in found] == [
        (planted, "ubb-platform/apps/example/services.py:5")]


def test_negative_control_an_attribute_write_is_read(tmp_path):
    planted = f"{_stem()}_x"
    write_repository(tmp_path, backend={"apps/example/services.py": (
        f'entry.resource_type = "{planted}"\n')})
    assert [f.name for f in verdict(tmp_path, retired_words())] == [planted]


def test_negative_control_a_computed_value_is_unreadable_not_clean(tmp_path):
    """A value assembled at the call could spell anything, so it is reported
    rather than assumed to spell nothing."""
    write_repository(tmp_path, backend={"apps/example/services.py": (
        'PREFIX = "grouping_field"\n'
        'record(resource_type=f"{PREFIX}_registry")\n')})
    found = verdict(tmp_path, retired_words())
    assert [f.surface for f in found] == ["unreadable audit resource_type"]


def test_negative_control_a_vocabulary_name_it_does_not_define_is_unreadable(
        tmp_path):
    write_repository(tmp_path, backend={"apps/example/services.py": (
        "from core.vocabulary import NOT_DECLARED\n"
        "record(resource_type=NOT_DECLARED)\n")})
    found = verdict(tmp_path, retired_words())
    assert [f.surface for f in found] == ["unreadable audit resource_type"]


@pytest.mark.parametrize("missing", ["document", "sdk"])
def test_negative_control_a_missing_surface_is_a_failure_not_a_pass(
        tmp_path, missing):
    write_repository(tmp_path, sdk=(missing != "sdk"))
    if missing == "document":
        (tmp_path / DOCUMENTS[1]).unlink()
    found = verdict(tmp_path, retired_words())
    assert [f.surface for f in found] == [
        "unreadable document" if missing == "document" else "unreadable SDK"]


# ---------------------------------------------------------------------------
# Positive controls — the gate is targeted, not a ban on the word
# ---------------------------------------------------------------------------

def test_positive_control_the_word_elsewhere_is_not_this_gates_subject(tmp_path):
    """The English word, and the retired word in every place this gate does
    not read, passes: a description, a property name and its title, a
    comment, a local, another keyword, a test and a historical migration."""
    stem = _stem()
    planted = f"{stem}_x"
    component = _component("GroupingFieldOut")
    component["description"] = f"Not a {stem} of the problem."
    component["properties"][f"{stem}_note"] = {
        "title": f"{stem.capitalize()} Note", "type": "string"}
    write_repository(tmp_path, schemas={"GroupingFieldOut": component}, backend={
        "apps/example/services.py": (
            f"# the {stem} of a problem\n"
            f'{stem} = "{planted}"\n'
            f'record(kind="{planted}", resource_type="grouping_field_registry")\n'),
        "apps/example/tests/test_services.py": (
            f'record(resource_type="{planted}")\n'),
        "apps/example/migrations/0001_initial.py": (
            f'record(resource_type="{planted}")\n')})
    assert verdict(tmp_path, retired_words()) == []
