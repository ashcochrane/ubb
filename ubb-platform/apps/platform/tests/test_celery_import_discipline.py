"""G13 — infrastructure terminology does not dictate domain vocabulary (#205).

ADR-0006 §7, in one sentence: *where a framework's word collides with a domain
word, the framework yields — namespace the infrastructure, qualify its uses,
keep the domain noun.* Celery's `task` does not get to rename the tenant's unit
of work.

The collision is real and current. `apps/platform/work/` holds the Task model
(#196 moved it out of `apps/platform/tasks/` precisely so the domain noun and
the queue's noun stopped being the same import path), and eighteen modules named
`tasks.py` hold Celery's scheduled work. A domain module writing

    from apps.platform.work import tasks

binds the bare word `tasks` to the queue in a file whose subject is the Task —
and every reader after that has to work out which sense is meant from context.

**Two conjuncts**, both about a *binding* rather than about a path:

1. No import binds the bare local name `tasks`, whatever it points at.
2. No import from Celery binds `task`, `tasks`, `Task` or `Tasks`.

The first is deliberately stated over the BOUND NAME rather than over the
imported module. Keying it on "the target is a `tasks` module" would leave
`from apps.x import services as tasks` legal, which puts the collision word in
the namespace by the one route the rule was written to close. Nothing in the
tree does that, and nothing should be able to.

The second is not in G13's one-line statement and is recorded in the manifest's
notes rather than smuggled in. It closes the same door at class scope: `from
celery import Task` puts the framework's base class under the domain's noun,
which is the identical defect one level down and would otherwise be legal. The
same shape as #203's G12, which refuses Django's own noun as a field word beyond
the three names ADR-0006 §3 spells.

What is NOT a violation is the whole point of the rule — the qualified forms are
what a domain module should be writing, so all three are positive controls
below: import the scheduled-work *function*, alias the module to a name that
says which sense is meant, or import it fully qualified and call through the
dotted path.

**Why this walks every node.** Its closest sibling is `test_product_boundaries.py`,
whose Context records lazy function-body imports as the historical erosion vector
for the boundary rule — a module-scope check would have missed them. There is no
reason this rule would erode differently, so `ast.walk` visits imports inside
functions, methods and conditionals exactly like module-scope ones.

**Why tests and migrations are in scope, unlike the boundary walker.** That
walker excludes them because a fixture may legitimately reach across a product
boundary to set one up. No such exemption exists here: a test binding `tasks`
bare is the same ambiguity in the same tree, read by the same people. The tree is
clean today, so the strict form costs nothing and leaves no allowlist to erode.

**Why the walk is not shared with the boundary walker**, since the two are
visibly similar. They scan different trees to different rules — that one takes
`apps/` and `core/` without tests or migrations, this one takes four trees with
them — and they need different things from a statement: the boundary rule is
about the module IMPORTED, so it yields the target, while this rule is about the
name BOUND, so it yields the local name and the statement to quote back. Only the
relative-import anchoring is genuinely common, and lifting fifteen lines into a
shared module would mean editing ADR-001's enforcement site as a side effect of a
vocabulary ticket. The duplication is therefore deliberate and stated, in the
same spirit as `tests/contracts/_helpers.py` recomputing the repository root
rather than importing it.
"""
import ast
from pathlib import Path

# apps/platform/tests/test_celery_import_discipline.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

ADR = "docs/adr/0006-domain-vocabulary-and-contract-naming.md"

# Every first-party tree. `config/` and `api/` are included because ADR-0006 §7
# is about the vocabulary a reader meets, and a reader meets all four.
SOURCE_TREES = ("apps", "core", "api", "config")

_EXCLUDED_DIR_NAMES = {"__pycache__"}

#: The domain's noun, in the spellings an import can bind it under. `tasks` is
#: the module; the rest are what Celery's own package exports it as.
COLLISION_NAMES = frozenset({"task", "tasks", "Task", "Tasks"})

