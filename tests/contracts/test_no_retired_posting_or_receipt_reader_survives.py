"""G21 #1 and #3, the half that reads the CODE (#153 §13.5; #190 §0.3 point 10).

#153 §13.5's cutover assertions are about what the system does with old facts,
and each has a behavioural half in the platform suite
(`ubb-platform/api/v1/tests/test_the_cutover_assertions.py`), which plants an
old fact and shows it reaches nothing. This module is the other half: that no
READER PATH for an old fact survives in production code, so the behaviour is
not an accident of which reads the tests happened to drive.

**#1 — "No old posting reaches a balance or a report."** The retired posting
structures are the posting's table and the columns the old migration chain
removed or renamed away (derived from that chain's history, each pinned below
with the migration that retired it), together with the names the vocabulary
registry retires for the same columns — read from the registry rather than
spelled here, because the forbidden-term sweep refuses them in every living
file, this one included. None may be a field of the posting model (so no ORM
reader can name one: Django refuses a field the model lacks), and no raw SQL in
production code may read the old table or name a retired column beside
`ubb_posting`.

**#3 — "No legacy pricing provenance is read."** The receipts module declares
ONE schema version and every production comparison of a receipt's declared
version is against it; no production code names the receipt's retired name.

Each check is a function over source text, so the planted violations below go
through exactly what the assertions over the real tree go through.
"""

import ast
import re

from _helpers import REPO_ROOT
from tools.vocabulary import load_registry

PLATFORM = REPO_ROOT / "ubb-platform"
POSTING_MODELS = "ubb-platform/apps/metering/usage/models.py"
RECEIPTS = "ubb-platform/apps/metering/pricing/receipts.py"

#: THE POSTING'S RETIRED STRUCTURES THAT NO REGISTRY ENTRY SWEEPS, each with the
#: migration of the old chain (deleted by the cutover, #190) that retired it.
PINNED_RETIRED_POSTING_STRUCTURES = {
    "ubb_usage_event": "the posting's table from usage/0001 until usage/0030 "
                       "renamed it `ubb_posting`",
    "invoice_id": "usage/0007 removed the posting's invoice link",
    "group_keys": "usage/0017 renamed it; usage/0033 folded it into the one "
                  "open bag",
    "cost_micros": "usage/0018 removed the single cost column",
    "properties": "usage/0018 removed the second open bag",
    "run_id": "usage/0026 renamed the unit-of-work link to `task`",
    "agent_id": "usage/0028 removed the three attribution columns",
    "product_id": "usage/0028",
    "service_id": "usage/0028",
    "dim1": "usage/0035 renamed the six slots to `grouping_field_1`..`_6`",
    "dim2": "usage/0035", "dim3": "usage/0035", "dim4": "usage/0035",
    "dim5": "usage/0035", "dim6": "usage/0035",
}

#: THE POSTING'S RETIRED STRUCTURES THE REGISTRY SWEEPS, by the concept that
#: retired them: the inline measurement bag (usage/0018, usage/0031), the
#: second open bag (usage/0033), the second correlation value (usage/0043) and
#: the receipt's earlier name (usage/0042) are retired aliases of these four
#: concepts; the inline unit total (usage/0032) is a retired SENSE of the first.
#: Every alias of each is held absent — wider than the four columns, which an
#: absence check can afford.
REGISTRY_CONCEPTS = ("measurement_key", "metadata_key", "idempotency_key",
                     "pricing_receipt_subject_type")
RECEIPT_CONCEPT = "pricing_receipt_subject_type"


def registry_retired_posting_structures():
    registry = load_registry(REPO_ROOT / "domain-vocabulary", REPO_ROOT)
    names = {alias: f"retired alias of `{concept}`"
             for concept in REGISTRY_CONCEPTS
             for alias in registry.concepts[concept].retired_aliases}
    for sense in registry.concepts["measurement_key"].retired_senses:
        names[sense.term] = "retired sense of `measurement_key`"
    return names


