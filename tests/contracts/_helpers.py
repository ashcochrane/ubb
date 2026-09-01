"""Synthetic registries, for putting the compiler through its real entry point.

Every negative control here builds a complete registry on disk and loads it with
:func:`tools.vocabulary.load_registry` — the same function CI and the CLI call.
Nothing patches the compiler's internals, because a test that mocks the thing
under test can only ever reproduce its mistakes: three SDK methods called routes
that existed nowhere and stayed green for months exactly that way.

The synthetic registries use the **real** ``schema.yaml`` and ``consumers.yaml``
unless a control is specifically about breaking one of them. So a change to the
shipped kind table is felt immediately by every control, rather than passing
against a stale copy of the rules.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from tools.vocabulary import load_registry
from tools.vocabulary.errors import RegistryInvalid

# tests/contracts/_helpers.py -> the git root (conftest.py put it on sys.path).
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_REGISTRY = REPO_ROOT / "domain-vocabulary"

# A file that exists in the synthetic repository root, for concepts to declare a
# consumer against. It sits under the `backend` surface's root.
CONSUMER_PATH = "ubb-platform/apps/example/models.py"

#: Sentinel for ``concept(values=ABSENT)`` — removes a field rather than setting
#: it to None, which is a different fault with a different code.
ABSENT = object()


#: The module that declares every outbox payload, and therefore every webhook.
PAYLOAD_SCHEMAS = "ubb-platform/apps/platform/events/schemas.py"


def events_whose_payload_declares(field):
    """The webhook names whose payload class carries ``field``.

    ``{event type, ...}``, read out of the payload module's own source,
    INHERITED FIELDS INCLUDED — a payload that takes a field from a shared base
    carries it on the wire exactly as one declaring it inline does, and a
    reader that could not see that would answer this question wrongly the day a
    base appeared. The four terminal stop events are the first such base and
    the reason this walk resolves them.

    Two reasons this is derived rather than written down, and both matter:

    **The names could not be spelled here.** The two events this field first
    rode were retired words with a ZERO ledger seat on this surface, so a module
    naming one failed the sweep for a word it did not own. Deriving was the
    first of the three techniques the sweep's own plan prefers, and the one
    that leaves nothing behind. Their successors are free words and the
    constraint is gone — but the derivation stays, on the second reason.

    **It is the comparison worth making anyway.** A caller pins what the
    published CONTRACT says about a field against what the PRODUCER declares —
    two encodings of one fact held to each other, which is this suite's whole
    job (#203). A hard-coded pair would agree with both right up until one of
    them moved.

    ⚠ IT WENT RED WHEN THE SPLIT LANDED, WHICH WAS THE POINT. The two events
    became four, every caller's expected set changed with them, and a person
    read the diff instead of a stale literal quietly still passing.

    Read with :mod:`ast` and never imported — this suite has no Django, which
    is the same rule the rename migration's own contract test states.
    """
    import ast

    source = (REPO_ROOT / PAYLOAD_SCHEMAS).read_text(encoding="utf-8")
    classes = {node.name: node for node in ast.parse(source).body
               if isinstance(node, ast.ClassDef)}

    def declares(name, seen=None):
        """``field`` is annotated on this class or on a base it names here.

        Bases outside this module are not resolved and cannot be: they are
        never dataclasses carrying payload fields, and a walk that followed
        them would be guessing at source it has not read.
        """
        seen = seen or set()
        if name in seen or name not in classes:
            return False
        seen.add(name)
        node = classes[name]
        if any(isinstance(statement, ast.AnnAssign)
               and isinstance(statement.target, ast.Name)
               and statement.target.id == field
               for statement in node.body):
            return True
        return any(isinstance(base, ast.Name) and declares(base.id, seen)
                   for base in node.bases)

    found = set()
    for name, node in classes.items():
        event_type = None
        for statement in node.body:
            if (isinstance(statement, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "EVENT_TYPE"
                            for t in statement.targets)
                    and isinstance(statement.value, ast.Constant)):
                event_type = statement.value.value
        if event_type and declares(name):
            found.add(event_type)
    return found


#: The migration ledger, for the two modules that hold a migration's own map to
#: the debts still recorded against the gate it pays.
LEDGER_PATH = "gates/migration-ledger.yaml"


def module_literal(path, name):
    """The value bound to a module-level ``name`` in ``path``, as a literal.

    ``ast.literal_eval`` rather than an import, for the reason #204 gives: a
    migration is read and never imported, so nothing here needs Django
    settings, a database or the app registry — and a migration's map is a dict
    of strings, which is exactly what a literal reader is for.
    """
    import ast

    source = (REPO_ROOT / path).read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        for target in getattr(node, "targets", []):
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{path} declares no module-level `{name}`")


def the_webhook_catalogue():
    """The registry's `webhook_event_type` concept — its values and the names
    it retired.

    Shared by the two migration modules that hold a stored-data map to it. They
    make different assertions (one map is one-to-one and the other one-to-two)
    but they read the same oracle, and two copies of one read are how the two
    come to disagree about what the registry says.
    """
    return load_registry(REPO_ROOT / "domain-vocabulary").concepts[
        "webhook_event_type"]


def names_a_gate_still_owes(gate):
    """The `found` values of every ledger entry recorded against ``gate``.

    What a migration may NOT move: a debt is paid by rewriting the name AND
    deleting its entry, in one act, so an entry surviving a rewrite would
    excuse a violation that no longer exists.
    """
    document = yaml.safe_load(
        (REPO_ROOT / LEDGER_PATH).read_text(encoding="utf-8"))
    return {entry["found"] for entry in document["entries"]
            if entry["gate"] == gate}


def concept(**overrides):
    """A minimal valid `closed` concept — the baseline each control mutates."""
    body = {
        "kind": "closed",
        "summary": "A synthetic concept, used to exercise the compiler.",
        "values": ["alpha", "beta"],
        "label_key_prefix": "synthetic",
        "consumers": [{"surface": "backend", "path": CONSUMER_PATH}],
    }
    body.update(overrides)
    return {key: value for key, value in body.items() if value is not ABSENT}


def write_registry(tmp_path, *, concepts, schema=None, consumers=None,
                   consumer_files=(CONSUMER_PATH,), make_concepts_dir=True,
                   surface_roots=None):
    """Write a registry under ``tmp_path`` and return its directory.

    ``concepts`` maps a domain file name to either a mapping (dumped as YAML) or
    a raw string (written verbatim — the only way to express faults YAML itself
    would otherwise hide, such as a key repeated in one mapping).

    Surface roots are created from the consumers document, so a synthetic
    registry resolves the way the real one does. Pass ``surface_roots`` to
    create only some of them, which is how a control about a root that has
    vanished gets a root that is genuinely absent.
    """
    registry_dir = tmp_path / "domain-vocabulary"
    registry_dir.mkdir(exist_ok=True)

    schema_text = _text(schema) if schema is not None else _real("schema.yaml")
    (registry_dir / "schema.yaml").write_text(schema_text, encoding="utf-8")

    consumers_text = (_text(consumers) if consumers is not None
                      else _real("consumers.yaml"))
    (registry_dir / "consumers.yaml").write_text(consumers_text, encoding="utf-8")
    roots = (_declared_roots(consumers_text) if surface_roots is None
             else surface_roots)
    for root in roots:
        (tmp_path / root).mkdir(parents=True, exist_ok=True)

    for relative in consumer_files:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# a synthetic consumer\n", encoding="utf-8")

    if make_concepts_dir:
        concepts_dir = registry_dir / "concepts"
        concepts_dir.mkdir(exist_ok=True)
        for name, document in concepts.items():
            (concepts_dir / name).write_text(_text(document), encoding="utf-8")

    return registry_dir


def load(tmp_path, **kwargs):
    """Build a synthetic registry and load it. Fails the test if it is invalid."""
    return load_registry(write_registry(tmp_path, **kwargs), tmp_path)


def rejection(tmp_path, **kwargs):
    """Build a synthetic registry and return the :class:`RegistryInvalid` it
    must raise. Fails the test if the registry loads — which is the shape that
    makes these negative controls, rather than assertions about a passing run."""
    registry_dir = write_registry(tmp_path, **kwargs)
    with pytest.raises(RegistryInvalid) as raised:
        load_registry(registry_dir, tmp_path)
    return raised.value


def copy_real_registry(tmp_path):
    """A verbatim copy of the SHIPPED registry.

    Some controls have to mutate exactly one thing about the *real* registry
    and show the consequence — a synthetic registry cannot do that, because it
    would differ from the committed artifacts for a hundred reasons at once and
    prove nothing about the one change under test.
    """
    destination = tmp_path / "domain-vocabulary"
    shutil.copytree(REAL_REGISTRY, destination)
    return destination


def redeclare(registry_dir, file_name, concept_name, **changes):
    """Rewrite one concept in a copied registry.

    The domain file is round-tripped through YAML, so its comments do not
    survive. That costs nothing: the compiler reads data, and every generator
    renders from the compiled concepts rather than from the file's text — so a
    control that changed only formatting would correctly produce no diff.
    """
    path = registry_dir / "concepts" / file_name
    assert path.is_file(), f"{file_name} is not a domain file in this registry"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    # #202 moves concepts between domain files. A control that quietly stopped
    # mutating anything would keep passing while proving nothing, so say which
    # concept moved rather than raising a bare KeyError from a dict lookup.
    assert concept_name in document, (
        f"{concept_name} is no longer declared in {file_name} — the control "
        f"must name the file it moved to"
    )
    document[concept_name].update(changes)
    path.write_text(_text(document), encoding="utf-8")


def _text(document):
    if isinstance(document, str):
        return document
    return yaml.safe_dump(document, sort_keys=False)


def _real(name):
    """The shipped file, so a control runs against the rules actually in force."""
    return (REAL_REGISTRY / name).read_text(encoding="utf-8")


def _declared_roots(consumers_text):
    document = yaml.safe_load(consumers_text)
    if not isinstance(document, dict):
        return []
    surfaces = document.get("surfaces")
    if not isinstance(surfaces, dict):
        return []
    return [body["root"] for body in surfaces.values()
            if isinstance(body, dict) and isinstance(body.get("root"), str)]
