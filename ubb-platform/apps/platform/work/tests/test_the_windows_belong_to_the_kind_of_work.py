"""How long work may go quiet, and how long it may run at all (#412, spec §7).

Two independent windows, each on the three-rung ladder the COGS ceiling
already climbs: the declared kind of work, then the tenant's own default, then
UBB's backstop. The kind of work's own declaration makes the argument for both
— one kind that legitimately costs twenty times its sibling should not force
the cap open on both, and one that legitimately runs twenty minutes between
usage reports should not force the silence window open on both either.

The two windows bound different things and neither implies the other:

  * the SILENCE window bounds time since the last usage report, and reporting
    usage is the ONLY thing that proves a unit is alive. There is no keepalive
    call and no read extends a unit's life — an implicit keepalive on reads was
    rejected outright, because a console listing, a support query or an admin
    inspecting stopped work would silently resurrect it.
  * the ABSOLUTE deadline bounds total age regardless of activity, and it
    cannot be switched off at any rung. Dropping it was considered and
    rejected: it is the guard that stops any tenant getting an immortal unit.

⚠ EVERY ASSERTION ABOUT A STOP REASON NAMES A CONSTANT, NEVER A STRING VALUE.
One of the two the sweepers write is sourced from the registry and one keeps
this module's own word, so a test spelling either would be asserting the very
thing that is allowed to move.
"""
import ast
from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import TaskLimitExceeded
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons
from apps.platform.work.models import Task, TaskType
from apps.platform.work.queries import (
    ABSOLUTE_DEADLINE_BACKSTOP_SECONDS, EXPIRY_LADDER_FALLBACK,
    SILENCE_WINDOW_BACKSTOP_SECONDS, expiry_windows, task_rollup_by_type,
    task_type_policy)
from apps.platform.work.services import TaskService
from apps.platform.work.tasks import close_abandoned_tasks, reap_stale_tasks
import core.vocabulary as generated
from core.vocabulary import (
    REASON_CODE_KNOWN_VALUES, TASK_STATUS_ACTIVE, TASK_STATUS_EXPIRED,
    TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK, TRIGGER_SOURCE_KNOWN_VALUES,
    TRIGGER_SOURCE_STALE_REAPER)

HOUR = 60 * 60

#: The generated handle for each of one concept's values, DERIVED from the
#: artifact rather than listed here. A list would be a statement about this
#: file; walking the artifact makes it a statement about the registry, which is
#: what the census asks and therefore what a test of the payment must ask.
TRIGGER_SOURCE_NAMES = frozenset(
    name for name in vars(generated)
    if name.startswith("TRIGGER_SOURCE_") and not name.endswith("_KNOWN_VALUES"))


class WindowTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Windows", products=["metering", "billing"],
            enforcement_mode="enforcing")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1")

    def _kind(self, key, *, kind=TASK_TYPE_KIND_TASK, silence=None,
              deadline=None):
        return TaskType.objects.create(
            tenant=self.tenant, key=key, kind=kind,
            silence_window_seconds=silence,
            absolute_deadline_seconds=deadline)

    def _unit(self, *, task_type="", parent=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            billing_owner_id=self.customer.id, task_type=task_type,
            parent=parent)

    def _age(self, unit, *, created=None, reported=None):
        """Put a unit's two timestamps where a sweeper will read them.

        Written with `update()` rather than `save()` because `created_at` is
        maintained by the base model and a save would stamp it back to now.
        """
        fields = {}
        if created is not None:
            fields["created_at"] = timezone.now() - created
        if reported is not None:
            fields["last_event_at"] = timezone.now() - reported
        Task.objects.filter(id=unit.id).update(**fields)
        unit.refresh_from_db()
        return unit

    def _windows(self, key=None, kind=TASK_TYPE_KIND_TASK):
        resolved = expiry_windows(self.tenant.id)
        if key is None:
            return resolved[EXPIRY_LADDER_FALLBACK]
        return resolved[(kind, key)]


