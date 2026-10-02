"""The renderer's suite runs on every change, and can fail it (#577).

`ubb-codegen` turns an Integration Blueprint into the files a tenant is
handed, and what holds it to its rules is a suite that renders committed
Blueprints and then compiles and runs the Python it wrote. A suite like that
is worth exactly as much as its place in CI: the forbidden-term sweep once
ran under `continue-on-error`, and the only end-to-end money test once sat in
no job at all, and both stayed green for months.

So its enforcement is checked here, the way the contract suite's own is:

1. **Its three steps run unconditionally and can fail the run** — no `if:`,
   no `continue-on-error`, on a workflow with no path filter. A renderer
   change touches `apps/codegen`; a contract change that breaks the renderer
   touches `openapi/` or the platform, so a filter naming either would stop
   the suite running for the other. They sit in a job of their own, so no
   unrelated step failing ahead of them can stop them running.
2. **Each step runs what its name says**, found by the command and not only
   by the name, so a step renamed onto another command does not pass.
3. **The job can run it**: it installs the SDK the generated code is executed
   against, and it does so before the tests.
4. **No case is silenced in the source**: a skipped case, or one marked to
   run alone, leaves the step green over less than it claims.
5. **Its fixtures are held by the platform's suite.** The Blueprints it
   renders are committed files, and the test that holds each one equal to
   what the route answers is collected by the platform suite's defaults.

Claims 1 to 4 each carry negative controls, through the same predicate the
real workflow and the real sources are read with. Claim 5 is two readings of
the tree with a vacuity floor each and no control of its own: what would make
either pass over nothing is a path that stopped resolving, and both fail on
that.
"""

import ast
import json
import re

import yaml

from _helpers import REPO_ROOT
from tools.gates.enforcement import collection_faults, step_faults

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PACKAGE = REPO_ROOT / "apps" / "codegen"

JOB = "codegen"

#: A case silenced where it is written: skipped, deferred, expected to fail,
#: made conditional, or marked to run alone. Matched as a modifier on a call,
#: whatever follows it — `.skip(`, `.skip.each(`, `.skipIf(…)(`.
SILENCER = re.compile(r"\.(skip|only|todo|fails|skipIf|runIf)\b")

#: The steps, by name, and the command each must run.
STEPS = {
    "Codegen typecheck — the renderer compiles against the committed contract":
        "pnpm --dir apps/codegen typecheck",
    "Codegen lint — the renderer stays a pure function":
        "pnpm --dir apps/codegen lint",
    "Codegen tests — every renderer branch, compiled and run":
        "pnpm --dir apps/codegen test",
}

TESTS = "Codegen tests — every renderer branch, compiled and run"
SDK_INSTALL = "pip install -e ./ubb-sdk"

#: The platform test that holds the committed Blueprints to the route.
FIXTURE_HOLDER = (
    "ubb-platform/api/v1/tests/"
    "test_the_renderers_fixtures_are_what_the_platform_answers.py"
    "::test_a_committed_blueprint_is_what_the_route_answers")


def renderer_faults(workflow):
    """Every reason `workflow` does not require the renderer's suite."""
    faults = []
    steps = ((workflow.get("jobs") or {}).get(JOB) or {}).get("steps") or []
    for name, command in STEPS.items():
        faults += step_faults(workflow, JOB, name)
        for step in steps:
            if step.get("name") == name and str(
                    step.get("run", "")).strip() != command:
                faults.append(f"step `{name}` runs `{step.get('run')}`, "
                              f"not `{command}`")

    names = [step.get("name") for step in steps]
    installs = [index for index, step in enumerate(steps)
                if SDK_INSTALL in str(step.get("run", ""))]
    if not installs:
        faults.append(f"job `{JOB}` never runs `{SDK_INSTALL}`, so the "
                      f"generated code has no SDK to be run against")
    elif TESTS in names and min(installs) > names.index(TESTS):
        faults.append("the SDK is installed after the tests that need it")
    return faults


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_ci_runs_the_renderers_suite_and_can_fail_on_it():
    assert renderer_faults(_workflow()) == []


def test_the_package_defines_the_scripts_the_steps_run():
    """The steps name three scripts; a script deleted from the package would
    leave a step that fails for the wrong reason, or — renamed to something
    that exits clean — one that passes over nothing."""
    scripts = json.loads(
        (PACKAGE / "package.json").read_text(encoding="utf-8"))["scripts"]

    assert scripts["test"] == "vitest run"
    assert scripts["lint"] == "eslint ."
    assert scripts["typecheck"].endswith("tsc -b")
    # The Blueprint's types are generated from the committed contract before
    # they are compiled against, every time.
    assert "openapi/v1.json" in scripts["contract:types"]
    assert scripts["typecheck"].startswith("pnpm contract:types")


