"""Every scheduled entry names work that can actually run.

The beat schedule is the one place in this tree where a dotted string is the
only thing binding a name to code. Nothing imports it, so nothing type-checks
it, and deleting the function it names leaves a schedule that fails at 3am in a
worker log rather than in CI. Slice 1 deletes scheduled work in three separate
commits, which is exactly the window in which that goes unnoticed.

**Two conjuncts, because the first one alone has already let a break through.**

1. Every entry's dotted path is a name the Celery registry actually holds.
2. Every module a scheduled task's body imports is importable, and every name
   it imports from one exists.

The second is not padding. When the ingest-health module was deleted, its
scheduled monitor kept a dotted path that resolved perfectly — the breakage was
one level down, in a function-body import that would have raised
``ModuleNotFoundError`` on the task's first run. The only test that invoked the
task died in the same commit, so the suite stayed green over a task that could
not run: the *"check that exists but cannot fail anything"* shape
``gates/README.md`` records this repository shipping three times. Conjunct 1
would not have caught it. Conjunct 2 does.

**Why the registry rather than ``hasattr(obj, "delay")``.** Beat does not call
the attribute it finds at the end of a dotted path — it looks the entry's string
up in ``app.tasks`` by REGISTERED NAME. Those coincide only because no
``@shared_task`` in this tree passes ``name=``; one that did would leave an
entry that imports cleanly, exposes ``.delay``, and is still unreachable to the
scheduler. Asking the registry asks the question beat asks. The registry is
populated as a side effect of importing each task's module, because
``autodiscover_tasks`` is lazy — so the import below is load-bearing, not just a
resolution step.

**Why function-body imports specifically.** Scheduled tasks in this tree import
lazily inside the function on purpose — ``apps/metering`` and ``apps/billing``
reach each other only through the sanctioned read contracts (ADR-001), and the
lazy form keeps module import graphs flat. So the *majority* of a task's real
dependencies are invisible to a module-scope check, and a walker that only read
module-scope imports would be reading the wrong half of the file.

**Resolution is restricted to first-party modules.** A missing third-party
package is a lockfile failure that every other test in the suite fails on
first; re-checking it here would import arbitrary vendor modules for no signal.

**Why this walk is not shared with ``test_celery_import_discipline.py``**, which
sits beside it and also parses imports. That walker reads whole SOURCE TREES
from disk to judge the NAME an import binds; this one starts from the beat
schedule, reaches only the handful of functions it names, and judges whether the
TARGET resolves. Neither the input nor the question is common, and the only
genuinely shared fifteen lines are the relative-import anchoring. The
duplication is deliberate and stated, in the same spirit as that module's own
note about not sharing with the ADR-001 boundary walker.

Negative controls run against synthetic functions defined at the foot of this
module, because the tree is clean and an absence test with nothing proving it
can fail asserts nothing.
"""
import ast
import importlib
import inspect
import textwrap

from django.conf import settings

#: The trees whose absence is a bug in this repository rather than in the
#: environment. Anything else resolves by the lockfile's guarantee.
FIRST_PARTY = ("apps.", "core.", "config.", "api.")

#: Floors for the vacuity guard. Set near the real numbers (27 entries, 56 body
#: imports at the time of writing) rather than far below them: a floor at a
#: third of the truth passes a walk that has stopped reaching two thirds of its
#: subject, which is the failure being guarded against. Later slices delete
#: scheduled work, so these are expected to be lowered — deliberately, in the
#: commit that removes the tasks, which is the point.
MIN_ENTRIES = 20
MIN_BODY_IMPORTS = 40


def _is_first_party(module):
    return any(module == top.rstrip(".") or module.startswith(top)
               for top in FIRST_PARTY)


