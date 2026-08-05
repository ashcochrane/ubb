"""Is a check actually armed? — the predicates behind an `installed` row.

A manifest that lets a gate *claim* to be installed is worth nothing; the whole
point of #201 is that the claim is checked. Three failures this repository has
already shipped say what checking has to mean:

- the sweep wired ``continue-on-error``, so its findings could never fail a PR;
- the only end-to-end money test sat in no CI job at all, and was dead for six
  months while the board stayed green;
- ``.gitignore``'s unanchored ``lib/`` dropped 22 modules for weeks, and #158
  §16 flags the same shape for path filters — a filter that never mentions a
  seventh input silently stops a gate running.

So an enforcement site is armed only when the workflow *requires* it and, for a
test node, the suite actually *collects* it. Both halves are pure functions over
parsed documents, so the negative controls feed them synthetic inputs through
the same entry point the real manifest uses.

What these predicates do NOT establish is that the test they find is worth
running. That is ADR-0008 §9's limit, restated at this level: a manifest is a
consistency check over consistency checks.
"""

import ast
import configparser
import fnmatch
import shlex
from pathlib import Path

# The command that runs the repository-wide contract suite. The job is found by
# what it RUNS, not by what it is called — a renamed job must not slip the check.
CONTRACT_COMMAND = "pytest tests/contracts"

# pytest's own defaults, applied when a suite declares no configuration file.
DEFAULT_PYTHON_FILES = ("test_*.py", "*_test.py")
DEFAULT_PYTHON_FUNCTIONS = ("test*",)
DEFAULT_PYTHON_CLASSES = ("Test*",)
DEFAULT_NORECURSEDIRS = ("*.egg", ".*", "_darcs", "build", "CVS", "dist",
                         "node_modules", "venv", "{arch}")

# A decorator or `pytestmark` naming any of these takes the test out of the run.
SKIPPING_MARKS = ("skip", "skipif", "xfail")


# ---------------------------------------------------------------------------
# The workflow
# ---------------------------------------------------------------------------

def _triggers(workflow):
    """The `on:` block.

    YAML 1.1 reads a bare `on` as the boolean true, so a workflow parsed with
    PyYAML keys its triggers under `True`. Reading only `"on"` finds nothing and
    concludes, wrongly and silently, that the workflow has no triggers at all.
    """
    for key in ("on", True):
        if key in workflow:
            return workflow[key]
    return None


def _enabled(value):
    """A `continue-on-error` / `if` value that is anything but a literal false
    counts as set — including a `${{ }}` expression this test cannot evaluate."""
    return value is not None and value is not False


def trigger_faults(workflow):
    """Every reason ``workflow`` does not run on every push and pull request."""
    triggers = _triggers(workflow)
    if not isinstance(triggers, dict):
        return [f"the workflow declares no triggers: {triggers!r}"]

    faults = []
    for event in ("push", "pull_request"):
        if event not in triggers:
            faults.append(f"the workflow does not run on {event}")
            continue
        filters = triggers[event] or {}
        for filter_key in ("paths", "paths-ignore"):
            if isinstance(filters, dict) and filter_key in filters:
                faults.append(
                    f"the {event} trigger carries a `{filter_key}` filter — a "
                    f"filter that never mentions an input silently stops the "
                    f"gate running"
                )
    return faults


def enforcement_faults(workflow, command=CONTRACT_COMMAND):
    """Every reason ``workflow`` does not REQUIRE ``command`` to pass.

    A pure function over a parsed document, so the negative controls in
    ``tests/contracts/test_contract_suite_is_enforced.py`` feed it synthetic
    workflows through the same entry point the real one uses.
    """
    faults = trigger_faults(workflow)
    if not isinstance(_triggers(workflow), dict):
        return faults  # no triggers at all; nothing below is meaningful

    found = False
    for job_name, job in (workflow.get("jobs") or {}).items():
        for step in (job.get("steps") or []):
            if command not in str(step.get("run", "")):
                continue
            found = True
            if _enabled(job.get("continue-on-error")):
                faults.append(f"job `{job_name}` is continue-on-error")
            if _enabled(step.get("continue-on-error")):
                faults.append(f"the step in `{job_name}` is continue-on-error")
            if _enabled(job.get("if")):
                faults.append(f"job `{job_name}` is conditional on `if`")
            if _enabled(step.get("if")):
                faults.append(f"the step in `{job_name}` is conditional on `if`")
    if not found:
        faults.append(f"no job runs `{command}`")
    return faults


def job_faults(workflow, job_name):
    """Every reason job ``job_name`` cannot fail the run."""
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return ["the workflow declares no jobs"]
    job = jobs.get(job_name)
    if not isinstance(job, dict):
        return [f"no job named `{job_name}`"]

    faults = []
    if _enabled(job.get("continue-on-error")):
        faults.append(f"job `{job_name}` is continue-on-error")
    if _enabled(job.get("if")):
        faults.append(f"job `{job_name}` is conditional on `if`")
    return faults


def step_faults(workflow, job_name, step_name):
    """Every reason the named step of the named job cannot fail the run.

    Includes the job's own faults and the workflow's triggers: a step in a
    ``continue-on-error`` job, or in a workflow that only runs on a schedule,
    is not a gate however it is written.
    """
    faults = trigger_faults(workflow) + job_faults(workflow, job_name)
    job = (workflow.get("jobs") or {}).get(job_name)
    if not isinstance(job, dict):
        return faults

    matched = [step for step in (job.get("steps") or [])
               if isinstance(step, dict) and step.get("name") == step_name]
    if not matched:
        return faults + [f"job `{job_name}` has no step named `{step_name}`"]

    for step in matched:
        if _enabled(step.get("continue-on-error")):
            faults.append(f"step `{step_name}` in job `{job_name}` is "
                          f"continue-on-error")
        if _enabled(step.get("if")):
            faults.append(f"step `{step_name}` in job `{job_name}` is "
                          f"conditional on `if`")
    return faults


