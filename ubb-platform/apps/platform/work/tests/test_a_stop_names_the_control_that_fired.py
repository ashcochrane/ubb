"""A stop names the control that fired — the kernel's half (#458, slice 6 §1,
§15), and migration `0027` that stamps it on every stored row.

The kernel STAMPS the family from the one map in `core.controls` and RECORDS
the id the caller passed, both beside the cause on the row; a cascade copies
its parent's; the announcement and the re-mint read the row. The route-driven
half — every lane through the recording route, the sweeper and the durable
lanes — is `api/v1/tests/test_every_stop_names_the_control_that_fired.py`;
this module holds the seams to the rows.
"""
import importlib

from django.apps import apps as global_apps
from django.test import TestCase

from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import TaskExpired, TaskKilled
from apps.platform.work import reasons
from apps.platform.work.models import (
    CEILING_BASIS_CHOICES, STOP_CAUSE_KEY, STOP_CONTROL_FAMILY_KEY,
    STOP_CONTROL_ID_KEY, STOP_MECHANISM_KEY, Task, TaskType)
from apps.platform.work.services import TaskService, ceiling_control_id
from apps.platform.work.tests._helpers import WorkTestBase
from core import controls
from core.vocabulary import (
    CEILING_BASIS_COST, CEILING_BASIS_TIME, CEILING_BASIS_VALUES,
    CONTROL_FAMILY_CEILING, TASK_STATUS_KILLED, TASK_TYPE_KIND_SUBTASK,
    TASK_TYPE_KIND_TASK, TRIGGER_SOURCE_USAGE_INGEST)

MIGRATION = importlib.import_module(
    "apps.platform.work.migrations.0027_a_stopped_unit_records_the_control_that_fired")


class TheCeilingsControlIsTheDeclarationTest(WorkTestBase):
    def _kind(self, key, *, kind=TASK_TYPE_KIND_TASK):
        return TaskType.objects.create(tenant=self.tenant, key=key, kind=kind,
                                       uncapped=True)

    def test_a_declared_unit_names_its_kinds_row_at_its_own_altitude(self):
        whole = self._kind("pipeline")
        piece = self._kind("pipeline", kind=TASK_TYPE_KIND_SUBTASK)
        parent = self._task(task_type="pipeline")
        contained = self._task(task_type="pipeline", parent=parent)

        self.assertEqual(ceiling_control_id(parent), str(whole.id))
        self.assertEqual(ceiling_control_id(contained), str(piece.id))

    def test_an_undeclared_unit_names_the_tenant(self):
        self.assertEqual(ceiling_control_id(self._task()), str(self.tenant.id))

    def test_a_kind_the_tenant_never_declared_names_the_tenant_too(self):
        """The unit says a kind, the tenant declared none by that name: it
        runs on the tenant rung, and the tenant is the control."""
        self.assertEqual(ceiling_control_id(self._task(task_type="nobody")),
                         str(self.tenant.id))


