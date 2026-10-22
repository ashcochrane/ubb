"""The renderer's suite runs on every change, and can fail it (#577, #578).

`ubb-codegen` turns an Integration Blueprint into the files a tenant is
handed, and what holds it to its rules is a suite that renders committed
Blueprints and then runs what it wrote: the Python it compiles and imports,
the shell it sources under `sh` and `bash`. A suite like that is worth
exactly as much as its place in CI: the forbidden-term sweep once ran under
`continue-on-error`, and the only end-to-end money test once sat in no job at
all, and both stayed green for months.

So its enforcement is checked here, the way the contract suite's own is:

1. **Its three steps run unconditionally and can fail the run** — no `if:`,
   no `continue-on-error`, on a workflow with no path filter. A renderer
   change touches `apps/codegen`; a contract change that breaks the renderer
   touches `openapi/` or the platform, so a filter naming either would stop
   the suite running for the other. They sit in a job of their own, so no
   unrelated step failing ahead of them can stop them running.
2. **Each step runs what its name says**, found by the command and not only
   by the name, so a step renamed onto another command does not pass.
3. **The job can run it**: it installs the SDK the generated Python is
   executed against, and it checks for the shell, `curl` and `jq` the
   generated shell is executed with, both before the tests. Nothing hands the
   job a container to run the shell in: on the runner the tools are its own.
4. **No case is silenced in the source**: a skipped case, or one marked to
   run alone, leaves the step green over less than it claims.
5. **Its fixtures are held by the platform's suite.** The Blueprints it
   renders are committed files, and the test that holds each one equal to
   what the route answers is collected by the platform suite's defaults.
6. **Every case a Code Builder gate rests on is written to run** (#587).
   G23, G24 and G26 name the test step above as a site, and a step names a
   suite rather than a case: deleting the five secret tests would leave the
   step, and the row, green. A vitest case is not a node the gate manifest
   can name, so the cases each of those rows rests on are named here, by
   file and title, and every row naming the step is held to having them and
   to naming the two nodes here that hold them.

Claims 1 to 4 and 6 each carry negative controls, through the same predicate
the real workflow and the real sources are read with. Claim 5 is two readings
of the tree with a vacuity floor each and no control of its own: what would
make either pass over nothing is a path that stopped resolving, and both fail
on that.
"""

import ast
import json
import re

import yaml

from _gate_helpers import real
from _helpers import REPO_ROOT
from tools.gates.enforcement import collection_faults, step_faults

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PACKAGE = REPO_ROOT / "apps" / "codegen"

#: What `vitest run` collects: every `*.test.ts` under `tests/`.
INCLUDE = 'include: ["tests/**/*.test.ts"]'

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

#: The step that checks for what a generated shell file is run with, and what
#: it must call: each fails the step, by name, on a runner that lacks it.
SHELL_TOOLS = "Shell tools — what the generated shell file is run with"
SHELL_TOOL_CHECKS = ("sh -c", "bash --version", "curl --version", "jq --version")

#: What tells the suite to run the shell in a container instead of on the
#: machine. A developer's choice on a machine with no tools of its own; set in
#: CI, it would move the tests off the runner the step above just checked.
SHELL_IMAGE = "UBB_CODEGEN_SHELL_IMAGE"

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

    faults += step_faults(workflow, JOB, SHELL_TOOLS)
    for step in steps:
        if step.get("name") != SHELL_TOOLS:
            continue
        for check in SHELL_TOOL_CHECKS:
            if check not in str(step.get("run", "")):
                faults.append(f"step `{SHELL_TOOLS}` does not run `{check}`")
        if TESTS in names and names.index(SHELL_TOOLS) > names.index(TESTS):
            faults.append("the shell tools are checked for after the tests "
                          "that need them")
    if SHELL_IMAGE in json.dumps(workflow):
        faults.append(f"the workflow sets `{SHELL_IMAGE}`, which takes the "
                      f"shell tests off the runner")
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

    assert len(found) >= 6, found
    # Each target has a module that RUNS what it rendered.
    assert "execution.test.ts" in found
    assert "shell.execution.test.ts" in found
    config = (PACKAGE / "vitest.config.ts").read_text(encoding="utf-8")
    assert INCLUDE in config


def silencers(source):
    """Every modifier in `source` that takes a case out of the run."""
    return [match.group(0) for match in SILENCER.finditer(source)]