def resolve_task(dotted):
    """Resolve a beat entry the way beat does. ``(task, None)`` or
    ``(None, reason)``.

    Returns a reason rather than raising for any failure this test is about, so
    one dangling entry does not hide the rest behind an error. The returned
    object is the module attribute, not the registry's task instance, because
    the caller wants its SOURCE — but membership of the registry is what decides
    whether the entry resolves at all.
    """
    module_path, _, attribute = dotted.rpartition(".")
    if not module_path:
        return None, f"{dotted!r} is not a dotted path"
    try:
        # Importing is what puts the task in the registry checked below:
        # `autodiscover_tasks` is lazy, so an unimported module's tasks are
        # simply absent.
        module = importlib.import_module(module_path)
    except Exception as exc:
        return None, f"{dotted!r}: importing {module_path!r} failed ({exc!r})"
    task = getattr(module, attribute, None)
    if task is None:
        return None, f"{dotted!r}: {module_path!r} has no attribute {attribute!r}"
    from config.celery import app
    if dotted not in app.tasks:
        return None, (f"{dotted!r} is not in the Celery task registry even after "
                      f"importing {module_path!r} — beat looks an entry up by "
                      f"registered NAME, so this is either not a task at all or "
                      f"a task registered under some other name")
    return task, None


def iter_body_imports(func):
    """Yield ``(module, names)`` for every import ANYWHERE inside ``func``.

    ``names`` is empty for a plain ``import x``; for ``from x import a, b`` it
    is the attributes that must exist on ``x``. Relative imports inside a
    function body are yielded resolved against the function's own package.
    """
    source = textwrap.dedent(inspect.getsource(func))
    package = getattr(func, "__module__", "")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, ()
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                # `from ..models import X` inside a function body — anchor on
                # the containing module's own dotted name, dropping one part per
                # dot (one drops the module itself, leaving its package).
                parts = package.split(".")[:-node.level]
                module = ".".join([*parts, module]) if module else ".".join(parts)
            yield module, tuple(alias.name for alias in node.names)


def unresolved_body_imports(func):
    """Every first-party import in ``func``'s body that would raise at runtime."""
    failures = []
    for module, names in iter_body_imports(func):
        if not _is_first_party(module):
            continue
        try:
            imported = importlib.import_module(module)
        except ImportError as exc:
            failures.append(f"{func.__name__} imports {module!r}, which is not "
                            f"importable ({exc})")
            continue
        for name in names:
            if hasattr(imported, name):
                continue
            # A submodule is a legal `from package import submodule`, and only
            # shows up as an attribute once it has been imported itself.
            try:
                importlib.import_module(f"{module}.{name}")
            except ImportError:
                failures.append(f"{func.__name__} imports {name!r} from "
                                f"{module!r}, which does not define it")
    return failures


def _scheduled():
    """``(entry_name, dotted_path)`` for every beat entry, sorted."""
    return sorted((name, entry["task"])
                  for name, entry in settings.CELERY_BEAT_SCHEDULE.items())


def test_every_beat_entry_names_a_registered_task():
    """Conjunct 1: the entry is a name the scheduler can actually enqueue."""
    reasons = [reason for _, dotted in _scheduled()
               if (reason := resolve_task(dotted)[1]) is not None]
    assert not reasons, "\n".join(reasons)


def test_every_scheduled_task_can_import_what_its_body_imports():
    """Conjunct 2: the dependencies a lazy import hides still exist."""
    failures = []
    for name, dotted in _scheduled():
        task, reason = resolve_task(dotted)
        if task is None:
            continue  # conjunct 1 owns this one; do not report it twice
        for failure in unresolved_body_imports(task):
            failures.append(f"beat entry {name!r}: {failure}")
    assert not failures, "\n".join(failures)


def test_the_walk_reached_the_schedule_it_judges():
    """Vacuity guard: a walker that reads nothing passes everything.

    Two floors, because they fail differently. The entry count catches a
    settings import that stopped resolving the schedule; the import count
    catches the subtler case — entries still resolve, but the body walk no
    longer reaches the lazy imports conjunct 2 is entirely about.
    """
    entries = _scheduled()
    assert len(entries) >= MIN_ENTRIES, f"only found {len(entries)} beat entries"
    inspected = 0
    for _, dotted in entries:
        task, _reason = resolve_task(dotted)
        if task is not None:
            inspected += sum(1 for _ in iter_body_imports(task))
    assert inspected >= MIN_BODY_IMPORTS, (
        f"the walk inspected only {inspected} imports inside scheduled task "
        f"bodies — these tasks import lazily by design, so a number this low "
        f"means the body walk has stopped reaching its subject")