#: The infrastructure package whose vocabulary yields.
FRAMEWORK = "celery"

RULE_MODULE = "bare-tasks-module-binding"
RULE_FRAMEWORK = "celery-noun-binding"

_ACCEPTABLE = (
    "Acceptable forms, all of which keep the domain's noun free:\n"
    "    from apps.platform.work.tasks import close_abandoned_tasks  "
    "# the function itself\n"
    "    from apps.platform.work import tasks as celery_tasks        "
    "# an alias that says which sense\n"
    "    import apps.platform.work.tasks                             "
    "# fully qualified, called through the dotted path"
)


def _iter_source_files():
    """Every .py under the first-party trees — tests and migrations included."""
    for top in SOURCE_TREES:
        root = PLATFORM_ROOT / top
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(PLATFORM_ROOT)
            if any(part in _EXCLUDED_DIR_NAMES for part in rel.parts):
                continue
            yield path, rel


def _module_name(rel_path):
    """Dotted module path for a file, and whether it is a package __init__."""
    parts = list(rel_path.with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def iter_bindings(tree, module, is_package=False):
    """Yield ``(lineno, local, target, statement)`` for every import ANYWHERE.

    ``local`` is the name the statement binds in this module's namespace, which
    is the only thing this rule is about — ``import x.y.tasks`` binds ``x``, so
    its uses are qualified and it is not a collision at all.

    ``target`` is the most specific dotted name imported, with relative imports
    resolved against ``module`` so ``from ..work import tasks`` is judged the
    same as its absolute spelling. ``statement`` is the source line, rebuilt for
    the failure message rather than re-read from disk.
    """
    pkg_parts = module.split(".") if module else []
    if not is_package and pkg_parts:
        pkg_parts = pkg_parts[:-1]  # containing package of a plain module
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                statement = f"import {alias.name}" + (
                    f" as {alias.asname}" if alias.asname else "")
                yield node.lineno, local, alias.name, statement
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: anchor it to the source package
                anchor = pkg_parts[: max(0, len(pkg_parts) - (node.level - 1))]
                suffix = node.module.split(".") if node.module else []
                base = ".".join(anchor + suffix)
            else:
                base = node.module or ""
            written = "." * node.level + (node.module or "")
            for alias in node.names:
                local = alias.asname or alias.name
                target = f"{base}.{alias.name}" if base else alias.name
                statement = f"from {written} import {alias.name}" + (
                    f" as {alias.asname}" if alias.asname else "")
                yield node.lineno, local, target, statement


def _is_framework(target):
    """Does the imported dotted name come out of Celery itself?"""
    return target == FRAMEWORK or target.startswith(FRAMEWORK + ".")


def _touches_infrastructure(target):
    """Does this import reach into scheduled work at all, however it binds?

    Broader than either rule above on purpose — it counts
    ``from apps.x.tasks import settle_raw_events``, which is the CORRECT form
    and therefore invisible to a violation count. This is the vacuity guard's
    input, and a guard that only counted the shapes the rules reject would read
    zero on a clean tree, which is precisely when the walker's reach is
    unproven.
    """
    return "tasks" in target.split(".") or _is_framework(target)


def classify_binding(source_label, lineno, local, target, statement):
    """Return ``(rule, message)`` if this import binds the domain's noun to
    infrastructure, else None."""
    if local == "tasks":
        return (
            RULE_MODULE,
            f"{source_label}:{lineno} binds the bare name `tasks` to {target} "
            f"(`{statement}`) — ADR-0006 §7: where a framework's word collides "
            f"with a domain word, the framework yields, and this repository's "
            f"domain noun is the Task. See {ADR}.\n{_ACCEPTABLE}",
        )
    if local in COLLISION_NAMES and _is_framework(target):
        return (
            RULE_FRAMEWORK,
            f"{source_label}:{lineno} binds `{local}` to Celery's {target} "
            f"(`{statement}`) — ADR-0006 §7: the framework yields, so its own "
            f"noun may not stand unqualified beside the domain's. Import it "
            f"under an alias (`from celery import Task as CeleryTask`) or "
            f"reference it through the package (`import celery`). See {ADR}.",
        )
    return None


def _collect():
    """Parse the whole tree once.

    Returns ``(violations, scanned modules, sightings)``. A *sighting* is any
    import that reaches into scheduled work, violating or not — the vacuity
    guard asserts on those, because a walker that stopped reaching the
    statements it judges would pass every assertion below while checking
    nothing.
    """
    violations = []
    scanned = set()
    sightings = 0
    for path, rel in _iter_source_files():
        label = rel.as_posix()
        module, is_package = _module_name(rel)
        scanned.add(module)
        # `utf-8-sig`, not `utf-8`: at least one module in the tree carries a
        # byte-order mark. Python's own tokenizer strips one, so the file is
        # valid Python and importing it works — but a walker that decodes the
        # bytes itself gets a leading U+FEFF and `ast.parse` refuses it. Reading
        # it as anything else would make the gate red on a file that is fine.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"),
                         filename=str(path))
        for lineno, local, target, statement in iter_bindings(
                tree, module, is_package):
            if _touches_infrastructure(target):
                sightings += 1
            hit = classify_binding(label, lineno, local, target, statement)
            if hit is not None:
                violations.append(hit)
    return violations, scanned, sightings


