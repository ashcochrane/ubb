"""The Code Builder's execution suite runs on every change, and can fail it
(#582; ADR-0008 §5 and §7, G25).

`tests/code_builder_execution/` takes a complete Blueprint through the
platform's route, renders it with `ubb-codegen`, writes it to disk unpatched
and runs it as a customer runs it against the real application. It is what
G25 will name when #184's flip installs that row, and until then this test is
what holds it armed. A suite like that is worth exactly as much as its place
in CI, so its enforcement is checked here, the way the renderer suite's is:

1. **Its step runs unconditionally and can fail the run** — no `if:`, no
   `continue-on-error`, on a workflow with no path filter, in a job of its
   own (`code-builder-execution`), so no unrelated step failing ahead of it
   can stop it running. A filter could never name every input that changes
   what is generated and run: the renderer, the contract, the SDK, the
   platform and the registry all do (#158 §7.3). The job's check keeps its
   name, `code-builder-execution`, because main's required checks name it:
   a rename, or a display name, would leave the requirement naming a check
   nothing reports (owner's review of #602). Making it required is a
   repository setting this suite cannot hold; renaming the job is a
   deliberate change to that setting too.
2. **The step runs what its name says**, found by the command and not only
   by the name.
3. **The job can run it**: the application's Postgres and Redis, DEBUG True
   (False redirects every plain-http request, which neither curl nor the SDK
   follows), the platform and the SDK installed, Node to render, and a step
   that checks for Node and Docker — all before the suite.
4. **Nothing is silenced in the suite's source**: a skipped or expected-to-
   fail case leaves the step green over less than it claims.
5. **Every image it runs a shell in is pinned**: each `FROM` by digest, each
   fetched file by checksum, and nothing installed by a package manager, so
   the machines it proves the file on are the same on every run.

Claims 1 to 4 each carry negative controls, through the same predicate the
real workflow and the real sources are read with.
"""
import re

import yaml

from _helpers import REPO_ROOT
from tools.gates.enforcement import (
    collection_faults, step_faults, trigger_faults)

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SUITE = REPO_ROOT / "tests" / "code_builder_execution"
SUITE_ROOT = "tests/code_builder_execution"
SUITE_CONFIG = f"{SUITE_ROOT}/pytest.ini"

JOB = "code-builder-execution"
STEP = ("Code Builder execution — complete artifacts run unmodified against "
        "the real application")
COMMAND = "python -m pytest tests/code_builder_execution"

TOOLS = "Execution tools — what renders the files and runs them"
TOOL_CHECKS = ("node --version", "docker version")
INSTALLS = ("pip install -r ubb-platform/requirements.lock.txt",
            "pip install -e ./ubb-sdk")
SERVICES = ("postgres", "redis")
NODE = "actions/setup-node"

#: A case taken out of the run where it is written.
SILENCER = re.compile(
    r"pytest\.(?:mark\.)?(?:skip|skipif|xfail|importorskip)\b")

#: The tests the suite exists for, each of which must stay collected.
NODES = (
    f"{SUITE_ROOT}/test_every_scenario_runs_unmodified.py"
    "::test_a_scenario_runs_unmodified",
    f"{SUITE_ROOT}/test_preflight_refuses_before_any_request.py"
    "::test_a_machine_without_a_tool_it_needs_is_refused_before_any_request",
    f"{SUITE_ROOT}/test_the_shell_matrix.py"
    "::test_only_bash_3_2_fails_and_only_the_form_decided_against",
    f"{SUITE_ROOT}/test_the_harness_runs_only_what_was_rendered.py"
    "::test_a_changed_artifact_is_refused_before_the_run_starts",
)


def _index(steps, predicate):
    found = [index for index, step in enumerate(steps) if predicate(step)]
    return found[0] if found else None


def execution_faults(workflow):
    """Every reason `workflow` does not require the execution suite."""
    faults = trigger_faults(workflow)
    faults += step_faults(workflow, JOB, STEP)
    job = (workflow.get("jobs") or {}).get(JOB) or {}
    steps = job.get("steps") or []
    # The check GitHub reports is named for the job, and main's required
    # checks name it: a display name would report the job under another.
    if "name" in job and job["name"] != JOB:
        faults.append(f"job `{JOB}` reports its check as `{job['name']}`, "
                      f"and main's required checks name `{JOB}`")

    suite = _index(steps, lambda step: step.get("name") == STEP)
    if suite is not None and str(steps[suite].get("run", "")).strip() != COMMAND:
        faults.append(f"step `{STEP}` runs `{steps[suite].get('run')}`, "
                      f"not `{COMMAND}`")
    if suite is None:
        return faults

    for service in SERVICES:
        if service not in (job.get("services") or {}):
            faults.append(f"job `{JOB}` has no `{service}` service")
    if str((job.get("env") or {}).get("DEBUG")) != "True":
        faults.append(f"job `{JOB}` does not set DEBUG to True")

    for install in INSTALLS:
        at = _index(steps, lambda step: install in str(step.get("run", "")))
        if at is None:
            faults.append(f"job `{JOB}` never runs `{install}`")
        elif at > suite:
            faults.append(f"`{install}` runs after the suite that needs it")
    node = _index(steps, lambda step: str(step.get("uses", "")).startswith(NODE))
    if node is None:
        faults.append(f"job `{JOB}` never sets up Node")
    elif node > suite:
        faults.append("Node is set up after the suite that needs it")

    faults += step_faults(workflow, JOB, TOOLS)
    tools = _index(steps, lambda step: step.get("name") == TOOLS)
    if tools is not None:
        for check in TOOL_CHECKS:
            if check not in str(steps[tools].get("run", "")):
                faults.append(f"step `{TOOLS}` does not run `{check}`")
        if tools > suite:
            faults.append("the tools are checked for after the suite that "
                          "needs them")
    return faults


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_ci_runs_the_execution_suite_and_can_fail_on_it():
    assert execution_faults(_workflow()) == []