class TheSilenceLadderTest(WindowTestBase):
    """One rung per case, and each case neutralises the rungs above it.

    A rung test that leaves a higher rung set proves nothing about the rung it
    names, because the higher one would answer identically.
    """

    def test_the_declared_kind_of_work_wins(self):
        self.tenant.task_stale_seconds = 1800
        self.tenant.save(update_fields=["task_stale_seconds"])
        self._kind("slow-crawl", silence=7200)
        self.assertEqual(self._windows("slow-crawl").silence, 7200)

    def test_the_tenant_default_answers_where_the_kind_declares_nothing(self):
        self.tenant.task_stale_seconds = 1800
        self.tenant.save(update_fields=["task_stale_seconds"])
        self._kind("ordinary")
        self.assertEqual(self._windows("ordinary").silence, 1800)
        # And for work whose kind this tenant has never declared at all.
        self.assertEqual(self._windows().silence, 1800)

    def test_ubbs_backstop_answers_where_neither_declares_anything(self):
        self.assertIsNone(self.tenant.task_stale_seconds)
        self._kind("ordinary")
        self.assertEqual(self._windows("ordinary").silence,
                         SILENCE_WINDOW_BACKSTOP_SECONDS)
        self.assertEqual(self._windows().silence, SILENCE_WINDOW_BACKSTOP_SECONDS)

    def test_a_kind_of_work_may_declare_that_it_has_no_silence_window(self):
        """Zero is a declaration, not an absence — which is why it does NOT
        fall through to the tenant rung beneath it."""
        self.tenant.task_stale_seconds = 60
        self.tenant.save(update_fields=["task_stale_seconds"])
        self._kind("long-atomic", silence=0)
        self.assertIsNone(self._windows("long-atomic").silence)
        self.assertEqual(self._windows().silence, 60)

    def test_a_tenant_may_declare_that_it_wants_no_silence_window(self):
        """The meaning zero has always had on the tenant column, preserved:
        reading it as a fall-through would silently re-arm a sweeper somebody
        switched off."""
        self.tenant.task_stale_seconds = 0
        self.tenant.save(update_fields=["task_stale_seconds"])
        self.assertIsNone(self._windows().silence)

    def test_a_kind_of_work_reclaims_a_window_its_tenant_switched_off(self):
        self.tenant.task_stale_seconds = 0
        self.tenant.save(update_fields=["task_stale_seconds"])
        self._kind("chatty", silence=30)
        self.assertEqual(self._windows("chatty").silence, 30)


class TheAbsoluteLadderTest(WindowTestBase):
    def test_the_declared_kind_of_work_wins(self):
        self.tenant.task_absolute_deadline_seconds = 3 * HOUR
        self.tenant.save(update_fields=["task_absolute_deadline_seconds"])
        self._kind("overnight", deadline=12 * HOUR)
        self.assertEqual(self._windows("overnight").absolute, 12 * HOUR)

    def test_the_tenant_default_answers_where_the_kind_declares_nothing(self):
        self.tenant.task_absolute_deadline_seconds = 3 * HOUR
        self.tenant.save(update_fields=["task_absolute_deadline_seconds"])
        self._kind("ordinary")
        self.assertEqual(self._windows("ordinary").absolute, 3 * HOUR)
        self.assertEqual(self._windows().absolute, 3 * HOUR)

    def test_ubbs_backstop_answers_where_neither_declares_anything(self):
        self.assertIsNone(self.tenant.task_absolute_deadline_seconds)
        self._kind("ordinary")
        self.assertEqual(self._windows("ordinary").absolute,
                         ABSOLUTE_DEADLINE_BACKSTOP_SECONDS)
        self.assertEqual(self._windows().absolute,
                         ABSOLUTE_DEADLINE_BACKSTOP_SECONDS)

    def test_no_resolved_deadline_is_ever_absent(self):
        """The two windows are not symmetric and the map says so: silence may
        resolve to nothing, the deadline may not."""
        self._kind("a", silence=0)
        self._kind("b", kind=TASK_TYPE_KIND_SUBTASK, silence=0)
        for pair in expiry_windows(self.tenant.id).values():
            self.assertIsNotNone(pair.absolute)