_VIOLATIONS, _SCANNED, _SIGHTINGS = _collect()


def _failures(rule):
    return "\n\n".join(message for name, message in _VIOLATIONS if name == rule)


# ---------------------------------------------------------------------------
# The shipped tree
# ---------------------------------------------------------------------------

def test_no_domain_module_imports_a_celery_tasks_module_unqualified():
    """G13. Nothing binds the bare word `tasks` to scheduled work."""
    assert not _failures(RULE_MODULE), "\n" + _failures(RULE_MODULE)


def test_celery_does_not_bind_the_domain_noun():
    """G13's second conjunct: the framework's own `Task` stays qualified."""
    assert not _failures(RULE_FRAMEWORK), "\n" + _failures(RULE_FRAMEWORK)


def test_the_walker_reached_the_imports_it_judges():
    """Vacuity guard: a walker that finds nothing passes everything.

    Two floors, because they fail differently. The module count catches a path
    that stopped resolving; the sighting count catches the subtler case — the
    walk still reads files, but no longer reaches the import statements the rule
    is about, so every assertion above is true of nothing.
    """
    assert len(_SCANNED) > 200, f"only scanned {len(_SCANNED)} modules"
    for expected in (
        "apps.platform.work.tasks",
        "apps.platform.events.tasks",
        "apps.metering.usage.tasks",
        "core.tasks",
        "config.celery",
    ):
        assert expected in _SCANNED, f"walker did not visit {expected}"
    assert _SIGHTINGS > 60, (
        f"the walk judged only {_SIGHTINGS} imports reaching into scheduled "
        f"work, and the tree has close to a hundred — the walker has stopped "
        f"reaching its own subject")


# ---------------------------------------------------------------------------
# Negative controls: prove the classifier flags what it claims to flag. Run on
# parsed snippets with synthetic module paths, not on real files — there is no
# violation in the tree to point at, and an absence test with nothing proving it
# can fail is a test that asserts nothing.
# ---------------------------------------------------------------------------

def _classify_snippet(source, module="apps.billing.synthetic.module"):
    tree = ast.parse(source)
    label = module.replace(".", "/") + ".py"
    return [
        hit
        for lineno, local, target, statement in iter_bindings(
            tree, module, is_package=False)
        for hit in [classify_binding(label, lineno, local, target, statement)]
        if hit is not None
    ]


def test_negative_control_module_scope_binding_is_flagged():
    hits = _classify_snippet("from apps.platform.work import tasks\n")
    assert len(hits) == 1
    rule, message = hits[0]
    assert rule == RULE_MODULE
    assert ":1 " in message
    # The failure has to tell the reader what to write instead.
    assert "from apps.platform.work import tasks as celery_tasks" in message