def test_no_renderer_test_is_skipped_or_run_alone():
    """A `.skip` silences a case and a `.only` silences every other case in
    its file, and either leaves the step green."""
    read = sorted((PACKAGE / "tests").rglob("*.ts"))
    silenced = [f"{path.name}: {marker}" for path in read
                for marker in silencers(path.read_text(encoding="utf-8"))]

    assert len(read) >= 11, [path.name for path in read]
    assert silenced == []


#: The renderer's cases each Code Builder gate rests on, by the file and the
#: title they are written with. The rows name the test step, which runs every
#: case; these say WHICH of them a row's claim is made of, so that losing one
#: fails here rather than leaving the row green (claim 6).
GATE_CASES = {
    # #158 §5.2's static layer, on both targets.
    "G23": (
        # Parse or compile.
        ("artifact.test.ts", "compiles, every Python file of it"),
        ("shell.artifact.test.ts",
         "parses, every shell file of it, under sh and under bash"),
        # Every operation the file reaches is the one its Blueprint names,
        # and every key it sends is one that operation publishes.
        ("execution.test.ts",
         "starts, records and closes through the operations the Blueprint names"),
        ("execution.test.ts",
         "sends only keys the operation's request publishes"),
        ("shell.execution.test.ts",
         "starts, records and closes through the operations the Blueprint names"),
        ("shell.execution.test.ts",
         "sends only keys the operation's request publishes: %s, run as its own blocks say"),
        ("shell.execution.test.ts",
         "reads these branches' published keys off a contract that has some"),
        # No real secret appears.
        ("artifact.test.ts",
         "reads the credential from the environment and writes it nowhere"),
        ("shell.artifact.test.ts",
         "reads the credential from the environment, hands it to curl on "
         "standard input, and writes it nowhere"),
        # Declared names are preserved.
        ("execution.test.ts", "reach the wire exactly as they were declared"),
        ("shell.execution.test.ts",
         "reach the wire exactly as they were declared"),
        # The rendered verdict is the one the plan was handed: in every
        # branch, and for each of the three verdicts in what it means.
        ("artifact.test.ts",
         "states the three versions, the target, the fingerprint and the verdict"),
        ("artifact.test.ts",
         "states the verdict its Blueprint carries, in every branch"),
        ("artifact.test.ts", "states a %s verdict and what it means"),
        ("artifact.test.ts", "lists an advisory and still says complete"),
        ("shell.artifact.test.ts",
         "states the three versions, the target, the fingerprint and the verdict"),
        ("shell.artifact.test.ts",
         "carries no readiness verdict, and the header of the runnable file does"),
        ("shell.artifact.test.ts",
         "states a %s verdict and what it means for a shell file"),
    ),
    # Every renderer branch of both targets, pinned as the files it returns.
    "G24": (
        ("snapshots.test.ts", "renders the files its snapshot holds"),
        ("snapshots.test.ts", "holds no snapshot of a file it no longer renders"),
        ("snapshots.test.ts",
         "are of the branches the tests render, and of no other"),
        ("snapshots.test.ts", "cover every branch the ticket names"),
        ("snapshots.test.ts",
         "cover the same branches for the shell target, and the one only it has"),
    ),
    # #156 §7's five secret tests, the renderer's half of each.
    "G26": (
        # 1. No secret value in generated source.
        ("artifact.test.ts",
         "reads the credential from the environment and writes it nowhere"),
        ("shell.artifact.test.ts",
         "reads the credential from the environment, hands it to curl on "
         "standard input, and writes it nowhere"),
        ("execution.test.ts",
         "reads the credential from the environment and nowhere else"),
        ("shell.execution.test.ts",
         "reads the credential from the environment and nowhere else"),
        ("snapshots.test.ts",
         "writes the same files whatever a secret token carries as a value: %s"),
        # 2. None in fixtures or snapshots — and the search can find one.
        ("artifact.test.ts", "nothing under %s is shaped like a key"),
        ("artifact.test.ts", "can find a key that is there"),
        ("artifact.test.ts",
         "no fixture carries a value on a secret token, so none could leak one"),
        # 3. Every secret reference carries setup instructions.
        ("artifact.test.ts",
         "gives every secret reference its setup instructions"),
        ("shell.artifact.test.ts",
         "gives every secret reference its setup instructions"),
        # 4. Every non-secret platform-known value renders consistently — a
        # declared constant's among them, which sits on a dotted token the
        # two cases above it pass over (#584).
        ("artifact.test.ts",
         "writes every platform-known argument as the literal Python reads "
         "back unchanged"),
        ("shell.artifact.test.ts",
         "writes every platform-known value a call sends as the JSON that means it"),
        ("artifact.test.ts",
         "states every platform-known token in the function for its call"),
        ("artifact.test.ts",
         "writes each constant as a typed exact literal in the module, with "
         "where it was declared"),
        ("artifact.test.ts",
         "keeps every constant's value out of the lines a tenant maintains"),
        ("execution.test.ts",
         "sends each constant as the exact decimal it was declared as"),
        ("shell.execution.test.ts",
         "sends each constant as the exact decimal it was declared as"),
        # 5. Every runtime value lands at its declared scope.
        ("artifact.test.ts",
         "asks for every runtime value as a required parameter, at the call "
         "it is declared for"),
        ("shell.artifact.test.ts",
         "asks for every runtime value as a name=value parameter, at the call "
         "it is declared for"),
    ),
}