class TheDeadlineCannotBeRemovedTest(WindowTestBase):
    """The rejected option, refused where it cannot be argued around.

    "No tenant gets an immortal unit" is a claim about every write to either
    column, so the database is what has to hold it — a service-layer refusal
    would be true only of the paths that happen to go through the service.
    """

    def test_a_kind_of_work_cannot_declare_a_zero_deadline(self):
        with self.assertRaises(IntegrityError) as raised:
            with transaction.atomic():
                self._kind("immortal", deadline=0)
        self.assertIn("ck_task_type_absolute_deadline_positive",
                      str(raised.exception))

    def test_a_tenant_cannot_declare_a_zero_deadline(self):
        with self.assertRaises(IntegrityError) as raised:
            with transaction.atomic():
                Tenant.objects.filter(id=self.tenant.id).update(
                    task_absolute_deadline_seconds=0)
        self.assertIn("ck_tenant_absolute_deadline_positive",
                      str(raised.exception))

    def test_a_kind_of_work_with_no_silence_window_still_cannot_run_forever(self):
        """The two rules together: silence may be switched off at every rung,
        and the unit is expired anyway once the backstop deadline passes."""
        self.tenant.task_stale_seconds = 0
        self.tenant.save(update_fields=["task_stale_seconds"])
        self._kind("long-atomic", silence=0)
        unit = self._unit(task_type="long-atomic")
        self._age(unit, created=timedelta(minutes=30), reported=timedelta(minutes=1))
        reap_stale_tasks()
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_ACTIVE)

        self._age(unit,
                  created=timedelta(seconds=ABSOLUTE_DEADLINE_BACKSTOP_SECONDS + 60),
                  reported=timedelta(minutes=1))
        reap_stale_tasks()
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_EXPIRED)
        self.assertEqual(unit.metadata.get("kill_reason"), reasons.STALE_MAX_AGE)