# ---------------------------------------------------------------------------
# Negative controls. The tree is clean, so both conjuncts above are absence
# tests; these prove the two resolvers flag what they claim to flag. They name
# kernel symbols only — a control that pinned another product's model would go
# red when THAT product deleted it, turning a test about beat into a test about
# somebody else's refactor.
# ---------------------------------------------------------------------------

def _task_with_a_dead_module_path():
    from apps.platform.work.no_such_module import thing  # noqa: F401


def _task_with_a_dead_submodule_name():
    # The other spelling of the same deletion, and the one that actually
    # shipped: the package still resolves, so only the NAME is missing.
    from apps.platform.work import no_such_module  # noqa: F401


def _task_with_a_dead_name_import():
    from apps.platform.work.models import NoSuchModel  # noqa: F401


def _task_with_a_dead_relative_import():
    # Anchored on this module's package (`apps.platform.tests`), so two dots
    # reach `apps.platform` — the branch in `iter_body_imports` that would
    # otherwise be the one unexercised path in the walker.
    from ..work.models import NoSuchModel  # noqa: F401


def _task_with_a_live_relative_import():
    from ..work.models import Task  # noqa: F401


def _task_with_a_live_import():
    from apps.platform.work.models import Task  # noqa: F401


def test_the_seat_quantity_reconciler_runs_hourly_after_the_mirror_reconciler():
    """R10 Stage C4 (A-2, RULED Q8): the pass that converges every billed seat
    quantity on its live roster reads the subscription mirror's status, so it
    is scheduled every hour, AFTER the mirror reconciler has refreshed it, and
    rides the subscriptions queue. A schedule fact, read by name: no product
    code is imported here."""
    schedule = settings.CELERY_BEAT_SCHEDULE
    seats = schedule["reconcile-subscription-seat-quantities"]
    mirrors = schedule["reconcile-subscription-mirrors"]
    assert seats["task"] == "apps.subscriptions.tasks.reconcile_subscription_seat_quantities"
    for entry in (seats, mirrors):
        assert entry["schedule"].hour == set(range(24))      # every hour
        assert len(entry["schedule"].minute) == 1             # once in it
    assert min(seats["schedule"].minute) > min(mirrors["schedule"].minute)
    task, reason = resolve_task(seats["task"])
    assert task is not None, reason
    assert task.queue == "ubb_subscriptions"


def test_a_dotted_path_that_does_not_resolve_is_caught():
    for dotted, fragment in (
        ("apps.platform.work.no_such_module.some_task", "importing"),
        ("apps.platform.tests.test_beat_schedule.no_such_attribute", "no attribute"),
        ("apps.platform.tests.test_beat_schedule.resolve_task", "not in the Celery task registry"),
    ):
        task, reason = resolve_task(dotted)
        assert task is None and fragment in reason, (dotted, reason)


def test_a_body_import_that_would_raise_at_runtime_is_caught():
    for func, fragment in (
        (_task_with_a_dead_module_path, "not importable"),
        (_task_with_a_dead_submodule_name, "does not define it"),
        (_task_with_a_dead_name_import, "does not define it"),
        (_task_with_a_dead_relative_import, "does not define it"),
    ):
        failures = unresolved_body_imports(func)
        assert len(failures) == 1 and fragment in failures[0], (func, failures)
    assert unresolved_body_imports(_task_with_a_live_import) == []
    assert unresolved_body_imports(_task_with_a_live_relative_import) == []


def test_the_relative_import_control_anchors_where_it_claims_to():
    """The relative controls are only evidence if they resolve where intended —
    a two-dot import that silently anchored elsewhere would make the failing
    control pass for the wrong reason."""
    assert list(iter_body_imports(_task_with_a_live_relative_import)) == [
        ("apps.platform.work.models", ("Task",))]


