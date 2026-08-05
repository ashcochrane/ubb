"""This suite gates, and that is checked rather than intended (ADR-0008 §7).

Every failure this repository has shipped in its own gates was the same one: a
check that existed but could not fail anything. The forbidden-term sweep wired
`continue-on-error`. The only end-to-end money test sat in no CI job at all and
called a retired endpoint for six months. Three SDK tests patched the transport,
so the mock reproduced the generator's mistake instead of contradicting it.

So the contract suite's own enforcement is a test, in two parts:

1. **It runs, and it is required.** A named job in the workflow runs it, on both
   push and pull request, with no `continue-on-error`, no `if:` condition, and
   no path filter — because a filter that never mentions a seventh input is
   exactly how a gate stops running while the board stays green (#158 §16).
2. **It runs without Django.** Nothing under `tests/contracts/` or
   `tools/` imports Django, the settings module or a platform package. The CI
   job installs two pinned packages and nothing else, so this is structurally
   true there; the walk below makes it true locally too, and immediately.

Both halves carry negative controls, because a gate that has never been shown to
fail is an assertion, not evidence.
"""

import ast
from pathlib import Path

import pytest
import yaml

from _helpers import REPO_ROOT
from tools.gates.enforcement import CONTRACT_COMMAND, enforcement_faults, triggers

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Importing any of these pulls in Django settings, a database connection, or
# both. `config` is the settings package; `apps` and `core` are the platform's.
DJANGO_ROOTS = ("django", "config", "apps", "core")

SCANNED_TREES = ("tests/contracts", "tools")


# ---------------------------------------------------------------------------
# 1. The job exists, and it is required
# ---------------------------------------------------------------------------
#
# `enforcement_faults` used to live here. #201 moved it to
# `tools/gates/enforcement.py`, because the gate manifest asks the same question
# about every check that claims to be installed — and two copies of "is this
# gate armed?" is exactly the second hand-maintained source this programme
# exists to refuse. The controls below still exercise it from here, against the
# workflow it was written for.


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_workflow_requires_the_contract_suite(workflow):
    assert enforcement_faults(workflow) == []


def test_the_workflow_was_actually_read(workflow):
    """Vacuity guard: prove the parse produced the real document, not an empty
    mapping that would make every check above pass on nothing.

    It names only the `contracts` job. Pinning the unrelated jobs beside it
    would mean renaming one of them turns the *registry* gate red, which is a
    false signal — and a gate that cries wolf gets weakened, not obeyed.
    """
    assert isinstance(workflow.get("jobs"), dict)
    assert "contracts" in workflow["jobs"], "the contracts job is missing"
    assert len(workflow["jobs"]) > 1, "only one job parsed — suspect the parse"
    assert isinstance(triggers(workflow), dict), "the `on:` block did not parse"


def test_the_contract_job_installs_no_django(workflow):
    """The strongest form of "runs without Django": the job cannot import it,
    because it is not installed. If this job ever installs the platform lock,
    the Django-free claim below becomes unfalsifiable."""
    steps = workflow["jobs"]["contracts"]["steps"]
    installs = " ".join(str(step.get("run", "")) for step in steps)
    assert "tests/contracts/requirements.txt" in installs
    assert "requirements.lock.txt" not in installs


# --- negative controls: the predicate flags a disarmed gate -----------------

def _synthetic(job_extra=None, step_extra=None, triggers=None):
    return {
        "on": triggers if triggers is not None else {"push": None,
                                                     "pull_request": None},
        "jobs": {
            "contracts": {
                **(job_extra or {}),
                "steps": [{"run": f"python -m {CONTRACT_COMMAND}",
                           **(step_extra or {})}],
            }
        },
    }


def test_negative_control_a_continue_on_error_job_is_flagged():
    faults = enforcement_faults(_synthetic(job_extra={"continue-on-error": True}))
    assert any("continue-on-error" in fault for fault in faults)


def test_negative_control_a_continue_on_error_step_is_flagged():
    faults = enforcement_faults(_synthetic(step_extra={"continue-on-error": True}))
    assert any("continue-on-error" in fault for fault in faults)


def test_negative_control_a_conditional_job_is_flagged():
    faults = enforcement_faults(_synthetic(job_extra={"if": "github.ref == 'refs/heads/main'"}))
    assert any("conditional" in fault for fault in faults)


def test_negative_control_a_path_filtered_trigger_is_flagged():
    """The gate's inputs are the registry, the compiler, the suite and the
    workflow. A filter listing three of them disarms it for the fourth."""
    faults = enforcement_faults(_synthetic(triggers={
        "push": {"paths": ["ubb-platform/**"]},
        "pull_request": None,
    }))
    assert any("paths" in fault for fault in faults)


def test_negative_control_a_missing_job_is_flagged():
    workflow = _synthetic()
    workflow["jobs"]["contracts"]["steps"] = [{"run": "echo hello"}]
    assert enforcement_faults(workflow) == [f"no job runs `{CONTRACT_COMMAND}`"]


def test_positive_control_a_plain_required_job_is_clean():
    assert enforcement_faults(_synthetic()) == []


def test_the_yaml_on_key_gotcha_is_handled():
    """`on:` parses to the boolean True under YAML 1.1. Reading only the string
    would report "no triggers" for every real GitHub workflow ever written."""
    parsed = yaml.safe_load("on:\n  push:\n  pull_request:\njobs: {}\n")
    assert True in parsed and "on" not in parsed
    assert set(triggers(parsed)) == {"push", "pull_request"}


# ---------------------------------------------------------------------------
# 2. Nothing here imports Django
# ---------------------------------------------------------------------------

def _python_files():
    for tree in SCANNED_TREES:
        for path in sorted((REPO_ROOT / tree).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def django_imports(source, label):
    """Every import in ``source`` that would drag Django in.

    Walks the whole tree, so a lazy import inside a function body is caught
    exactly like a module-scope one — the historical erosion vector the product
    boundary walker was built to close.
    """
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root in DJANGO_ROOTS:
                hits.append(f"{label}:{node.lineno} imports {name}")
    return hits


def test_nothing_in_the_contract_suite_imports_django():
    violations = []
    scanned = []
    for path in _python_files():
        label = path.relative_to(REPO_ROOT).as_posix()
        scanned.append(label)
        violations += django_imports(path.read_text(encoding="utf-8"), label)
    assert not violations, "\n" + "\n".join(violations)

    # Vacuity guard: a broken path would otherwise scan nothing and pass.
    assert len(scanned) >= 6, f"only scanned {len(scanned)} files: {scanned}"
    for expected in ("tests/contracts/conftest.py",
                     "tests/contracts/test_vocabulary_registry.py",
                     "tools/vocabulary/compiler.py"):
        assert expected in scanned, f"walker did not visit {expected}"


def test_negative_control_a_django_import_is_flagged():
    assert django_imports("from django.db import models\n", "x.py")


def test_negative_control_a_lazy_django_import_is_flagged():
    assert django_imports("def f():\n    import config.settings\n", "x.py")


def test_positive_control_ordinary_imports_are_not_flagged():
    assert not django_imports("import yaml\nfrom pathlib import Path\n", "x.py")
    # `coreapi` is not `core`: prefix matching must not confuse sibling names.
    assert not django_imports("import coreapi\n", "x.py")
