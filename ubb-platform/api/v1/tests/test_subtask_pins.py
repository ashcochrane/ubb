"""Subtasks — the #38 acceptance pins (spec §L, subtask legs).

Pin 1 (subtask leg)  — the tipping event on a subtask limit lands and bills,
                       and the ceiling bites on the one recording path — at
                       record time, with nothing deferred to a later sweep
                       (#192).
Pin 13               — subtask killed ALONE (parent keeps running and
                       counting); rollup into the parent's provider total;
                       parent trip kills the parent and cascades to active
                       subtasks.
Pin 14 (subtask leg) — only the provider total races a subtask limit; both
                       totals on the record and the response.
Start-gate           — refusals parent_task_not_active /
                       subtask_depth_exceeded; subtask default limit +
                       coverage gate; closing a parent auto-completes its
                       active subtasks.
"""
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, Client

from apps.billing.gating.models import RiskConfig
from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at, what_it_bills)
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.events.models import OutboxEvent
from apps.platform.work.models import Task
from apps.platform.work.services import (
    PARENT_NOT_ACTIVE, SUBTASK_DEPTH_EXCEEDED, CloseDeclaration, TaskService)
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    TASK_OUTCOME_DELIVERED,
    TASK_STATUS_ACTIVE, TASK_STATUS_CANCELLED, TASK_STATUS_COMPLETED,
    TASK_STATUS_KILLED)


class SubtaskPinMixin:
    """Fixture + helpers, TestCase-agnostic: the batch-parity pin needs a
    TransactionTestCase (real commits — #112 kills execute on_commit), the
    rest stay on the fast wrapped-transaction TestCase."""

    def setUp(self):
        cache.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Subtasks", products=["metering", "billing"],
            billing_mode="prepaid",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=100_000_000)
        declares_a_caller_supplied_cost(self.tenant, DECLARED)
        a_rule_that_prices_what_it_measures(self.tenant)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _task(self, limit=None, parent=None, balance=100_000_000):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit,
            billing_owner_id=self.customer.id, parent=parent)

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "idempotency_key": f"idem-{uuid.uuid4()}",
            # Every body here states the supplier's own cost, admissible only
            # against an Event Type that declares it arrives on the call
            # (#324). `extra` still wins, so a test may name another key.
            "event_type": DECLARED,
        }
        # ⚠ WHAT AN EVENT BILLS IS CONFIGURED, NOT SENT (#365). Callers say
        # `bills=N` exactly as they used to say the deleted request field; the
        # shared door turns it into the quantities this tenant's own rule
        # charges N for, so one number goes in and no caller here learns which
        # key it lands under.
        data.update(what_it_bills(extra))
        data.update(extra)
        return self.http_client.post(
            "/api/v1/metering/usage", data=json.dumps(data),
            content_type="application/json", **self._auth())

    def _start(self, **extra):
        """Register a unit of work through the one route that registers one.

        ⚠ THIS USED TO BE THE AFFORDABILITY CALL WITH A FLAG ON IT (#410).
        Registering work is `POST /api/v1/tasks` now — at the root, ungated,
        and with the caller's key required — so a refusal is an HTTP refusal
        rather than a verdict riding inside a 200.
        """
        data = {"customer_id": str(self.customer.id),
                "idempotency_key": f"attempt-{uuid.uuid4()}"}
        data.update(extra)
        return self.http_client.post(
            "/api/v1/tasks", data=json.dumps(data),
            content_type="application/json", **self._auth())

    def _started(self, **extra):
        """...and the body of a start that was admitted."""
        response = self._start(**extra)
        assert response.status_code == 200, response.json()
        return response.json()

    def _events(self, event_type):
        return OutboxEvent.objects.filter(event_type=event_type)


class SubtaskPinTestBase(SubtaskPinMixin, TestCase):
    pass