def retired_posting_structures():
    return {**PINNED_RETIRED_POSTING_STRUCTURES,
            **registry_retired_posting_structures()}


def production_modules():
    """Every production Python module of the platform: not a test, not a
    migration (the fresh set's rules carry SQL G20 and the rules module hold),
    not the virtualenv."""
    for path in sorted(PLATFORM.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        parts = path.relative_to(PLATFORM).parts
        if (parts[0] in (".venv", "scripts", "conformance", "docs")
                or "tests" in parts or "migrations" in parts):
            continue
        yield rel, path.read_text(encoding="utf-8-sig")


def _strings(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def old_posting_readers(sources, retired):
    """Raw SQL that reads the old table, or names a retired column beside
    `ubb_posting`: one sentence per finding."""
    table, columns = "ubb_usage_event", set(retired) - {"ubb_usage_event"}
    faults = []
    for rel, text in sources:
        for line, value in _strings(ast.parse(text)):
            if re.search(rf"\b{table}\b", value):
                faults.append(f"{rel}:{line} reads the old posting table")
            if re.search(r"\bubb_posting\b", value):
                for column in sorted(columns):
                    if re.search(rf"\b{re.escape(column)}\b", value):
                        faults.append(f"{rel}:{line} names the retired "
                                      f"posting column {column!r}")
    return faults


def model_fields(text, model):
    """The field names a model class assigns (`name = models.X(...)`)."""
    for node in ast.parse(text).body:
        if isinstance(node, ast.ClassDef) and node.name == model:
            return {target.id
                    for statement in node.body if isinstance(statement, ast.Assign)
                    and isinstance(statement.value, ast.Call)
                    and "models." in ast.unparse(statement.value.func)
                    for target in statement.targets if isinstance(target, ast.Name)}
    raise AssertionError(f"no class {model}")


def retired_fields_on_the_posting(text, retired):
    fields = model_fields(text, "Posting")
    return sorted(name for name in fields
                  if name in retired or f"{name}_id" in retired)


def legacy_receipt_readers(sources, retired_receipt_names):
    """Every way production code could still read an older receipt: a second
    schema-version constant in the receipts module, a comparison of a declared
    version against anything but the one constant, or the retired name."""
    faults = []
    for rel, text in sources:
        tree = ast.parse(text)
        if rel == RECEIPTS:
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (isinstance(target, ast.Name)
                                and "SCHEMA_VERSION" in target.id
                                and target.id != "RECEIPT_SCHEMA_VERSION"):
                            faults.append(f"{rel}:{node.lineno} declares a "
                                          f"second receipt shape {target.id}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and \
                    "receipt_schema_version" in ast.unparse(node):
                for side in [node.left, *node.comparators]:
                    if isinstance(side, ast.Constant) and \
                            not isinstance(side.value, str):
                        faults.append(f"{rel}:{node.lineno} compares a receipt's "
                                      f"version with {side.value!r}")
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(".get") \
                    and node.args and isinstance(node.args[0], ast.Constant) \
                    and node.args[0].value == "receipt_schema_version" \
                    and len(node.args) > 1:
                faults.append(f"{rel}:{node.lineno} reads a missing receipt "
                              f"version as a default shape")
        for line, value in _strings(tree):
            for name in retired_receipt_names:
                if re.search(rf"\b{name}\b", value):
                    faults.append(f"{rel}:{line} names the receipt's retired "
                                  f"name")
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in retired_receipt_names:
                faults.append(f"{rel}:{node.lineno} reads the receipt's retired "
                              f"name")
    return faults


def retired_receipt_names():
    registry = load_registry(REPO_ROOT / "domain-vocabulary", REPO_ROOT)
    return set(registry.concepts[RECEIPT_CONCEPT].retired_aliases)


# ---------------------------------------------------------------------------
# #1 — no live reader path for an old posting
# ---------------------------------------------------------------------------

def test_the_retired_posting_structures_are_derived_not_assumed():
    """Vacuity guard: the set is the pinned history PLUS what the registry
    retires, and both halves are there — an empty registry read would leave
    the swept columns unchecked while every assertion below stayed green."""
    derived = registry_retired_posting_structures()
    assert len(derived) >= 5, derived
    held = set(retired_posting_structures())
    assert set(PINNED_RETIRED_POSTING_STRUCTURES) <= held
    assert set(derived) <= held, (
        f"the registry's retired names {sorted(set(derived) - held)} are read "
        f"but not held absent")
    assert retired_receipt_names(), "the receipt's retired name was not read"


def test_the_posting_model_declares_no_retired_structure():
    text = (REPO_ROOT / POSTING_MODELS).read_text(encoding="utf-8-sig")
    assert len(model_fields(text, "Posting")) > 30
    assert retired_fields_on_the_posting(text, retired_posting_structures()) == []


def test_no_production_sql_reads_an_old_posting():
    sources = list(production_modules())
    assert len(sources) > 200, "the walk did not read the platform"
    assert old_posting_readers(sources, retired_posting_structures()) == []


def test_planted_a_reader_of_the_old_table_is_found():
    planted = [("ubb-platform/apps/x/reports.py",
                'SQL = "SELECT SUM(billed_cost_micros) FROM ubb_usage_event"\n')]
    assert old_posting_readers(planted, retired_posting_structures()) == [
        "ubb-platform/apps/x/reports.py:1 reads the old posting table"]


def test_planted_a_retired_column_beside_the_posting_table_is_found():
    swept = sorted(registry_retired_posting_structures())[0]
    planted = [("ubb-platform/apps/x/reports.py",
                f'SQL = "SELECT {swept} FROM ubb_posting"\n'
                'OK = "SELECT billed_cost_micros FROM ubb_posting"\n')]
    assert old_posting_readers(planted, retired_posting_structures()) == [
        f"ubb-platform/apps/x/reports.py:1 names the retired posting column "
        f"{swept!r}"]


def test_planted_a_retired_field_on_the_posting_is_found():
    planted = ("from django.db import models\n"
               "class Posting(models.Model):\n"
               "    group_keys = models.JSONField()\n"
               "    run = models.ForeignKey('work.Task', on_delete=models.CASCADE)\n"
               "    metadata = models.JSONField()\n")
    assert retired_fields_on_the_posting(planted, retired_posting_structures()) == [
        "group_keys", "run"]


# ---------------------------------------------------------------------------
# #3 — no legacy pricing provenance reader
# ---------------------------------------------------------------------------

def test_no_production_code_reads_a_legacy_receipt():
    sources = list(production_modules())
    assert any(rel == RECEIPTS for rel, _ in sources), "the receipts module was not read"
    assert legacy_receipt_readers(sources, retired_receipt_names()) == []


def test_planted_a_second_shape_constant_is_found():
    planted = [(RECEIPTS, "RECEIPT_SCHEMA_VERSION = 2\nLEGACY_SCHEMA_VERSION = 0\n")]
    assert legacy_receipt_readers(planted, set()) == [
        f"{RECEIPTS}:2 declares a second receipt shape LEGACY_SCHEMA_VERSION"]


def test_planted_a_dispatch_on_an_older_version_is_found():
    planted = [("ubb-platform/apps/x/read.py",
                "def read(r):\n"
                "    if r.get('receipt_schema_version', 0) == 1:\n"
                "        return r['legacy']\n")]
    assert legacy_receipt_readers(planted, set()) == [
        "ubb-platform/apps/x/read.py:2 compares a receipt's version with 1",
        "ubb-platform/apps/x/read.py:2 reads a missing receipt version as a "
        "default shape"]


def test_planted_a_read_of_the_receipts_retired_name_is_found():
    (name,) = sorted(retired_receipt_names())[-1:]
    planted = [("ubb-platform/apps/x/read.py",
                f"def read(posting):\n    return posting.{name}\n")]
    assert legacy_receipt_readers(planted, retired_receipt_names()) == [
        "ubb-platform/apps/x/read.py:2 reads the receipt's retired name"]