def test_negative_control_lazy_function_body_binding_is_flagged():
    """The erosion vector ADR-001's Context names, in this rule's shape."""
    hits = _classify_snippet(
        "def sneaky():\n"
        "    from apps.billing.wallets import tasks\n"
        "    return tasks\n"
    )
    assert len(hits) == 1
    assert hits[0][0] == RULE_MODULE
    assert ":2 " in hits[0][1]


def test_negative_control_relative_import_is_resolved_and_flagged():
    # In apps/billing/x/y.py, "from ..wallets import tasks" resolves to
    # apps.billing.wallets.tasks and binds the bare noun just the same.
    hits = _classify_snippet("from ..wallets import tasks\n", "apps.billing.x.y")
    assert len(hits) == 1
    assert hits[0][0] == RULE_MODULE


def test_negative_control_aliasing_back_onto_the_domain_noun_is_flagged():
    """`as tasks` is the qualified form with the qualification removed."""
    hits = _classify_snippet("import apps.referrals.tasks as tasks\n")
    assert len(hits) == 1
    assert hits[0][0] == RULE_MODULE


def test_negative_control_binding_anything_else_to_the_noun_is_flagged():
    """The rule is about the NAME BOUND, not about what it points at.

    A rule keyed on "the target is a `tasks` module" would let these through,
    and each puts the collision word in the namespace by exactly the route
    ADR-0006 §7 is written to close.
    """
    for source in ("from apps.billing.wallets import services as tasks\n",
                   "import queue as tasks\n"):
        hits = _classify_snippet(source)
        assert len(hits) == 1, source
        assert hits[0][0] == RULE_MODULE, source


def test_negative_control_celery_base_class_binding_is_flagged():
    for source in ("from celery import Task\n",
                   "from celery.app.task import Task\n",
                   "import celery.app.task as task\n"):
        hits = _classify_snippet(source)
        assert len(hits) == 1, source
        assert hits[0][0] == RULE_FRAMEWORK, source


# ---------------------------------------------------------------------------
# Positive controls: the qualified forms are the point of the rule, so each one
# the failure message recommends is proved legal here. A gate that refused its
# own advice would be unfixable.
# ---------------------------------------------------------------------------

def test_positive_control_the_recommended_forms_are_legal():
    assert not _classify_snippet(
        "from apps.platform.work.tasks import close_abandoned_tasks\n")
    assert not _classify_snippet(
        "from apps.platform.work import tasks as celery_tasks\n")
    assert not _classify_snippet("import apps.platform.work.tasks\n")
    assert not _classify_snippet("from celery import shared_task\n")
    assert not _classify_snippet("from celery import Task as CeleryTask\n")
    assert not _classify_snippet("from celery.schedules import crontab\n")


def test_positive_control_the_domain_noun_itself_is_untouched():
    """The rule is about the framework's word, not about the domain's.

    `Task` bound from the work app is the correct name for the correct thing —
    a rule that condemned it would have inverted ADR-0006 §7, making the domain
    yield to the framework it exists to protect the domain from.
    """
    assert not _classify_snippet(
        "from apps.platform.work.models import Task, Subtask\n")
    assert not _classify_snippet("from apps.platform.work import services\n")


def test_prefix_matching_does_not_confuse_sibling_names():
    # `tasks_webhook_cleanup` is a real module beside `tasks.py`; binding it is
    # unambiguous and must not be swept up by a prefix match.
    assert not _classify_snippet(
        "from apps.platform.events import tasks_webhook_cleanup\n")
    # `celery_config` is not the celery package.
    assert not _classify_snippet("from celery_config import Task\n")
    assert not _touches_infrastructure(
        "apps.platform.events.tasks_webhook_cleanup")
    assert not _is_framework("celery_config.app")