@patch("apps.platform.events.tasks.process_single_event")
class Pin1SubtaskTippingEventTest(SubtaskPinTestBase):
    def test_subtask_tipping_event_lands_bills_and_kills_alone(self, _mock):
        parent = self._task(limit=100_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        # The kill executes on the recording transaction's on_commit (#112).
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(sub.id),
                                provider_cost_micros=6_000_000,
                                bills=9_000_000)

        # The tipping event answers 200 and is durably recorded + billed.
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        event = Posting.objects.get(id=body["event_id"])
        self.assertEqual(event.billed_cost_micros, 9_000_000)
        self.assertEqual(event.task_id, sub.id)

        # The subtask is killed ALONE; the response says so, scoped to it.
        sub.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(sub.status, TASK_STATUS_KILLED)
        self.assertEqual(sub.metadata["kill_reason"], "subtask_limit")
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "subtask_limit")
        self.assertEqual(body["stop_scope"], "subtask")
        self.assertEqual(body["task_id"], str(sub.id))
        self.assertEqual(body["parent_task_id"], str(parent.id))

        # Exactly one subtask.limit_exceeded, ids explicit; no task-scoped one.
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 1)
        self.assertEqual(self._events("task.limit_exceeded").count(), 0)
        payload = self._events("subtask.limit_exceeded").get().payload
        self.assertEqual(payload["subtask_id"], str(sub.id))
        self.assertEqual(payload["parent_task_id"], str(parent.id))
        self.assertEqual(payload["reason"], "subtask_limit")
        self.assertEqual(payload["total_provider_cost_micros"], 6_000_000)
        self.assertEqual(payload["provider_cost_limit_micros"], 5_000_000)

    def test_subtask_limit_bites_at_record_time_with_nothing_deferred(self, _mock):
        """Preserves: the Subtask COGS ceiling kills the subtask alone, and
        the tipping event's provider cost rolls up into the parent's total.

        This pin used to prove that on the deferred lane, where both the kill
        and the rollup waited for a later sweep. The surviving path does both
        inline, so the same guarantee now holds with nothing deferred."""
        parent = self._task()
        sub = self._task(limit=5_000_000, parent=parent)
        # The kill executes on the recording transaction's on_commit (#112).
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(sub.id),
                                provider_cost_micros=6_000_000,
                                bills=6_000_000)
        self.assertEqual(resp.status_code, 200)

        # Containment and rollup are both already true on this response.
        sub.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(sub.status, TASK_STATUS_KILLED)
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        self.assertEqual(parent.total_provider_cost_micros, 6_000_000)
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 1)


@patch("apps.platform.events.tasks.process_single_event")
class Pin13ContainmentTest(SubtaskPinTestBase):
    def test_subtask_killed_alone_parent_keeps_running_and_counting(self, _mock):
        parent = self._task(limit=100_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        # Trip the subtask's own limit (kill executes at commit — #112).
        with self.captureOnCommitCallbacks(execute=True):
            self._record(task_id=str(sub.id), provider_cost_micros=6_000_000,
                         bills=6_000_000)
        sub.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(sub.status, TASK_STATUS_KILLED)
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        # Rollup: the parent's provider total carries the subtask's spend.
        self.assertEqual(parent.total_provider_cost_micros, 6_000_000)

        # The parent keeps running AND counting: direct parent events land,
        # and late events on the killed subtask still roll up.
        self._record(task_id=str(parent.id), provider_cost_micros=1_000_000,
                     bills=1_000_000)
        resp = self._record(task_id=str(sub.id), provider_cost_micros=2_000_000,
                            bills=2_000_000)
        body = resp.json()
        self.assertEqual(body["stop_reason"], "task_not_active")
        self.assertEqual(body["stop_scope"], "subtask")
        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        self.assertEqual(parent.total_provider_cost_micros, 9_000_000)
        self.assertEqual(parent.event_count, 3)

    def test_parent_trip_kills_parent_and_cascades_to_active_subtasks(self, _mock):
        parent = self._task(limit=10_000_000)
        tripping_sub = self._task(parent=parent)
        sibling_sub = self._task(parent=parent)

        # A subtask event pushes the ROLLED-UP provider total past the
        # parent's limit: the parent's cap covers everything underneath it.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(tripping_sub.id),
                                provider_cost_micros=11_000_000,
                                bills=11_000_000)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_limit")
        self.assertEqual(body["stop_scope"], "task")
        self.assertEqual(body["parent_task_id"], str(parent.id))

        parent.refresh_from_db()
        tripping_sub.refresh_from_db()
        sibling_sub.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_KILLED)
        self.assertEqual(parent.metadata["kill_reason"], "task_limit")
        # Containment cuts downward: BOTH subtasks are cascade-killed ...
        self.assertEqual(tripping_sub.status, TASK_STATUS_KILLED)
        self.assertEqual(sibling_sub.status, TASK_STATUS_KILLED)
        self.assertEqual(sibling_sub.metadata["kill_reason"], "parent_killed")
        # ... but only the parent announces (the subtasks crossed nothing).
        self.assertEqual(self._events("task.limit_exceeded").count(), 1)
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 0)
        payload = self._events("task.limit_exceeded").get().payload
        self.assertEqual(payload["task_id"], str(parent.id))
        self.assertEqual(payload["total_provider_cost_micros"], 11_000_000)

    def test_both_limits_tripping_on_one_event_announce_both(self, _mock):
        parent = self._task(limit=10_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(sub.id),
                                provider_cost_micros=12_000_000,
                                bills=12_000_000)
        body = resp.json()
        # The WIDEST tripped scope wins the scalar slot: stop the whole tree.
        self.assertEqual(body["stop_reason"], "task_limit")
        self.assertEqual(body["stop_scope"], "task")
        # Both kills happened; both announcements fired — the subtask's own
        # crossing is not swallowed by the parent's cascade.
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 1)
        self.assertEqual(self._events("task.limit_exceeded").count(), 1)
        sub.refresh_from_db()
        self.assertEqual(sub.metadata["kill_reason"], "subtask_limit")


