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