# ---------------------------------------------------------------------------
# What a REAL process sees (W7 preparation findings F1 and F2, ruled 2026-10-30).
#
# Everything above resolves a beat entry by importing its module first, so it
# cannot notice a task that no process imports. Two were: `core.tasks` (not an
# installed app) and `apps.platform.events.tasks_webhook_cleanup` (not named
# `tasks.py`), both invisible to `autodiscover_tasks`, so beat published them by
# bare name to the default `celery` queue no worker consumes. And the web process
# never imported `config.celery` at all, so every `.delay()` it issued bound to
# Celery's default app and failed. Each check below therefore runs in a FRESH
# interpreter, doing only what the real process does, and reports back as JSON.
# ---------------------------------------------------------------------------
import json
import os
import subprocess
import sys

_WORKER_VIEW = """
import json, django
django.setup()
from django.conf import settings
from config.celery import app
app.loader.import_default_modules()   # what worker and beat do at start-up
declared = sorted(q.name for q in settings.CELERY_TASK_QUEUES)
entries = {}
for name, spec in settings.CELERY_BEAT_SCHEDULE.items():
    task = app.tasks.get(spec["task"])
    entries[spec["task"]] = {"registered": task is not None,
                             "queue": getattr(task, "queue", None) if task else None}
print(json.dumps({"declared": declared, "entries": entries}))
"""

_WEB_VIEW = """
import json, logging, sys, uuid
import config.wsgi           # exactly what gunicorn imports
import config.urls           # what the first routed request loads
from django.conf import settings
from apps.platform.events import outbox, tasks
app = tasks.process_single_event._get_app()
marker = str(uuid.uuid4())
records = []
class Capture(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())
logging.getLogger("ubb.events").addHandler(Capture())
outbox._dispatch(marker)     # the doorbell a usage write rings on commit
import redis
client = redis.from_url(app.conf.broker_url)
raw = next((m for m in client.lrange("ubb_events", 0, 200) if marker.encode() in m), None)
if raw is not None:
    client.lrem("ubb_events", 1, raw)
print(json.dumps({
    "config_celery_loaded": "config.celery" in sys.modules,
    "app": app.main,
    "broker_is_settings_broker": app.conf.broker_url == settings.CELERY_BROKER_URL,
    "dispatch_failed_logged": any("dispatch_failed" in m for m in records),
    "message_reached_ubb_events": raw is not None,
}))
"""


def _as_a_fresh_process(script):
    env = dict(os.environ, DJANGO_SETTINGS_MODULE="config.settings",
               PYTHONIOENCODING="utf-8", PYTHONPATH=str(settings.BASE_DIR))
    proc = subprocess.run([sys.executable, "-c", script], cwd=settings.BASE_DIR,
                          capture_output=True, text=True, encoding="utf-8", env=env)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_every_scheduled_task_is_registered_and_routable_as_the_worker_sees_it():
    """F2. Registered after the loader's own start-up import — not after this
    test imported it — and carrying a `queue` the worker is told to consume."""
    view = _as_a_fresh_process(_WORKER_VIEW)
    declared = set(view["declared"])
    faults = [f"{name}: registered={facts['registered']} queue={facts['queue']}"
              for name, facts in sorted(view["entries"].items())
              if not facts["registered"] or facts["queue"] not in declared]
    assert not faults, "\n".join(faults)
    # The two this fix exists for, named so the assertion can never go vacuous.
    for name in ("core.tasks.flush_api_key_last_used",
                 "apps.platform.events.tasks_webhook_cleanup.cleanup_webhook_delivery_attempts"):
        assert view["entries"][name]["registered"], name


def test_the_web_import_path_binds_shared_tasks_to_the_configured_app():
    """F1. Importing what gunicorn imports loads the configured app, and the
    outbox doorbell publishes to its broker without `outbox.dispatch_failed`."""
    view = _as_a_fresh_process(_WEB_VIEW)
    assert view["config_celery_loaded"], view
    assert view["app"] == "ubb_platform", view
    assert view["broker_is_settings_broker"], view
    assert not view["dispatch_failed_logged"], view
    assert view["message_reached_ubb_events"], view