@patch("apps.platform.events.tasks.process_single_event")
class Pin13BatchParityTest(SubtaskPinMixin, TransactionTestCase):
    """TransactionTestCase (#112): the mid-batch semantics under test — the
    tipping item's kill LANDS before the next item runs, so that item gets
    task_not_active — exist only when each item's transaction really commits
    (kill execution rides the recording transaction's on_commit)."""

    def test_batch_parity_subtask_verdicts(self, _mock):
        parent = self._task(limit=100_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        events = [{
            "customer_id": str(self.customer.id),
            "idempotency_key": f"ib{i}",
            "task_id": str(sub.id), "provider_cost_micros": 6_000_000,
            "event_type": DECLARED,
        } for i in range(2)]
        resp = self.http_client.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": events}),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 2)
        # Item 1 trips the subtask limit; item 2 lands on the killed subtask
        # — identical to firing the same items as sequential singles.
        self.assertEqual(body["results"][0]["stop_reason"], "subtask_limit")
        self.assertEqual(body["results"][0]["stop_scope"], "subtask")
        self.assertEqual(body["results"][1]["stop_reason"], "task_not_active")
        self.assertEqual(body["results"][1]["stop_scope"], "subtask")
        for item in body["results"]:
            self.assertEqual(item["parent_task_id"], str(parent.id))
        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        self.assertEqual(parent.total_provider_cost_micros, 12_000_000)


@patch("apps.platform.events.tasks.process_single_event")
class Pin14SubtaskDenominationTest(SubtaskPinTestBase):
    def test_only_the_provider_total_races_a_subtask_limit(self, _mock):
        parent = self._task()
        sub = self._task(limit=5_000_000, parent=parent)
        # Billed way past the limit, provider under it -> nothing fires.
        resp = self._record(task_id=str(sub.id), provider_cost_micros=1_000_000,
                            bills=50_000_000)
        body = resp.json()
        self.assertFalse(body["stop"])
        sub.refresh_from_db()
        self.assertEqual(sub.status, TASK_STATUS_ACTIVE)
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 0)

        # Both totals on the record and the response, denominationally explicit.
        self.assertEqual(sub.total_billed_cost_micros, 50_000_000)
        self.assertEqual(sub.total_provider_cost_micros, 1_000_000)
        self.assertEqual(body["task_total_billed_cost_micros"], 50_000_000)
        self.assertEqual(body["task_total_provider_cost_micros"], 1_000_000)

        # The provider total crossing is what kills.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(sub.id),
                                provider_cost_micros=4_500_000,
                                # The least this tenant's rule can charge; the
                                # figure is asserted nowhere and the number
                                # beside it is what races the limit.
                                bills=1_000)
        self.assertEqual(resp.json()["stop_reason"], "subtask_limit")
        sub.refresh_from_db()
        self.assertEqual(sub.status, TASK_STATUS_KILLED)