class TheFlipStampsTheControlTest(WorkTestBase):
    def test_a_kill_records_family_and_id_beside_the_cause(self):
        unit = self._task(limit=1)
        killed, transitioned = TaskService.kill_task(
            unit.id, reasons.TASK_COGS_CEILING, control_id="the-declaration")

        self.assertTrue(transitioned)
        self.assertEqual(killed.metadata[STOP_CAUSE_KEY], reasons.TASK_COGS_CEILING)
        self.assertEqual(killed.metadata[STOP_CONTROL_FAMILY_KEY], CONTROL_FAMILY_CEILING)
        self.assertEqual(killed.metadata[STOP_CONTROL_ID_KEY], "the-declaration")
        self.assertEqual(killed.ceiling_basis, CEILING_BASIS_COST)

    def test_an_expiry_on_a_window_is_the_ceilings_on_time(self):
        unit = self._task()
        expired, _ = TaskService.expire_task(
            unit.id, reasons.ABSOLUTE_DEADLINE, control_id=str(self.tenant.id))

        self.assertEqual(expired.metadata[STOP_CONTROL_FAMILY_KEY], CONTROL_FAMILY_CEILING)
        self.assertEqual(expired.ceiling_basis, CEILING_BASIS_TIME)

    def test_a_flip_with_no_cause_stamps_no_control(self):
        """The baseline sweeper expires silently and names no bound."""
        unit = self._task()
        expired, _ = TaskService.expire_task(unit.id)
        for key in (STOP_CAUSE_KEY, STOP_CONTROL_FAMILY_KEY, STOP_CONTROL_ID_KEY):
            self.assertNotIn(key, expired.metadata)
        self.assertIsNone(expired.ceiling_basis)

    def test_a_cascades_word_passed_to_a_flip_directly_is_refused(self):
        """Contained work inherits its parent's family; a caller cannot stop a
        unit 'because its parent' from outside the cascade, because there is
        no family to stamp on it."""
        unit = self._task()
        with self.assertRaises(controls.NoFamilyOfItsOwn):
            TaskService.kill_task(unit.id, reasons.PARENT_KILLED)
        unit.refresh_from_db()
        self.assertNotEqual(unit.status, TASK_STATUS_KILLED)

    def test_the_cascade_copies_the_parents_family_and_id(self):
        parent = self._task(limit=1)
        contained = self._task(parent=parent)
        TaskService.kill_task(parent.id, reasons.TASK_COGS_CEILING,
                              control_id="the-parents-declaration")

        contained.refresh_from_db()
        self.assertEqual(contained.metadata[STOP_CAUSE_KEY], reasons.PARENT_KILLED)
        self.assertEqual(contained.metadata[STOP_MECHANISM_KEY], "parent_cascade")
        self.assertEqual(contained.metadata[STOP_CONTROL_FAMILY_KEY],
                         CONTROL_FAMILY_CEILING)
        self.assertEqual(contained.metadata[STOP_CONTROL_ID_KEY],
                         "the-parents-declaration")
        self.assertIsNone(contained.ceiling_basis)

    def test_the_announcement_reads_the_row_it_stamped(self):
        unit = self._task(limit=1)
        TaskService.kill_and_announce(
            unit.id, reasons.TASK_COGS_CEILING, tenant_id=self.tenant.id,
            customer_id=self.customer.id, trigger_source=TRIGGER_SOURCE_USAGE_INGEST,
            control_id=ceiling_control_id(unit))

        payload = self._events(TaskKilled.EVENT_TYPE).get().payload
        unit.refresh_from_db()
        self.assertEqual(payload["control_family"], unit.metadata[STOP_CONTROL_FAMILY_KEY])
        self.assertEqual(payload["control_id"], unit.metadata[STOP_CONTROL_ID_KEY])
        self.assertEqual(payload["ceiling_basis"], unit.ceiling_basis)


class TheWorkModelHoldsTheBasisTest(TestCase):
    def test_the_choices_are_the_registrys_two_by_reference(self):
        """`g2-backend-ceiling_basis`, on `CEILING_STATUS_CHOICES`'s footing:
        identities from the registry, wording written beside them, read by
        the admin's listing and by the row's own derived property."""
        self.assertEqual({identity for identity, _ in CEILING_BASIS_CHOICES},
                         CEILING_BASIS_VALUES)
        self.assertEqual(dict(CEILING_BASIS_CHOICES)[CEILING_BASIS_COST], "Cost")
        self.assertEqual(dict(CEILING_BASIS_CHOICES)[CEILING_BASIS_TIME], "Time")

    def test_the_admin_words_the_basis_and_blanks_a_stop_that_was_not_a_ceilings(self):
        from apps.platform.work.admin import TaskAdmin
        render = TaskAdmin.ceiling_basis
        self.assertEqual(render(None, Task(metadata={STOP_CAUSE_KEY: reasons.SILENCE_WINDOW})),
                         "Time")
        self.assertEqual(render(None, Task(metadata={STOP_CAUSE_KEY: reasons.HARD_FLOOR})), "")
        self.assertEqual(render(None, Task(metadata={})), "")


