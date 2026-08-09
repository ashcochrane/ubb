"""Synthetic gate programmes, for putting the compiler through its real entry point.

Every negative control here builds a complete programme on disk — a `gates/`
directory, a CI workflow and the test files an `installed` row points at — and
loads it with :func:`tools.gates.load_programme`, the same function CI and the
CLI call. Nothing patches the compiler's internals, because a test that mocks
the thing under test can only ever reproduce its mistakes.

The synthetic programmes use the **real** ``schema.yaml`` and ``slices.yaml``
unless a control is specifically about breaking one of them. So a change to the
shipped status table or a slice being declared landed is felt immediately by
every control, rather than passing against a stale copy of the rules.
"""

import shutil
import subprocess

import pytest
import yaml

from _helpers import REPO_ROOT
from tools.gates import load_programme
from tools.gates.errors import GatesInvalid

REAL_GATES = REPO_ROOT / "gates"

WORKFLOW_PATH = ".github/workflows/ci.yml"

#: The synthetic suite's root, and the file a legal `installed` row names.
SUITE_ROOT = "tests/contracts"
TEST_FILE = f"{SUITE_ROOT}/test_synthetic.py"
TEST_NODE = f"{TEST_FILE}::test_alpha"

#: A workflow that REQUIRES both of its jobs: on push and pull request, no
#: filters, no `if:`, no `continue-on-error`. Controls mutate one thing about
#: it and show the consequence.
def workflow_document(**overrides):
    document = {
        "name": "CI",
        "on": {"push": None, "pull_request": None},
        "jobs": {
            "contracts": {
                "runs-on": "ubuntu-latest",
                "steps": [{"name": "Contract suite",
                           "run": "python -m pytest tests/contracts"}],
            },
            "checks": {
                "runs-on": "ubuntu-latest",
                "steps": [{"name": "Named step", "run": "echo checking"}],
            },
        },
    }
    document.update(overrides)
    return document


#: A test module whose functions the synthetic suite genuinely collects — plus
#: one that is skipped and one inside a class, because both are cases the
#: collection rules have to get right rather than guess at.
TEST_MODULE = '''\
import pytest


def test_alpha():
    assert True


@pytest.mark.skip(reason="a gate that does not run is not installed")
def test_skipped():
    assert True


class TestThings:
    def test_in_a_class(self):
        assert True


def helper_not_a_test():
    return True
'''


def suites(**overrides):
    document = {
        "contracts": {
            "summary": "The synthetic contract suite.",
            "job": "contracts",
            "step": "Contract suite",
            "root": SUITE_ROOT,
        },
    }
    document.update(overrides)
    return document


#: The slice the synthetic rows are owed by. It MUST be one that has not landed:
#: a baseline row owed by a landed slice is rejected for `landed_slice_owns_gate`
#: in every control, none of which is testing that. Slice 8 is the cutover, the
#: last thing in the programme to land, so this outlives every slice that could
#: invalidate it — and `test_a_landed_slice_may_not_still_owe_a_gate` mutates
#: THIS slice, so the two cannot drift apart.
UNLANDED_SLICE = "slice_8"


def owned(slice_key=UNLANDED_SLICE, **overrides):
    """A minimal valid `owned_by_<slice>` row — the baseline most rows use."""
    body = {
        "statement": "A synthetic gate, used to exercise the compiler.",
        "oracle": "the synthetic oracle",
        "status": f"owned_by_{slice_key}",
        "blocked_on": "the subject does not exist yet",
    }
    body.update(overrides)
    return body


def installed(sites=None, **overrides):
    """A minimal valid `installed` row, enforced by a node the suite collects."""
    body = {
        "statement": "A synthetic gate that runs.",
        "oracle": "the synthetic oracle",
        "status": "installed",
        "enforced_by": sites if sites is not None else [
            {"suite": "contracts", "node": TEST_NODE},
        ],
    }
    body.update(overrides)
    return body


def obligation(**overrides):
    body = {
        "statement": "A synthetic obligation nobody can automate.",
        "oracle": "none — this is the human half",
        "status": "deferred_obligation",
        "reason": "it requires judgement about meaning",
        "owner_role": "the accountable engineering owner",
        "evidence_required": "a record naming the commit and the scenarios",
    }
    body.update(overrides)
    return body