class StartGateSubtaskTest(SubtaskPinTestBase):
    def test_register_subtask_under_active_parent(self):
        parent = self._task()
        body = self._started(parent_task_id=str(parent.id))
        self.assertEqual(body["parent_task_id"], str(parent.id))
        sub = Task.objects.get(id=body["task_id"])
        self.assertEqual(sub.parent_id, parent.id)

    def test_top_level_start_has_null_parent(self):
        body = self._started()
        self.assertIsNone(body["parent_task_id"])

    def test_nonexistent_parent_refused_parent_task_not_active(self):
        refused = self._start(parent_task_id=str(uuid.uuid4()))
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["reason"], PARENT_NOT_ACTIVE)
        self.assertEqual(Task.objects.count(), 0)

    def test_terminal_parent_refused_parent_task_not_active(self):
        parent = self._task()
        TaskService.close_task(parent.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        refused = self._start(parent_task_id=str(parent.id))
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["reason"], PARENT_NOT_ACTIVE)

    def test_foreign_customers_parent_refused(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        foreign_parent = TaskService.create_task(
            self.tenant, other, balance_snapshot_micros=0,
            billing_owner_id=other.id)
        refused = self._start(parent_task_id=str(foreign_parent.id))
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["reason"], PARENT_NOT_ACTIVE)

    def test_subtask_parent_refused_subtask_depth_exceeded(self):
        parent = self._task()
        sub = self._task(parent=parent)
        refused = self._start(parent_task_id=str(sub.id))
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["reason"], SUBTASK_DEPTH_EXCEEDED)

    def test_subtask_default_limit_applies_with_no_cost_rates_declared(self):
        # The SUBTASK default (not the task default) is the fallback for a
        # subtask start, and it resolves on a tenant that has declared no cost
        # rates: #321 deleted the coverage gate that refused a limited start
        # here, subtask and task alike, with nothing in its place.
        RiskConfig.objects.create(
            tenant=self.tenant,
            default_subtask_provider_cost_limit_micros=3_000_000)
        parent = self._task()
        body = self._started(parent_task_id=str(parent.id))
        self.assertEqual(body["provider_cost_limit_micros"], 3_000_000)

        # A top-level start ignores the subtask default (no task default set
        # -> uncapped).
        body = self._started()
        self.assertIsNone(body["provider_cost_limit_micros"])

    def test_explicit_subtask_limit_wins_over_default(self):
        RiskConfig.objects.create(
            tenant=self.tenant,
            default_subtask_provider_cost_limit_micros=3_000_000)
        parent = self._task()
        body = self._started(parent_task_id=str(parent.id),
                             provider_cost_limit_micros=7_000_000)
        sub = Task.objects.get(id=body["task_id"])
        self.assertEqual(sub.provider_cost_limit_micros, 7_000_000)


class CloseCascadeTest(SubtaskPinTestBase):
    def test_closing_a_parent_withdraws_active_subtasks(self):
        # One call still cleans the tree up; what changed is what the tree
        # then SAYS (#408). The close declared the delivery of the parent, so
        # only the parent may read `completed` — each contained piece was
        # withdrawn, which is what `cancelled` means.
        parent = self._task()
        sub_active = self._task(parent=parent)
        sub_killed = self._task(parent=parent)
        TaskService.kill_task(sub_killed.id)

        resp = self.http_client.post(
            f"/api/v1/tasks/{parent.id}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], TASK_STATUS_COMPLETED)
        self.assertIsNone(body["parent_task_id"])
        sub_active.refresh_from_db()
        sub_killed.refresh_from_db()
        self.assertEqual(sub_active.status, TASK_STATUS_CANCELLED)
        # A killed subtask keeps its state — cleanup never rewrites history.
        self.assertEqual(sub_killed.status, TASK_STATUS_KILLED)

    def test_closing_a_subtask_closes_it_alone(self):
        parent = self._task()
        sub = self._task(parent=parent)
        resp = self.http_client.post(
            f"/api/v1/tasks/{sub.id}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
            content_type="application/json", **self._auth())
        body = resp.json()
        self.assertEqual(body["status"], TASK_STATUS_COMPLETED)
        self.assertEqual(body["parent_task_id"], str(parent.id))
        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