class Migration0027StampsEveryStoredRowTest(WorkTestBase):
    """The migration's second encoding of the names, held to the code, and
    the stamping on rows and queued payloads — called with the live registry
    as `0026`'s tests are, for the same reason: it changes no schema."""

    def test_the_names_are_the_codes(self):
        self.assertEqual(MIGRATION.CAUSE_KEY, STOP_CAUSE_KEY)
        self.assertEqual(MIGRATION.FAMILY_KEY, STOP_CONTROL_FAMILY_KEY)
        self.assertEqual(MIGRATION.CONTROL_KEY, STOP_CONTROL_ID_KEY)
        self.assertEqual(MIGRATION.FAMILY_CEILING, CONTROL_FAMILY_CEILING)
        self.assertEqual(MIGRATION.BASIS_BY_CAUSE, controls.CEILING_BASIS_BY_REASON)
        self.assertEqual(set(MIGRATION.TERMINAL_STOP_EVENTS),
                         {TaskKilled.EVENT_TYPE, TaskExpired.EVENT_TYPE,
                          "subtask.killed", "subtask.expired"})
        self.assertEqual((MIGRATION.KIND_TASK, MIGRATION.KIND_SUBTASK),
                         (TASK_TYPE_KIND_TASK, TASK_TYPE_KIND_SUBTASK))

    def _stopped(self, *, cause, task_type="", parent=None, **more):
        unit = self._task(task_type=task_type, parent=parent)
        Task.objects.filter(pk=unit.pk).update(
            status="killed", metadata={STOP_CAUSE_KEY: cause, **more})
        unit.refresh_from_db()
        return unit

    def test_a_stopped_row_is_stamped_the_ceilings_family_and_its_declaration(self):
        kind = TaskType.objects.create(tenant=self.tenant, key="k", uncapped=True)
        declared = self._stopped(cause=reasons.TASK_COGS_CEILING, task_type="k")
        undeclared = self._stopped(cause=reasons.SILENCE_WINDOW)
        untouched = self._task()

        MIGRATION._stamp_the_control(global_apps, None)

        declared.refresh_from_db()
        undeclared.refresh_from_db()
        untouched.refresh_from_db()
        self.assertEqual(declared.metadata[STOP_CONTROL_FAMILY_KEY], CONTROL_FAMILY_CEILING)
        self.assertEqual(declared.metadata[STOP_CONTROL_ID_KEY], str(kind.id))
        self.assertEqual(undeclared.metadata[STOP_CONTROL_ID_KEY], str(self.tenant.id))
        self.assertNotIn(STOP_CONTROL_FAMILY_KEY, untouched.metadata)

    def test_contained_work_a_cascade_stopped_takes_its_parents_control(self):
        """§1: a cascade inherits its parent's — on the historical rows too.
        The contained unit runs under its OWN declared kind, which would name
        a different row; what it records is the parent's."""
        parents_kind = TaskType.objects.create(tenant=self.tenant, key="pipe", uncapped=True)
        TaskType.objects.create(tenant=self.tenant, key="piece",
                                kind=TASK_TYPE_KIND_SUBTASK, uncapped=True)
        parent = self._stopped(cause=reasons.TASK_COGS_CEILING, task_type="pipe")
        contained = self._stopped(cause=reasons.PARENT_KILLED, task_type="piece",
                                  parent=parent)

        MIGRATION._stamp_the_control(global_apps, None)

        contained.refresh_from_db()
        self.assertEqual(contained.metadata[STOP_CONTROL_FAMILY_KEY], CONTROL_FAMILY_CEILING)
        self.assertEqual(contained.metadata[STOP_CONTROL_ID_KEY], str(parents_kind.id))

    def test_a_queued_payload_is_stamped_from_its_unit_and_its_own_cause(self):
        unit = self._stopped(cause=reasons.ABSOLUTE_DEADLINE)
        # A literal payload on purpose (`docs/conventions/testing.md`'s
        # exception): the POINT is the legacy shape a row queued before
        # #458 holds, which the current dataclass can no longer construct.
        queued = OutboxEvent.objects.create(
            event_type=TaskExpired.EVENT_TYPE, tenant_id=self.tenant.id,
            payload={"tenant_id": str(self.tenant.id), "task_id": str(unit.id),
                     STOP_CAUSE_KEY: reasons.ABSOLUTE_DEADLINE})

        MIGRATION._stamp_the_control(global_apps, None)

        queued.refresh_from_db()
        self.assertEqual(queued.payload["control_family"], CONTROL_FAMILY_CEILING)
        self.assertEqual(queued.payload["control_id"], str(self.tenant.id))
        self.assertEqual(queued.payload["ceiling_basis"], CEILING_BASIS_TIME)

    def test_a_row_already_stamped_is_not_written_and_the_reverse_forgets(self):
        unit = self._stopped(cause=reasons.TASK_COGS_CEILING,
                             **{STOP_CONTROL_FAMILY_KEY: CONTROL_FAMILY_CEILING,
                                STOP_CONTROL_ID_KEY: "kept"})

        MIGRATION._stamp_the_control(global_apps, None)
        unit.refresh_from_db()
        self.assertEqual(unit.metadata[STOP_CONTROL_ID_KEY], "kept")

        MIGRATION._forget_the_control(global_apps, None)
        unit.refresh_from_db()
        self.assertEqual(unit.metadata, {STOP_CAUSE_KEY: reasons.TASK_COGS_CEILING})
