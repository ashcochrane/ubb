"""The stop-context builder (#41, spec §H) — unit tests.

One pure-ish builder turns what the recording transaction already knows —
the accumulate verdicts, the (possibly killed) unit, the owner's durable
stop-signal state — into the immutable stop-context array stored on the
event. The rules pinned here:

- A fresh crossing verdict marks the TIPPING event: ``arrived_after=false``,
  ``tripped_at`` = the event's own record time.
- A late event on a limit-killed unit carries the SAME limit with
  ``arrived_after=true`` and the kill time as ``tripped_at`` — the episode's
  itemization stays coherent.
- A cascade-killed subtask's late events point at the PARENT's episode.
- Non-limit terminal states (completed / reaped) tag ``task_not_active``.
- Customer scope comes from the durable ledger's STOP lines (slice 6 §9):
  each open episode → that line's own word (the hard floor's, the pool's)
  with the line's episode id, one entry per open line; suspension without
  an open episode → ``suspended``. Soft-floor state NEVER marks (§F).
- One ceiling word at either altitude (slice 6 §7): the entry's scope says
  which altitude's ceiling was crossed, so cases key entries by SCOPE.
- Multiple simultaneous limits → one array entry per limit, nothing lost.
"""
from django.test import TestCase
from django.utils import timezone

from apps.billing.gating.models import StopSignalState
from apps.metering.usage.services.stop_context import build_stop_context
from apps.platform.customers.models import Customer
from apps.platform.work import reasons
from apps.platform.work.models import Task
from apps.platform.work.services import (
    STOP_CAUSE_KEY, CloseDeclaration, TaskService)
from apps.platform.tenants.models import Tenant
from core.vocabulary import TASK_OUTCOME_DELIVERED

NO_VERDICTS = {"crossed_task_limit": False, "crossed_subtask_limit": False,
               "task_not_active": False}


class StopContextTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Ctx", products=["metering", "billing"],
            billing_mode="prepaid", enforcement_mode="enforcing")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.now = timezone.now()

    def _task(self, parent=None, **extra):
        return Task.objects.create(
            tenant=self.tenant, customer=self.customer, parent=parent,
            balance_snapshot_micros=100_000_000,
            billing_owner_id=self.customer.id, **extra)

    def _build(self, task=None, verdicts=None, **kw):
        kw.setdefault("owner", self.customer)
        kw.setdefault("tenant", self.tenant)
        kw.setdefault("now", self.now)
        return build_stop_context(task=task, verdicts=verdicts, **kw)