# ---------------------------------------------------------------------------
# The pytest suite
# ---------------------------------------------------------------------------

class Collection:
    """One suite's collection rules, read from its pytest configuration.

    Read rather than assumed: ``ubb-platform/pytest.ini`` excludes
    ``conformance`` from the default run, which is exactly the kind of
    exclusion that would let a gate be listed and never collected.
    """

    def __init__(self, python_files, python_functions, python_classes,
                 norecursedirs, ignored):
        self.python_files = python_files
        self.python_functions = python_functions
        self.python_classes = python_classes
        self.norecursedirs = norecursedirs
        self.ignored = ignored

    @classmethod
    def from_config(cls, config_path):
        """pytest's defaults, overridden by ``config_path`` where it speaks."""
        values = {}
        if config_path is not None:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(config_path.read_text(encoding="utf-8"))
            if parser.has_section("pytest"):
                values = dict(parser.items("pytest"))

        def words(key, default):
            return tuple(values[key].split()) if key in values else default

        ignored = tuple(
            token.split("=", 1)[1]
            for token in shlex.split(values.get("addopts", ""))
            if token.startswith("--ignore=")
        )
        return cls(
            python_files=words("python_files", DEFAULT_PYTHON_FILES),
            python_functions=words("python_functions", DEFAULT_PYTHON_FUNCTIONS),
            python_classes=words("python_classes", DEFAULT_PYTHON_CLASSES),
            norecursedirs=words("norecursedirs", DEFAULT_NORECURSEDIRS),
            ignored=ignored,
        )


def _matches_any(name, patterns):
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def _skipping_marks(node):
    """The skip/xfail marks on one decorated definition or `pytestmark` value."""
    found = set()
    for expression in getattr(node, "decorator_list", [node]):
        for inner in ast.walk(expression):
            name = (inner.attr if isinstance(inner, ast.Attribute)
                    else inner.id if isinstance(inner, ast.Name) else None)
            if name in SKIPPING_MARKS:
                found.add(name)
    return found


def _module_level_skips(tree):
    found = set()
    for statement in tree.body:
        targets = (statement.targets if isinstance(statement, ast.Assign)
                   else [statement.target] if isinstance(statement, ast.AnnAssign)
                   else [])
        if any(isinstance(target, ast.Name) and target.id == "pytestmark"
               for target in targets):
            found |= _skipping_marks(statement.value)
    return found


def _definitions(tree, collection):
    """Every `(name, node)` pytest would consider a test function in ``tree``.

    Module scope, plus the bodies of classes whose names match
    ``python_classes`` — a gate's test may legitimately live in a class.
    """
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield statement.name, statement
        elif (isinstance(statement, ast.ClassDef)
              and _matches_any(statement.name, collection.python_classes)):
            for inner in statement.body:
                if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield inner.name, inner


def collection_faults(repo_root, root, config_path, node):
    """Every reason the pytest suite rooted at ``root`` would not run ``node``.

    ``node`` is ``path/to/test_file.py::test_function``, repo-relative — the
    same spelling ``pytest`` itself takes, so a reader can paste it into a shell
    and watch it run.
    """
    if node.count("::") != 1:
        return [f"`{node}` is not a `path::function` node id"]
    relative, function = node.split("::")

    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        return [f"`{relative}` must be a repository-relative path inside the tree"]
    if not path.as_posix().startswith(root.rstrip("/") + "/"):
        return [f"`{relative}` is outside the suite's root `{root}`"]

    absolute = repo_root / path
    if not absolute.is_file():
        return [f"`{relative}` does not exist"]

    collection = Collection.from_config(
        repo_root / config_path if config_path else None)

    faults = []
    if not _matches_any(path.name, collection.python_files):
        faults.append(f"`{path.name}` does not match the suite's python_files "
                      f"({' '.join(collection.python_files)}), so pytest never "
                      f"collects it")
    for part in path.parts[:-1]:
        if _matches_any(part, collection.norecursedirs):
            faults.append(f"the directory `{part}` matches the suite's "
                          f"norecursedirs, so this file is excluded from the "
                          f"default run")
    for ignored in collection.ignored:
        if path.as_posix() == ignored or path.as_posix().startswith(
                ignored.rstrip("/") + "/"):
            faults.append(f"the suite's addopts carry `--ignore={ignored}`, "
                          f"which excludes this file")

    try:
        tree = ast.parse(absolute.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as problem:
        return faults + [f"`{relative}` does not parse: {problem}"]

    definitions = dict(_definitions(tree, collection))
    if function not in definitions:
        return faults + [f"`{relative}` defines no test named `{function}`"]
    if not _matches_any(function, collection.python_functions):
        faults.append(f"`{function}` does not match the suite's "
                      f"python_functions "
                      f"({' '.join(collection.python_functions)})")

    marks = _skipping_marks(definitions[function]) | _module_level_skips(tree)
    if marks:
        faults.append(f"`{function}` is marked {', '.join(sorted(marks))} — a "
                      f"gate that does not run is not installed")
    return faults