class TheAnnouncingSweeperReadsTheLadderTest(WindowTestBase):
    """The end-to-end half: the resolved pair is what actually decides."""

    def test_a_declared_silence_window_widens_what_the_sweeper_leaves_alone(self):
        self._kind("slow-crawl", silence=2 * HOUR)
        slow = self._unit(task_type="slow-crawl")
        ordinary = self._unit()
        for unit in (slow, ordinary):
            self._age(unit, created=timedelta(minutes=40),
                      reported=timedelta(minutes=30))
        reap_stale_tasks()
        slow.refresh_from_db()
        ordinary.refresh_from_db()
        # One tenant, one silence, two answers — which is the whole point.
        self.assertEqual(slow.status, TASK_STATUS_ACTIVE)
        self.assertEqual(ordinary.status, TASK_STATUS_EXPIRED)
        self.assertEqual(ordinary.metadata.get("kill_reason"),
                         reasons.SILENCE_WINDOW)

    def test_a_declared_silence_window_narrows_it_too(self):
        self.tenant.task_stale_seconds = 4 * HOUR
        self.tenant.save(update_fields=["task_stale_seconds"])
        self._kind("chatty", silence=60)
        chatty = self._unit(task_type="chatty")
        self._age(chatty, created=timedelta(minutes=40),
                  reported=timedelta(minutes=5))
        reap_stale_tasks()
        chatty.refresh_from_db()
        self.assertEqual(chatty.status, TASK_STATUS_EXPIRED)

    def test_a_declared_deadline_bounds_work_that_is_still_reporting(self):
        self._kind("runaway", deadline=HOUR)
        runaway = self._unit(task_type="runaway")
        self._age(runaway, created=timedelta(hours=2),
                  reported=timedelta(seconds=5))
        reap_stale_tasks()
        runaway.refresh_from_db()
        self.assertEqual(runaway.status, TASK_STATUS_EXPIRED)
        self.assertEqual(runaway.metadata.get("kill_reason"),
                         reasons.STALE_MAX_AGE)

    def test_the_announcement_names_the_mechanism_beside_the_cause(self):
        """Two fields because they are two questions (#412). The reason moves
        between the two windows and the mechanism does not, which is what a
        subscriber classifying by mechanism needs and cannot get by parsing
        a reason string."""
        self._kind("runaway", silence=60, deadline=HOUR)
        quiet = self._unit(task_type="runaway")
        self._age(quiet, created=timedelta(minutes=30),
                  reported=timedelta(minutes=5))
        overrun = self._unit(task_type="runaway")
        self._age(overrun, created=timedelta(hours=2),
                  reported=timedelta(seconds=5))
        reap_stale_tasks()

        announced = {
            row.payload["task_id"]: row.payload
            for row in OutboxEvent.objects.filter(
                event_type=TaskLimitExceeded.EVENT_TYPE)}
        self.assertEqual(announced[str(quiet.id)]["reason"],
                         reasons.SILENCE_WINDOW)
        self.assertEqual(announced[str(overrun.id)]["reason"],
                         reasons.STALE_MAX_AGE)
        for payload in announced.values():
            self.assertEqual(payload["trigger_source"],
                             TRIGGER_SOURCE_STALE_REAPER)

    def test_the_deadline_is_the_reason_when_both_windows_have_elapsed(self):
        """The more serious of the two facts stays on the record: saying the
        tenant went quiet about work that had in fact run out of time would
        describe the wrong thing."""
        self._kind("runaway", silence=60, deadline=HOUR)
        unit = self._unit(task_type="runaway")
        self._age(unit, created=timedelta(hours=2), reported=timedelta(hours=1))
        reap_stale_tasks()
        unit.refresh_from_db()
        self.assertEqual(unit.metadata.get("kill_reason"), reasons.STALE_MAX_AGE)

    def test_work_that_never_reported_is_not_silent(self):
        """Silence is measured from the last report, so a unit that has never
        made one is slow to start rather than quiet — it belongs to the
        baseline sweeper, which reaps on age alone."""
        self._kind("chatty", silence=60)
        unit = self._unit(task_type="chatty")
        self._age(unit, created=timedelta(minutes=30))
        self.assertIsNone(unit.last_event_at)
        reap_stale_tasks()
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_ACTIVE)

    def test_one_word_names_two_kinds_of_work_with_different_windows(self):
        """A kind of work is `(altitude, key)` and never the key alone, so the
        parent link is what selects between two declarations sharing a word."""
        self._kind("render", kind=TASK_TYPE_KIND_TASK, silence=4 * HOUR)
        self._kind("render", kind=TASK_TYPE_KIND_SUBTASK, silence=60)
        parent = self._unit(task_type="render")
        contained = self._unit(task_type="render", parent=parent)
        for unit in (parent, contained):
            self._age(unit, created=timedelta(minutes=40),
                      reported=timedelta(minutes=30))
        reap_stale_tasks()
        parent.refresh_from_db()
        contained.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        self.assertEqual(contained.status, TASK_STATUS_EXPIRED)


class TheBaselineSweeperReadsTheLadderTest(WindowTestBase):
    """The unannounced sweeper runs for every tenant, including the ones with
    no reaper of their own, so a declared window has to reach it too.

    What the windows decide HERE is liveness, not reaping: this sweeper's
    subject is work nobody closed, and its one-hour floor is unchanged. A unit
    inside both of its windows is alive and exempt from that floor; a unit past
    either is not exempt, and is swept once it is also older than an hour.
    """

    def setUp(self):
        super().setUp()
        self.tenant.enforcement_mode = "off"
        self.tenant.save(update_fields=["enforcement_mode"])

    def test_a_declared_silence_window_keeps_work_alive_past_the_floor(self):
        self._kind("slow-crawl", silence=4 * HOUR)
        slow = self._unit(task_type="slow-crawl")
        ordinary = self._unit()
        for unit in (slow, ordinary):
            self._age(unit, created=timedelta(hours=2),
                      reported=timedelta(hours=1))
        close_abandoned_tasks()
        slow.refresh_from_db()
        ordinary.refresh_from_db()
        self.assertEqual(slow.status, TASK_STATUS_ACTIVE)
        self.assertEqual(ordinary.status, TASK_STATUS_EXPIRED)

    def test_a_declared_deadline_sweeps_work_the_silence_window_would_spare(self):
        self._kind("runaway", silence=4 * HOUR, deadline=90 * 60)
        unit = self._unit(task_type="runaway")
        self._age(unit, created=timedelta(hours=2), reported=timedelta(minutes=1))
        close_abandoned_tasks()
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_EXPIRED)

    def test_a_tenant_that_declared_nothing_is_swept_exactly_as_before(self):
        """The backstops ARE the durations this sweeper used to spell, so the
        pre-ladder behaviour is what a tenant with an empty registry gets."""
        alive = self._unit()
        silent = self._unit()
        self._age(alive, created=timedelta(hours=2), reported=timedelta(minutes=1))
        self._age(silent, created=timedelta(hours=2), reported=timedelta(minutes=30))
        close_abandoned_tasks()
        alive.refresh_from_db()
        silent.refresh_from_db()
        self.assertEqual(alive.status, TASK_STATUS_ACTIVE)
        self.assertEqual(silent.status, TASK_STATUS_EXPIRED)

    def test_work_with_no_configuration_anywhere_still_cannot_run_forever(self):
        self.assertEqual(TaskType.objects.filter(tenant=self.tenant).count(), 0)
        self.assertIsNone(self.tenant.task_stale_seconds)
        self.assertIsNone(self.tenant.task_absolute_deadline_seconds)
        unit = self._unit()
        self._age(unit,
                  created=timedelta(seconds=ABSOLUTE_DEADLINE_BACKSTOP_SECONDS + 60),
                  reported=timedelta(seconds=1))
        close_abandoned_tasks()
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_EXPIRED)


