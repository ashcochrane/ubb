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
- Customer scope comes from the durable ledger (floor_stop family): open
  episode → the lane's customer-wide stop (the hard floor's word for a
  prepaid owner, the pool's for a postpaid one — `reasons.customer_stop_reason`)
  with the episode id; suspension without an open episode → ``suspended``.
  Soft-floor state NEVER marks (§F).
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
    def _open_episode(self, seq=3, family="floor_stop", state="stopped"):
        return StopSignalState.objects.create(
            tenant=self.tenant, owner=self.customer, family=family,
            state=state, episode_seq=seq, reason=reasons.HARD_FLOOR,
            transitioned_at=self.now)

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
        ctx = self._build(None, None, opened_episode_seq=4)
        self.assertFalse(ctx[0]["arrived_after"])

    def test_cleared_episode_tags_nothing(self):
        self._open_episode(state="cleared")
        self.assertIsNone(self._build(None, None))

    def test_soft_floor_state_never_tags(self):
        self._open_episode(family="soft_floor")
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

    def test_a_postpaid_owners_episode_is_the_pools_stop(self):
        """The split (slice 6 §7): the same open episode names the pool's
        word for a postpaid owner, the way the producers name it — by the
        owner's tenant billing mode, until the ledger carries its own line."""
        self.tenant.billing_mode = "postpaid"
        self.tenant.save(update_fields=["billing_mode"])
        self._open_episode(seq=2)
        ctx = self._build(None, None)
        self.assertEqual(ctx[0]["limit"], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(ctx[0]["stop_scope"], "customer")