#: Comment, which can spell a case without being one: a whole `/* … */`
#: block, and a line comment.
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"^\s*//")

#: The two nodes of this module every row with cases names (claim 6): its
#: cases written, and nothing around them silenced.
CASE_NODES = tuple(
    f"tests/contracts/test_the_renderer_suite_is_enforced.py::{name}"
    for name in ("test_every_case_a_code_builder_gate_rests_on_is_written_to_run",
                 "test_no_renderer_test_is_skipped_or_run_alone"))


def written(title, source):
    """Is `title` a case `source` writes to run?

    `it("<title>", …)`, or `it.each(<cases>)("<title>", …)` over cases that
    are not written empty — the two forms the suite uses. A case under a
    modifier (`it.skip(`, `it.only(`) does not match, and neither does a
    `describe` of that title or a case in a comment. A skip or an `only`
    elsewhere — on the `describe` around it, or on another case — is
    `test_no_renderer_test_is_skipped_or_run_alone`'s to refuse. The title is
    matched as the double-quoted literal the suite writes it as.
    """
    code = "\n".join(line for line in BLOCK_COMMENT.sub("", source).splitlines()
                     if not LINE_COMMENT.match(line))
    literal = re.escape(json.dumps(title, ensure_ascii=False))
    each = r"(?:\.each\((?!\s*\[\s*\]\s*\))(?:[^()]|\([^()]*\))*\))?"
    return re.search(rf"\bit{each}\(\s*{literal}\s*,", code) is not None


def test_every_case_a_code_builder_gate_rests_on_is_written_to_run():
    """Claim 6. Each case is written to run in a file the step's
    `vitest run` collects, so deleting or renaming one, or putting a modifier
    on it, is red here; a skip or an `only` around it is red in
    `test_no_renderer_test_is_skipped_or_run_alone`."""
    config = (PACKAGE / "vitest.config.ts").read_text(encoding="utf-8")
    assert INCLUDE in config

    missing = []
    for gate, cases in GATE_CASES.items():
        assert len(cases) >= 5, gate
        for file, title in cases:
            assert file.endswith(".test.ts"), file
            source = (PACKAGE / "tests" / file).read_text(encoding="utf-8")
            if not written(title, source):
                missing.append(f"{gate}: {file}: {title}")
    assert missing == []


def test_the_rows_that_name_the_renderers_tests_are_the_rows_with_cases():
    """Every gate naming the test step as a site has its cases named above
    and names this module's two nodes that hold them, and no gate has cases
    named that does not name the step — so a row cannot rest on the suite
    without saying which of it, nor drop what holds those cases, and a list
    cannot outlive the row it was for."""
    rows = yaml.safe_load(real("manifest.yaml"))["gates"]
    naming = sorted(
        gate for gate, row in rows.items()
        if {"job": JOB, "step": TESTS} in (row.get("enforced_by") or []))

    assert naming == sorted(GATE_CASES)
    for gate in naming:
        assert rows[gate]["status"] == "installed", gate
        sites = rows[gate]["enforced_by"]
        for node in CASE_NODES:
            assert {"suite": "contracts", "node": node} in sites, (gate, node)