def test_the_suite_has_tests_to_run():
    """Vacuity guard: `vitest run` over a directory with no test file would be
    a green step that tested nothing."""
    found = sorted(path.name for path in (PACKAGE / "tests").glob("*.test.ts"))

    assert len(found) >= 4, found
    config = (PACKAGE / "vitest.config.ts").read_text(encoding="utf-8")
    assert 'include: ["tests/**/*.test.ts"]' in config


def silencers(source):
    """Every modifier in `source` that takes a case out of the run."""
    return [match.group(0) for match in SILENCER.finditer(source)]


def test_no_renderer_test_is_skipped_or_run_alone():
    """A `.skip` silences a case and a `.only` silences every other case in
    its file, and either leaves the step green."""
    read = sorted((PACKAGE / "tests").rglob("*.ts"))
    silenced = [f"{path.name}: {marker}" for path in read
                for marker in silencers(path.read_text(encoding="utf-8"))]

    assert len(read) >= 7, [path.name for path in read]
    assert silenced == []


def test_the_fixtures_are_held_by_a_test_the_platform_suite_collects():
    assert collection_faults(REPO_ROOT, "ubb-platform",
                             "ubb-platform/pytest.ini", FIXTURE_HOLDER) == []


def test_every_blueprint_the_suite_renders_is_one_the_platform_holds():
    """The renderer's fixtures are files; the platform test names the set it
    produces. Read from the test's source, since this suite imports no
    platform module."""
    holder = REPO_ROOT / FIXTURE_HOLDER.split("::")[0]
    tree = ast.parse(holder.read_text(encoding="utf-8"))
    (declared,) = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and getattr(node.targets[0], "id", None) == "BLUEPRINT_FIXTURES"]
    produced = sorted(key.value for key in declared.keys)
    committed = sorted(
        path.stem for path in (PACKAGE / "fixtures" / "blueprints").glob("*.json"))

    assert len(committed) >= 8
    assert committed == produced


# --- negative controls: the predicate flags a disarmed suite -----------------

def _synthetic(step_extra=None, job_extra=None, triggers=None, rename=None,
               drop_install=False, install_last=False):
    steps = [{"name": name, "run": command, **(step_extra or {})}
             for name, command in STEPS.items()]
    if rename:
        steps[-1]["run"] = rename
    install = {"name": "install", "run": SDK_INSTALL}
    if install_last:
        steps.append(install)
    elif not drop_install:
        steps.insert(0, install)
    return {
        "on": triggers if triggers is not None else {"push": None,
                                                     "pull_request": None},
        "jobs": {JOB: {**(job_extra or {}), "steps": steps}},
    }


def test_positive_control_a_plain_required_suite_is_clean():
    assert renderer_faults(_synthetic()) == []


def test_negative_control_a_continue_on_error_step_is_flagged():
    faults = renderer_faults(_synthetic(step_extra={"continue-on-error": True}))
    assert any("continue-on-error" in fault for fault in faults)


def test_negative_control_a_conditional_step_is_flagged():
    faults = renderer_faults(_synthetic(
        step_extra={"if": "contains(github.event.head_commit.message, 'x')"}))
    assert any("conditional" in fault for fault in faults)


def test_negative_control_a_conditional_job_is_flagged():
    faults = renderer_faults(_synthetic(job_extra={"if": "false"}))
    assert any("conditional" in fault for fault in faults)


def test_negative_control_a_path_filter_is_flagged():
    faults = renderer_faults(_synthetic(triggers={
        "push": {"paths": ["apps/codegen/**"]}, "pull_request": None}))
    assert any("paths" in fault for fault in faults)


def test_negative_control_a_missing_step_is_flagged():
    workflow = _synthetic()
    workflow["jobs"][JOB]["steps"].pop()
    assert any("no step named" in fault for fault in renderer_faults(workflow))


def test_negative_control_a_step_running_something_else_is_flagged():
    faults = renderer_faults(_synthetic(rename="echo tested"))
    assert any("runs `echo tested`" in fault for fault in faults)


def test_negative_control_a_job_with_no_sdk_is_flagged():
    faults = renderer_faults(_synthetic(drop_install=True))
    assert any("no SDK" in fault for fault in faults)


def test_negative_control_an_sdk_installed_too_late_is_flagged():
    faults = renderer_faults(_synthetic(install_last=True))
    assert faults == ["the SDK is installed after the tests that need it"]


def test_negative_control_a_silenced_case_is_flagged():
    for source in ('it.skip("x", () => {})', 'describe.only("x", () => {})',
                   'it.skip.each([1])("x", () => {})', 'it.todo("x")',
                   'it.skipIf(process.env.CI)("x", () => {})',
                   'it.runIf(hasPython)("x", () => {})',
                   'it.fails("x", () => {})'):
        assert silencers(source), source


def test_positive_control_an_ordinary_case_is_not_flagged():
    assert silencers('it("skips nothing and runs only once", () => {})') == []
    assert silencers('it.each(CASES)("refuses %s", () => {})') == []