def test_the_suite_collects_the_tests_it_exists_for():
    """Vacuity guard: a step running a directory that collects nothing, or
    that collects around the tests that matter, is green over nothing."""
    for node in NODES:
        assert collection_faults(REPO_ROOT, SUITE_ROOT, SUITE_CONFIG,
                                 node) == [], node


def silencers(source):
    return [match.group(0) for match in SILENCER.finditer(source)]


def test_no_execution_test_is_skipped_or_expected_to_fail():
    read = sorted(SUITE.rglob("*.py"))
    silenced = [f"{path.name}: {marker}" for path in read
                for marker in silencers(path.read_text(encoding="utf-8"))]

    assert len(read) >= 9, [path.name for path in read]
    assert silenced == []


def image_faults(dockerfile):
    """Every way `dockerfile` builds something other than the same image
    every time. An instruction continued over several lines is read whole:
    a URL or a package manager on a continuation line is still there."""
    faults = []
    instructions = re.sub(r"\\\r?\n", " ", dockerfile)
    for line in instructions.splitlines():
        line = " ".join(line.split())
        words = line.split()
        if not words:
            continue
        if words[0] == "FROM" and "@sha256:" not in words[1]:
            faults.append(f"`{line}` is not pinned by digest")
        if words[0] == "ADD" and "://" in line and "--checksum=sha256:" not in line:
            faults.append(f"`{line}` fetches a file with no checksum")
        if words[0] == "RUN" and re.search(r"\b(apt-get|apt|apk|yum|dnf|pip)\b",
                                           line):
            faults.append(f"`{line}` installs from a package manager")
    return faults


def test_every_image_the_suite_runs_a_shell_in_is_pinned():
    dockerfiles = sorted((SUITE / "images").glob("*/Dockerfile"))

    assert len(dockerfiles) >= 7, dockerfiles
    assert {path.parent.name: image_faults(path.read_text(encoding="utf-8"))
            for path in dockerfiles} == {
        path.parent.name: [] for path in dockerfiles}


# --- negative controls: the predicates flag a disarmed suite -----------------

def _synthetic(step_extra=None, job_extra=None, triggers=None, run=COMMAND,
               drop=(), order="tools first", env=None, services=SERVICES):
    steps = [
        {"name": "install", "run": "\n".join(INSTALLS)},
        {"uses": "actions/setup-node@v4", "with": {"node-version": "22"}},
        {"name": TOOLS, "run": "\n".join(TOOL_CHECKS)},
        {"name": STEP, "run": run, **(step_extra or {})},
    ]
    steps = [step for step in steps
             if not any(dropped in str(step) for dropped in drop)]
    if order == "suite first":
        steps = [steps[-1], *steps[:-1]]
    return {
        "on": triggers if triggers is not None else {"push": None,
                                                     "pull_request": None},
        "jobs": {JOB: {**(job_extra or {}),
                       "services": {name: {} for name in services},
                       "env": env if env is not None else {"DEBUG": "True"},
                       "steps": steps}},
    }


def test_positive_control_a_plain_required_suite_is_clean():
    assert execution_faults(_synthetic()) == []


def test_negative_control_a_missing_job_is_flagged():
    workflow = _synthetic()
    workflow["jobs"] = {"another": workflow["jobs"][JOB]}
    assert any("no job named" in fault for fault in execution_faults(workflow))


def test_negative_control_a_check_reported_under_another_name_is_flagged():
    faults = execution_faults(_synthetic(job_extra={"name": "Seam C"}))
    assert faults == [f"job `{JOB}` reports its check as `Seam C`, and "
                      f"main's required checks name `{JOB}`"]


def test_negative_control_a_continue_on_error_step_is_flagged():
    faults = execution_faults(_synthetic(
        step_extra={"continue-on-error": True}))
    assert any("continue-on-error" in fault for fault in faults)