class LivenessIsProvedByReportingUsageTest(WindowTestBase):
    """There is no keepalive, and no read may become one."""

    #: The modules that write the liveness stamp, and how many times each does.
    #:
    #: A COUNT rather than a bare set of names, because a set only makes the
    #: easier half of the claim — that no OTHER module writes it — and would
    #: stay green over a second write appearing inside the one module that is
    #: allowed one. The single writer is the accumulate primitive, which is the
    #: whole rule: usage reports prove liveness and nothing else does.
    WRITES_THE_LIVENESS_STAMP = {"apps/platform/work/services.py": 1}

    STAMP = "last_event_at"
    BACKEND = Path(__file__).resolve().parents[4]

    def _writes(self, tree):
        """Every assignment to the stamp in one module: a bare attribute
        assignment, a keyword to a `create()`/`update()` call, or a dict entry
        in a `defaults=`. A reader that only looked for `x.stamp = y` would
        miss the two idioms Django code actually uses."""
        found = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                found += sum(
                    1 for t in node.targets
                    if isinstance(t, ast.Attribute) and t.attr == self.STAMP)
            elif isinstance(node, ast.Call):
                found += sum(1 for kw in node.keywords if kw.arg == self.STAMP)
                for kw in node.keywords:
                    if isinstance(kw.value, ast.Dict):
                        found += sum(
                            1 for k in kw.value.keys
                            if isinstance(k, ast.Constant) and k.value == self.STAMP)
        return found

    def test_the_only_writer_of_the_liveness_stamp_is_the_usage_report(self):
        writers = {}
        for path in sorted(self.BACKEND.rglob("*.py")):
            relative = path.relative_to(self.BACKEND).as_posix()
            if "/migrations/" in f"/{relative}" or "/tests/" in f"/{relative}":
                continue
            source = path.read_text(encoding="utf-8")
            if self.STAMP not in source:
                continue
            if count := self._writes(ast.parse(source)):
                writers[relative] = count
        self.assertEqual(writers, self.WRITES_THE_LIVENESS_STAMP)

    def test_reading_a_quiet_unit_does_not_extend_its_life(self):
        """The rejected option, measured. An implicit keepalive on reads would
        mean an admin looking at stopped work resurrected it — so the read
        contract is driven here first, and the sweeper must still take it."""
        self._kind("chatty", silence=60)
        unit = self._unit(task_type="chatty")
        self._age(unit, created=timedelta(minutes=40),
                  reported=timedelta(minutes=30))
        before = Task.objects.get(id=unit.id).last_event_at

        # Every read a support query or a console listing has of this unit.
        self.assertIsNotNone(task_type_policy(
            self.tenant.id, "chatty", TASK_TYPE_KIND_TASK))
        task_rollup_by_type(self.tenant.id)
        expiry_windows(self.tenant.id)

        self.assertEqual(Task.objects.get(id=unit.id).last_event_at, before)
        reap_stale_tasks()
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_EXPIRED)

    def test_a_usage_report_is_what_keeps_a_unit_alive(self):
        """The positive control for the case above: the same unit, the same
        window, and the one call that IS a keepalive."""
        self._kind("chatty", silence=60)
        unit = self._unit(task_type="chatty")
        self._age(unit, created=timedelta(minutes=40),
                  reported=timedelta(minutes=30))
        TaskService.accumulate_cost(unit.id, billed_cost_micros=1,
                                    provider_cost_micros=1)
        reap_stale_tasks()
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_ACTIVE)