def gates(**overrides):
    """All twenty-seven rows, owed by slice 0, with ``overrides`` applied.

    The inventory is the real one, so a control that adds or drops a row is
    testing the real rule rather than a convenient subset.
    """
    rows = {f"G{number}": owned() for number in range(1, 28)}
    rows.update(overrides)
    return rows


#: Bound before ``write_programme``'s parameters shadow the names.
_default_gates, _default_suites = gates, suites


def write_programme(tmp_path, *, gates=None, obligations=None, suites=None,
                    schema=None, slices=None, ledger=None, exceptions=None,
                    workflow=None, files=None, manifest=None,
                    make_suite_root=True):
    """Write a whole synthetic repository under ``tmp_path``; return its root.

    Every document may be a mapping (dumped as YAML) or a raw string (written
    verbatim — the only way to express faults YAML itself would otherwise hide,
    such as a key repeated in one mapping).
    """
    gates_dir = tmp_path / "gates"
    gates_dir.mkdir(exist_ok=True)

    _write(gates_dir / "schema.yaml", schema, real("schema.yaml"))
    _write(gates_dir / "slices.yaml", slices, real("slices.yaml"))
    _write(gates_dir / "manifest.yaml", manifest,
           {"version": 1,
            "suites": _default_suites() if suites is None else suites,
            "gates": _default_gates() if gates is None else gates,
            "obligations": {} if obligations is None else obligations})
    _write(gates_dir / "migration-ledger.yaml", ledger,
           {"version": 1, "entries": [], "seeding_authorisations": []})
    _write(gates_dir / "permanent-exceptions.yaml", exceptions,
           {"version": 1, "exceptions": []})

    _write(tmp_path / WORKFLOW_PATH, workflow, workflow_document())

    if make_suite_root:
        _write(tmp_path / TEST_FILE, TEST_MODULE, None)
    for relative, content in (files or {}).items():
        _write(tmp_path / relative, content, None)

    return gates_dir


def load(tmp_path, **kwargs):
    """Build a synthetic programme and load it. Fails the test if it is invalid."""
    return load_programme(write_programme(tmp_path, **kwargs), tmp_path)


def rejection(tmp_path, **kwargs):
    """Build a synthetic programme and return the :class:`GatesInvalid` it must
    raise. Fails the test if it loads — which is the shape that makes these
    negative controls, rather than assertions about a passing run."""
    gates_dir = write_programme(tmp_path, **kwargs)
    with pytest.raises(GatesInvalid) as raised:
        load_programme(gates_dir, tmp_path)
    return raised.value


def copy_real_programme(tmp_path):
    """The SHIPPED gates directory, with everything its claims resolve against.

    Some controls have to mutate exactly one thing about the *real* manifest and
    show the consequence — a synthetic programme cannot do that, because it
    would differ from the shipped one for a hundred reasons at once.

    What is copied is derived from the manifest itself: every declared suite's
    root and configuration, and every file an `installed` row names. So a row
    added by a later slice is carried here on the day it is added, rather than
    quietly falling outside a hard-coded list.
    """
    shutil.copytree(REAL_GATES, tmp_path / "gates")
    target = tmp_path / WORKFLOW_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / WORKFLOW_PATH, target)

    manifest = yaml.safe_load((REAL_GATES / "manifest.yaml").read_text("utf-8"))
    wanted = set()
    for suite in (manifest.get("suites") or {}).values():
        (tmp_path / suite["root"]).mkdir(parents=True, exist_ok=True)
        if suite.get("config"):
            wanted.add(suite["config"])
    for row in (manifest.get("gates") or {}).values():
        for site in row.get("enforced_by") or []:
            if "node" in site:
                wanted.add(site["node"].split("::")[0])
    for relative in wanted:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / relative, destination)
    return tmp_path / "gates"


def git(repo, *arguments):
    """Run one git command in ``repo``, failing loudly rather than silently."""
    result = subprocess.run(["git", "-C", str(repo), *arguments],
                            capture_output=True, text=True)
    assert result.returncode == 0, (
        f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _write(path, document, default):
    if document is None:
        if default is None:
            return
        document = default
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (document if isinstance(document, str)
            else yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    path.write_text(text, encoding="utf-8")


def real(name):
    """The shipped file, so a control runs against the rules actually in force."""
    return (REAL_GATES / name).read_text(encoding="utf-8")