class UnitContextTest(StopContextTestBase):
    def test_no_verdicts_no_customer_state_returns_none(self):
        task = self._task()
        self.assertIsNone(self._build(task, dict(NO_VERDICTS)))
        self.assertIsNone(self._build(None, None))

    def test_tipping_event_on_the_units_ceiling(self):
        task = self._task(task_cogs_ceiling_micros=10)
        ctx = self._build(task, dict(NO_VERDICTS, crossed_task_limit=True))
        self.assertEqual(ctx, [{
            "limit": reasons.TASK_COGS_CEILING, "stop_scope": "task",
            "tripped_at": self.now.isoformat(), "episode_seq": None,
            "task_id": str(task.id), "subtask_id": None,
            "arrived_after": False,
        }])

    def test_subtask_double_crossing_carries_both_contexts(self):
        parent = self._task(task_cogs_ceiling_micros=100)
        sub = self._task(parent=parent, task_cogs_ceiling_micros=10)
        ctx = self._build(sub, dict(NO_VERDICTS, crossed_task_limit=True,
                                    crossed_subtask_limit=True))
        self.assertEqual(len(ctx), 2)
        # ONE word, TWO scopes: the parent's crossing and the contained unit's
        # own are told apart by scope and by nothing else (slice 6 §7).
        by_scope = {c["stop_scope"]: c for c in ctx}
        self.assertEqual(set(by_scope), {"task", "subtask"})
        for entry in ctx:
            self.assertEqual(entry["limit"], reasons.TASK_COGS_CEILING)
            self.assertEqual(entry["task_id"], str(parent.id))
            self.assertEqual(entry["subtask_id"], str(sub.id))
        self.assertFalse(by_scope["task"]["arrived_after"])

    def test_late_event_on_limit_killed_task(self):
        task = self._task(task_cogs_ceiling_micros=10)
        TaskService.kill_task(task.id, reason=reasons.TASK_COGS_CEILING)
        task.refresh_from_db()
        ctx = self._build(task, dict(NO_VERDICTS, task_not_active=True))
        self.assertEqual(ctx, [{
            "limit": reasons.TASK_COGS_CEILING, "stop_scope": "task",
            "tripped_at": task.completed_at.isoformat(), "episode_seq": None,
            "task_id": str(task.id), "subtask_id": None,
            "arrived_after": True,
        }])

    def test_late_event_on_cascade_killed_subtask_points_at_parent_episode(self):
        parent = self._task(task_cogs_ceiling_micros=10)
        sub = self._task(parent=parent)
        TaskService.kill_task(parent.id, reason=reasons.TASK_COGS_CEILING)
        sub.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(sub.metadata[STOP_CAUSE_KEY], reasons.PARENT_KILLED)
        ctx = self._build(sub, dict(NO_VERDICTS, task_not_active=True))
        self.assertEqual(ctx, [{
            "limit": reasons.TASK_COGS_CEILING, "stop_scope": "task",
            "tripped_at": parent.completed_at.isoformat(), "episode_seq": None,
            "task_id": str(parent.id), "subtask_id": str(sub.id),
            "arrived_after": True,
        }])

    def test_late_event_on_completed_task_is_task_not_active(self):
        task = self._task()
        TaskService.close_task(task.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        task.refresh_from_db()
        ctx = self._build(task, dict(NO_VERDICTS, task_not_active=True))
        self.assertEqual(ctx, [{
            "limit": "task_not_active", "stop_scope": "task",
            "tripped_at": task.completed_at.isoformat(), "episode_seq": None,
            "task_id": str(task.id), "subtask_id": None,
            "arrived_after": True,
        }])

    def test_late_event_on_reaped_task_is_task_not_active(self):
        task = self._task()
        TaskService.kill_task(task.id, reason=reasons.SILENCE_WINDOW)
        task.refresh_from_db()
        ctx = self._build(task, dict(NO_VERDICTS, task_not_active=True))
        self.assertEqual(ctx[0]["limit"], "task_not_active")
        self.assertTrue(ctx[0]["arrived_after"])

    def test_late_subtask_event_that_trips_parent_limit_carries_both(self):
        # A late event on a killed subtask still rolls up and can tip the
        # PARENT's limit: both the fresh parent crossing and the subtask's
        # own late context ride the array.
        parent = self._task(task_cogs_ceiling_micros=10)
        sub = self._task(parent=parent, task_cogs_ceiling_micros=5)
        TaskService.kill_task(sub.id, reason=reasons.TASK_COGS_CEILING)
        sub.refresh_from_db()
        ctx = self._build(sub, dict(NO_VERDICTS, crossed_task_limit=True,
                                    task_not_active=True))
        by_scope = {c["stop_scope"]: c for c in ctx}
        self.assertEqual({c["limit"] for c in ctx}, {reasons.TASK_COGS_CEILING})
        self.assertFalse(by_scope["task"]["arrived_after"])
        self.assertTrue(by_scope["subtask"]["arrived_after"])
        self.assertEqual(by_scope["subtask"]["tripped_at"],
                         sub.completed_at.isoformat())


class CustomerContextTest(StopContextTestBase):
    def _open_episode(self, seq=3, line=reasons.HARD_FLOOR, state="stopped"):
        # A ledger row on one LINE (slice 6 §9): the family is the line's,
        # derived the way the ledger derives it.
        from apps.billing.gating.services.stop_signal_service import family_of_line
        return StopSignalState.objects.create(
            tenant=self.tenant, owner=self.customer,
            control_family=family_of_line(line), reason=line,
            state=state, episode_seq=seq, transitioned_at=self.now)

    def test_open_floor_episode_tags_the_lanes_stop(self):
        row = self._open_episode(seq=3)
        ctx = self._build(None, None)
        self.assertEqual(ctx, [{
            "limit": reasons.HARD_FLOOR, "stop_scope": "customer",
            "tripped_at": row.transitioned_at.isoformat(), "episode_seq": 3,
            "task_id": None, "subtask_id": None,
            "arrived_after": True,
        }])

    def test_tipping_event_when_this_debit_opened_the_episode(self):
        self._open_episode(seq=4)
        ctx = self._build(None, None, opened_episode_seq=4,
                          opened_line=reasons.HARD_FLOOR)
        self.assertFalse(ctx[0]["arrived_after"])

    def test_the_tipping_entry_is_matched_on_the_line_as_well_as_the_id(self):
        """Two lines number their episodes independently (#458), so the
        same id on both is the ordinary case, not a coincidence: only the
        line the debit opened is tipping, the other's entry is late."""
        self._open_episode(seq=2, line=reasons.HARD_FLOOR)
        self._open_episode(seq=2, line=reasons.CUSTOMER_SPEND_POOL)
        ctx = self._build(None, None, opened_episode_seq=2,
                          opened_line=reasons.CUSTOMER_SPEND_POOL)
        by_limit = {entry["limit"]: entry["arrived_after"] for entry in ctx}
        self.assertEqual(by_limit, {reasons.HARD_FLOOR: True,
                                    reasons.CUSTOMER_SPEND_POOL: False})

    def test_cleared_episode_tags_nothing(self):
        self._open_episode(state="cleared")
        self.assertIsNone(self._build(None, None))

    def test_soft_floor_state_never_tags(self):
        from apps.billing.gating.services.stop_signal_service import LINE_SOFT_FLOOR
        self._open_episode(line=LINE_SOFT_FLOOR)
        self.assertIsNone(self._build(None, None))

    def test_suspended_owner_without_episode_tags_suspended(self):
        self.customer.status = "suspended"
        self.customer.suspension_reason = "fraud"
        ctx = self._build(None, None)
        self.assertEqual(ctx, [{
            "limit": "suspended", "stop_scope": "customer",
            "tripped_at": None, "episode_seq": None,
            "task_id": None, "subtask_id": None,
            "arrived_after": True,
        }])

    def test_open_episode_wins_over_folded_suspension(self):
        # The suspension fold: a floor stop suspends the owner in the same
        # transition — ONE episode, one context, not two.
        self._open_episode()
        self.customer.status = "suspended"
        ctx = self._build(None, None)
        self.assertEqual(len(ctx), 1)
        self.assertEqual(ctx[0]["limit"], reasons.HARD_FLOOR)

    def test_enforcement_off_tags_no_customer_context(self):
        self.tenant.enforcement_mode = "off"
        self._open_episode()
        self.customer.status = "suspended"
        self.assertIsNone(self._build(None, None))

    def test_unit_and_customer_contexts_compose(self):
        self._open_episode(seq=7)
        task = self._task(task_cogs_ceiling_micros=10)
        ctx = self._build(task, dict(NO_VERDICTS, crossed_task_limit=True))
        by_limit = {c["limit"]: c for c in ctx}
        self.assertEqual(set(by_limit), {reasons.TASK_COGS_CEILING, reasons.HARD_FLOOR})
        # Customer-scope entries carry the event's unit attribution too.
        self.assertEqual(by_limit[reasons.HARD_FLOOR]["task_id"], str(task.id))
        self.assertEqual(by_limit[reasons.HARD_FLOOR]["episode_seq"], 7)

    def test_a_pool_episode_is_the_pools_stop(self):
        """The split (slice 6 §7, §9): an open episode on the pool's line
        names the pool's word — read off the ledger line, never forked off
        the owner's tenant billing mode (#458): the tenant here is still
        prepaid, and the tag says what the line says."""
        self._open_episode(seq=2, line=reasons.CUSTOMER_SPEND_POOL)
        ctx = self._build(None, None)
        self.assertEqual(ctx[0]["limit"], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(ctx[0]["stop_scope"], "customer")

    def test_an_owner_held_by_both_lines_is_tagged_once_per_line(self):
        """A customer stopped by its pool and by its floor at once holds two
        open episodes (slice 6 §9); a late event is tagged into each, under
        that line's own word and episode id — and the tipping entry is the
        one whose episode THIS event's debit opened, the other is late."""
        self._open_episode(seq=3, line=reasons.HARD_FLOOR)
        self._open_episode(seq=1, line=reasons.CUSTOMER_SPEND_POOL)
        ctx = self._build(None, None, opened_episode_seq=1,
                          opened_line=reasons.CUSTOMER_SPEND_POOL)
        by_limit = {entry["limit"]: entry for entry in ctx}
        self.assertEqual(set(by_limit),
                         {reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL})
        self.assertEqual(by_limit[reasons.HARD_FLOOR]["episode_seq"], 3)
        self.assertTrue(by_limit[reasons.HARD_FLOOR]["arrived_after"])
        self.assertEqual(by_limit[reasons.CUSTOMER_SPEND_POOL]["episode_seq"], 1)
        self.assertFalse(by_limit[reasons.CUSTOMER_SPEND_POOL]["arrived_after"])