def test_the_shell_tests_have_no_way_to_pass_without_a_shell():
    """Where the shell is, is a setting; whether the tests run is not. The
    one place that setting is read must run the harness either way — on the
    machine or in the image — and neither branch may give up quietly."""
    support = (PACKAGE / "tests" / "support" / "shell.ts").read_text(
        encoding="utf-8")

    assert f"process.env.{SHELL_IMAGE}" in support
    # Both branches, each by the call it makes: the harness run by this
    # machine's interpreter, and the harness run inside the image.
    assert 'join(HARNESS_DIRECTORY, "shell_harness.py")' in support
    assert '"python3", "/harness/shell_harness.py"' in support
    assert "throw ran.error" in support
    assert "ran.status !== 0" in support
    # And the harness itself asks every shell it names: none is optional.
    harness = (PACKAGE / "tests" / "harness" / "shell_harness.py").read_text(
        encoding="utf-8")
    assert 'SHELLS = ("sh", "bash")' in harness
    assert "shutil.which" not in harness and "skip" not in harness.lower()


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
               drop_install=False, install_last=False, tools="first",
               tool_checks=SHELL_TOOL_CHECKS, tools_extra=None):
    steps = [{"name": name, "run": command, **(step_extra or {})}
             for name, command in STEPS.items()]
    if rename:
        steps[-1]["run"] = rename
    install = {"name": "install", "run": SDK_INSTALL}
    if install_last:
        steps.append(install)
    elif not drop_install:
        steps.insert(0, install)
    shell_tools = {"name": SHELL_TOOLS, "run": "\n".join(tool_checks),
                   **(tools_extra or {})}
    if tools == "first":
        steps.insert(0, shell_tools)
    elif tools == "last":
        steps.append(shell_tools)
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


def test_negative_control_a_job_that_never_checks_for_the_shell_tools_is_flagged():
    faults = renderer_faults(_synthetic(tools=None))
    assert any("no step named" in fault and SHELL_TOOLS in fault
               for fault in faults)


def test_negative_control_a_tool_left_unchecked_is_flagged():
    for dropped in SHELL_TOOL_CHECKS:
        kept = tuple(check for check in SHELL_TOOL_CHECKS if check != dropped)
        faults = renderer_faults(_synthetic(tool_checks=kept))
        assert faults == [
            f"step `{SHELL_TOOLS}` does not run `{dropped}`"], dropped


def test_negative_control_shell_tools_checked_too_late_are_flagged():
    faults = renderer_faults(_synthetic(tools="last"))
    assert faults == [
        "the shell tools are checked for after the tests that need them"]


def test_negative_control_a_conditional_tools_check_is_flagged():
    faults = renderer_faults(_synthetic(tools_extra={"if": "false"}))
    assert any("conditional" in fault for fault in faults)


def test_negative_control_shell_tests_moved_into_a_container_are_flagged():
    workflow = _synthetic()
    workflow["jobs"][JOB]["env"] = {SHELL_IMAGE: "some-image"}
    assert renderer_faults(workflow) == [
        f"the workflow sets `{SHELL_IMAGE}`, which takes the shell tests off "
        f"the runner"]


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


# --- claim 6's controls: a case that is not written to run is not one --------

def test_positive_control_a_case_written_either_way_is_found():
    assert written("holds it", 'it("holds it", () => {})')
    assert written("refuses %s", 'it.each(CASES)(\n  "refuses %s",\n  (x) => {})')
    assert written("scans %s", 'it.each([A, join(B, "c")])("scans %s", (d) => {})')
    assert written("it's naïve", 'it("it\'s naïve", () => {})')


def test_negative_control_a_case_that_is_not_there_is_not_written():
    assert not written("holds it", 'it("holds something else", () => {})')
    assert not written("holds it", 'it("holds it, and more", () => {})')


def test_negative_control_a_silenced_case_is_not_written():
    for modifier in ("skip", "only", "todo", "fails"):
        assert not written("holds it", f'it.{modifier}("holds it", () => {{}})')


def test_negative_control_a_describe_or_a_comment_is_not_a_case():
    assert not written("holds it", 'describe("holds it", () => {})')
    assert not written("holds it", '// it("holds it", () => {})')
    assert not written("holds it", '/**\n * it("holds it", () => {})\n */')
    assert not written("holds it", '/*\nit("holds it", () => {});\n*/')
    assert written("holds it", '/* a note */\nit("holds it", () => {})')


def test_negative_control_a_case_over_no_cases_is_not_written():
    assert not written("refuses %s", 'it.each([])("refuses %s", (x) => {})')
    assert not written("refuses %s", 'it.each( [ ] )("refuses %s", (x) => {})')