class TheWordsTheseStopsTravelUnderTest(TestCase):
    """What the stop-reason module takes from the registry, and what it keeps.

    The two windows above each produce a stop, and a stop's cause is a registry
    concept whose declared backend consumer IS that module. So the windows and
    the words they emit are one subject: the module holds by reference every
    value the registry has a word for and this slice can produce, and keeps its
    own only where the registry has none.

    ⚠ THE ASSERTIONS READ THE MODULE'S OWN IMPORT AND ASSIGNMENT STATEMENTS,
    not the values. Comparing a constant to the generated one is satisfied by a
    literal that happens to agree, which is exactly the debt this pays; and
    membership in `vars()` is defeated by an aliased import, which binds a new
    name over one shared value. The census measures references, so the test
    that means anything measures references too.
    """

    MODULE = Path(reasons.__file__)
    GENERATED = "core.vocabulary"

    def _referenced(self, prefix):
        """The names this module imports from the generated artifact under one
        concept's prefix, and the module constants each is bound to."""
        tree = ast.parse(self.MODULE.read_text(encoding="utf-8"))
        imported = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == self.GENERATED
            for alias in node.names
            if alias.name.startswith(prefix) and alias.asname is None
        }
        bound = {
            node.targets[0].id: node.value.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Name)
            and node.value.id.startswith(prefix)
        }
        return imported, bound

    def test_every_mechanism_that_can_apply_a_stop_is_held_by_reference(self):
        """All five, which is what makes the concept's backend debt payable
        here rather than partly here."""
        imported, _ = self._referenced("TRIGGER_SOURCE_")
        self.assertEqual(imported, TRIGGER_SOURCE_NAMES)
        self.assertEqual(reasons.KNOWN_TRIGGER_SOURCES,
                         TRIGGER_SOURCE_KNOWN_VALUES)

    def test_exactly_two_stop_causes_are_held_by_reference(self):
        """And which two is the claim, not how many. The other three known
        values are end-state names for mechanisms that do not exist yet, so
        importing them would be this module performing another slice's renames
        on paths it cannot drive."""
        imported, bound = self._referenced("REASON_CODE_")
        self.assertEqual(imported, {"REASON_CODE_PARENT_KILLED",
                                    "REASON_CODE_SILENCE_WINDOW"})
        self.assertEqual(bound, {"PARENT_KILLED": "REASON_CODE_PARENT_KILLED",
                                 "SILENCE_WINDOW": "REASON_CODE_SILENCE_WINDOW"})

    def test_the_silence_windows_stop_is_a_word_the_registry_knows(self):
        self.assertIn(reasons.SILENCE_WINDOW, REASON_CODE_KNOWN_VALUES)

    def test_the_deadlines_stop_travels_as_a_word_the_registry_does_not_know(self):
        """Legal rather than owed: the concept is open, so a value it has never
        seen travels instead of being refused at the boundary. Coining one here
        would be this module inventing a name the registry owns."""
        self.assertNotIn(reasons.STALE_MAX_AGE, REASON_CODE_KNOWN_VALUES)

    def test_the_two_a_sweeper_writes_are_two_and_are_both_stop_reasons(self):
        self.assertNotEqual(reasons.SILENCE_WINDOW, reasons.STALE_MAX_AGE)
        self.assertIn(reasons.SILENCE_WINDOW, reasons.ALL_REASONS)
        self.assertIn(reasons.STALE_MAX_AGE, reasons.ALL_REASONS)