def test_negative_control_a_continue_on_error_job_is_flagged():
    faults = execution_faults(_synthetic(job_extra={"continue-on-error": True}))
    assert any("continue-on-error" in fault for fault in faults)


def test_negative_control_a_conditional_step_is_flagged():
    faults = execution_faults(_synthetic(
        step_extra={"if": "github.event_name == 'push'"}))
    assert any("conditional" in fault for fault in faults)


def test_negative_control_a_conditional_job_is_flagged():
    faults = execution_faults(_synthetic(job_extra={"if": "false"}))
    assert any("conditional" in fault for fault in faults)


def test_negative_control_a_path_filter_is_flagged():
    faults = execution_faults(_synthetic(triggers={
        "push": None, "pull_request": {"paths": ["apps/codegen/**"]}}))
    assert any("paths" in fault for fault in faults)


def test_negative_control_a_missing_suite_step_is_flagged():
    faults = execution_faults(_synthetic(drop=(STEP,)))
    assert any("no step named" in fault and STEP in fault for fault in faults)


def test_negative_control_a_step_running_something_else_is_flagged():
    faults = execution_faults(_synthetic(run="echo tested"))
    assert faults == [f"step `{STEP}` runs `echo tested`, not `{COMMAND}`"]


def test_negative_control_a_job_without_its_services_is_flagged():
    for service in SERVICES:
        kept = tuple(name for name in SERVICES if name != service)
        faults = execution_faults(_synthetic(services=kept))
        assert faults == [f"job `{JOB}` has no `{service}` service"], service


def test_negative_control_debug_left_false_is_flagged():
    faults = execution_faults(_synthetic(env={"DEBUG": "False"}))
    assert faults == [f"job `{JOB}` does not set DEBUG to True"]


def test_negative_control_a_missing_install_is_flagged():
    for install in INSTALLS:
        workflow = _synthetic()
        steps = workflow["jobs"][JOB]["steps"]
        steps[0] = {"name": "install",
                    "run": "\n".join(other for other in INSTALLS
                                     if other != install)}
        assert execution_faults(workflow) == [
            f"job `{JOB}` never runs `{install}`"], install


def test_negative_control_no_node_is_flagged():
    faults = execution_faults(_synthetic(drop=("setup-node",)))
    assert faults == [f"job `{JOB}` never sets up Node"]


def test_negative_control_setup_after_the_suite_is_flagged():
    faults = execution_faults(_synthetic(order="suite first"))
    assert sorted(faults) == sorted([
        *(f"`{install}` runs after the suite that needs it"
          for install in INSTALLS),
        "Node is set up after the suite that needs it",
        "the tools are checked for after the suite that needs them"])


def test_negative_control_a_tool_left_unchecked_is_flagged():
    for dropped in TOOL_CHECKS:
        workflow = _synthetic()
        steps = workflow["jobs"][JOB]["steps"]
        steps[2] = {"name": TOOLS, "run": "\n".join(
            check for check in TOOL_CHECKS if check != dropped)}
        assert execution_faults(workflow) == [
            f"step `{TOOLS}` does not run `{dropped}`"], dropped


def test_negative_control_a_silenced_case_is_flagged():
    for source in ("@pytest.mark.skip(reason='x')", "@pytest.mark.skipif(True)",
                   "@pytest.mark.xfail", "pytest.skip('no docker')",
                   "pytest.importorskip('docker')", "pytest.xfail('x')"):
        assert silencers(source), source


def test_positive_control_an_ordinary_case_is_not_flagged():
    assert silencers("def test_it_skips_nothing(): pass") == []


def test_negative_control_an_unpinned_image_is_flagged():
    assert image_faults("FROM debian:bookworm-slim") == [
        "`FROM debian:bookworm-slim` is not pinned by digest"]
    # In the form the real files use: the URL on a continuation line.
    assert image_faults(
        "ADD --chmod=755 \\\n    https://example.org/jq /usr/local/bin/jq") == [
        "`ADD --chmod=755 https://example.org/jq /usr/local/bin/jq` fetches a "
        "file with no checksum"]
    assert image_faults("RUN set -e \\\n  && apt-get install -y jq") == [
        "`RUN set -e && apt-get install -y jq` installs from a package manager"]
    assert image_faults(
        "FROM debian@sha256:" + "0" * 64) == []


def test_negative_control_each_real_image_unpinned_is_flagged():
    """The real files, each made unpinned: what the check reads is the form
    they are written in."""
    for path in sorted((SUITE / "images").glob("*/Dockerfile")):
        text = path.read_text(encoding="utf-8")
        unpinned = re.sub(r"@sha256:[0-9a-f]{64}", "", text)
        unpinned = unpinned.replace("--checksum=sha256:", "--checksum-was=")
        assert image_faults(unpinned), path.parent.name
        if "ADD " in text:
            assert any("no checksum" in fault
                       for fault in image_faults(unpinned)), path.parent.name
