"""#41 acceptance pins — past-limit accounting.

Spec pins (docs/plans/2026-07-15-one-rule-enforcement-spec.md §L):
  Pin 2 (completes) — events on a killed task carry stop-context per the §H
           schema; the tipping event carries arrived_after=false. Single and
           batch parity — the two surviving recording surfaces (#192).
  Pin 9  — an episode is reconstructed end-to-end in ONE call: stop →
           itemized events → totals in both denominations → resume. The
           per-customer report that first answered it retired in #466; the
           successor read is Stops and breaches
           (`GET /api/v1/spend-controls/stops-and-breaches`), whose own
           module drives the reconstruction, and the two cases kept here are
           the ones that module does not: a tag written under an earlier
           spelling, and a bare suspension.
  Pin 10 — negative_since set on the ≥0 → <0 transition, cleared on
           recovery; the ops surface counts aged negatives.
  Plus: the past_limit / stop_scope / episode_seq filters compose on the
           event and analytics surfaces.
"""
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase

from apps.billing.gating.services.stop_signal_service import STATE_STOPPED
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at, what_it_bills)
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.events.models import OutboxEvent
from apps.platform.work.services import TaskService
from apps.platform.work import reasons
from apps.platform.work.services import STOP_CAUSE_KEY
from apps.platform.tenants.models import Tenant, TenantApiKey

FLOOR = 5_000_000       # hard floor: the stop line is -5M
SOFT = 2_000_000        # soft floor: the wind-down line is -2M

# The §H schema — the EXACT per-entry key set, pinned.
_CONTEXT_KEYS = {"limit", "stop_scope", "tripped_at", "episode_seq",
                 "task_id", "subtask_id", "arrived_after"}


class PastLimitPinTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="PastLimit", products=["metering", "billing"],
            billing_mode="prepaid", enforcement_mode="enforcing")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=20_000_000)
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=FLOOR,
            soft_min_balance_micros=SOFT)
        declares_a_caller_supplied_cost(self.tenant, DECLARED)
        a_rule_that_prices_what_it_measures(self.tenant)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _task(self, limit=10_000_000):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            task_cogs_ceiling_micros=limit,
            billing_owner_id=self.customer.id)

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
        resp = self.http_client.post(
            "/api/v1/metering/usage", data=json.dumps(data),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def _drain_durable(self):
        """Run the durable drawdown lane over every usage.recorded event —
        what the outbox dispatcher would do (mocked out at class level)."""
        for row in OutboxEvent.objects.filter(
                event_type="usage.recorded").order_by("created_at"):
            handle_usage_recorded_billing(str(row.id), row.payload)

    def _credit(self, amount):
        """Manual wallet credit through the real endpoint; on_commit hooks
        (the live-ledger resume fast lane) run via captureOnCommitCallbacks."""
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.http_client.post(
                "/api/v1/billing/credit", data=json.dumps({
                    "customer_id": self.customer.external_id,
                    "amount_micros": amount, "source": "test",
                    "reference": "r1", "idempotency_key": f"c-{uuid.uuid4()}",
                }), content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)

    def _report(self, query=""):
        resp = self.http_client.get(
            "/api/v1/spend-controls/stops-and-breaches"
            f"?customer_id={self.customer.id}{query}", **self._auth())
        self.assertEqual(resp.status_code, 200)
        return resp.json()


@patch("apps.platform.events.tasks.process_single_event")
class Pin2StopContextOnKilledTaskTest(PastLimitPinTestBase):
    def test_tipping_and_late_events_carry_schema_contexts(self, _mock):
        task = self._task(limit=10_000_000)
        # The kill executes on the recording transaction's on_commit (#112)
        # — it must land before the late event so that event arrives AFTER.
        with self.captureOnCommitCallbacks(execute=True):
            tip = self._record(task_id=str(task.id),
                               provider_cost_micros=11_000_000,
                               bills=1_000_000)
        late = self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                            bills=1_000_000)

        # The ack carries the itemized array; the stored row matches it.
        tip_ctx, late_ctx = tip["stop_context"], late["stop_context"]
        self.assertEqual(
            Posting.objects.get(id=tip["event_id"]).stop_context, tip_ctx)
        self.assertEqual(
            Posting.objects.get(id=late["event_id"]).stop_context, late_ctx)

        # §H schema: exact key set, closed vocabulary values.
        for ctx in (tip_ctx, late_ctx):
            self.assertEqual(len(ctx), 1)
            self.assertEqual(set(ctx[0]), _CONTEXT_KEYS)

        # The tipping event tripped the limit — arrived_after=false.
        self.assertEqual(tip_ctx[0]["limit"], reasons.TASK_COGS_CEILING)
        self.assertEqual(tip_ctx[0]["stop_scope"], "task")
        self.assertEqual(tip_ctx[0]["task_id"], str(task.id))
        self.assertIsNone(tip_ctx[0]["subtask_id"])
        self.assertIsNone(tip_ctx[0]["episode_seq"])
        self.assertFalse(tip_ctx[0]["arrived_after"])
        self.assertIsNotNone(tip_ctx[0]["tripped_at"])

        # The late event points back at the SAME episode: same limit,
        # arrived_after=true, tripped_at = the kill time.
        task.refresh_from_db()
        self.assertEqual(late_ctx[0]["limit"], reasons.TASK_COGS_CEILING)
        self.assertTrue(late_ctx[0]["arrived_after"])
        self.assertEqual(late_ctx[0]["tripped_at"],
                         task.completed_at.isoformat())

    def test_batch_items_carry_stop_context(self, _mock):
        task = self._task(limit=1_000_000)
        # Kill executes at commit (#112) — land it before the batch below.
        with self.captureOnCommitCallbacks(execute=True):
            self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                         bills=1_000_000)
        resp = self.http_client.post(
            "/api/v1/metering/usage/batch", data=json.dumps({"events": [{
                "customer_id": str(self.customer.id),
                "idempotency_key": "ib1",
                "task_id": str(task.id), "provider_cost_micros": 500_000,
                "event_type": DECLARED, "measurements": priced_at(500_000),
            }]}), content_type="application/json", **self._auth())
        item = resp.json()["results"][0]
        self.assertTrue(item["accepted"])
        self.assertEqual(item["stop_context"][0]["limit"], reasons.TASK_COGS_CEILING)
        self.assertTrue(item["stop_context"][0]["arrived_after"])

    def test_the_stored_row_carries_the_context_not_just_the_ack(self, _mock):
        """Preserves: the tipping event's §H context is written onto the
        durable row with the exact provider cost that tripped the limit —
        not merely returned on the ack.

        This pin used to prove it for the deferred lane, where the row was
        written by a later sweep and the ack could not have carried it. The
        surviving path writes the row and answers the ack in one act, so the
        assertion is now that the stored row still carries the full §H
        context — the half that outlives the response."""
        task = self._task(limit=10_000_000)
        resp = self._record(task_id=str(task.id),
                            provider_cost_micros=12_000_000,
                            bills=1_000_000)
        event = Posting.objects.get()
        self.assertEqual(event.provider_cost_micros, 12_000_000)
        self.assertEqual(event.stop_context[0]["limit"], reasons.TASK_COGS_CEILING)
        self.assertFalse(event.stop_context[0]["arrived_after"])
        self.assertEqual(set(event.stop_context[0]), _CONTEXT_KEYS)
        self.assertEqual(event.stop_context, resp["stop_context"])

    def test_replay_returns_the_original_context(self, _mock):
        task = self._task(limit=1_000_000)
        body = {"task_id": str(task.id), "provider_cost_micros": 2_000_000,
                "bills": 500_000,
                "idempotency_key": "replay-me"}
        first = self._record(**body)
        replay = self._record(**body)
        self.assertEqual(replay["event_id"], first["event_id"])
        self.assertEqual(replay["stop_context"], first["stop_context"])


@patch("apps.platform.events.tasks.process_single_event")
class Pin9StopsAndBreachesTest(PastLimitPinTestBase):
    """Pin 9 on its successor read (#466). The end-to-end reconstruction — a
    ceiling row explained by its unit and the events after the stop, a
    hard-floor row itemising its events, a soft-floor marker row, the window,
    the totals over exactly the rows shown — is driven in
    `test_spend_control_reports.py`. The two cases below are the ones that
    module does not drive, carried over from the retired report's pins."""

    def test_a_historical_customer_scope_tag_still_lands_in_itemization(
            self, _mock):
        """`stop_context` is immutable and written once (billing-surface-
        correctness, task 1 round 1), and it was NOT migrated when the stop
        vocabulary was (#457, slice 6 §8): rows tagged under an earlier
        spelling carry it forever. The bucketing keys on SCOPE and the
        episode's own id, never on an allow-list of current words, so such a
        row is itemized under its episode whatever spelling it carries."""
        from apps.billing.gating.models import StopSignalState
        from core.vocabulary import CONTROL_FAMILY_WALLET_POLICY

        # Trip a real floor crossing so a genuine episode exists on the
        # signal ledger (the episode ROW is sourced from there, not from any
        # event tag) — balance 20M, floor 5M: one event billing 26M crosses.
        self._record(provider_cost_micros=1_000_000, bills=26_000_000)
        state = StopSignalState.objects.get(owner=self.customer,
                                            reason=reasons.HARD_FLOOR)
        self.assertEqual(state.state, STATE_STOPPED)

        # A hand-crafted event carrying a RETIRED tag value at the SAME
        # episode — exactly what a pre-relabel write left behind, immutably.
        legacy = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="legacy-1",
            provider_cost_micros=1_000_000, billed_cost_micros=4_000_000,
            stop_context=[{
                "limit": "a_spelling_no_constant_carries", "stop_scope": "customer",
                "tripped_at": state.transitioned_at.isoformat(),
                "episode_seq": state.episode_seq,
                "task_id": None, "subtask_id": None, "arrived_after": True,
            }])

        report = self._report()
        floor_rows = [r for r in report["rows"]
                      if r["control_family"] == CONTROL_FAMILY_WALLET_POLICY
                      and not r["soft_floor"]]
        self.assertEqual(len(floor_rows), 1)
        event_ids = {e["event_id"] for e in floor_rows[0]["itemised"]["events"]}
        self.assertIn(str(legacy.id), event_ids)
        totals = {t["control_family"]: t for t in report["totals"]}
        self.assertGreaterEqual(
            totals[CONTROL_FAMILY_WALLET_POLICY]["billed_cost_micros"], 4_000_000)

    def test_suspended_tag_stays_excluded_from_itemization(self, _mock):
        """`suspended` is a taggable customer-scope value but never an
        episode — a bare suspension has nothing to itemize. It must stay
        excluded now that the filter is a deny-list, not an allow-list."""
        suspended_event = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="susp-1",
            provider_cost_micros=1_000_000, billed_cost_micros=1_000_000,
            stop_context=[{
                "limit": reasons.SUSPENDED, "stop_scope": "customer",
                "tripped_at": None, "episode_seq": None,
                "task_id": None, "subtask_id": None, "arrived_after": True,
            }])

        report = self._report()
        self.assertEqual(report["rows"], [])
        self.assertEqual(report["totals"], [])
        all_event_ids = {
            e["event_id"] for row in report["rows"]
            for e in row["itemised"]["events"]}
        self.assertNotIn(str(suspended_event.id), all_event_ids)


@patch("apps.platform.events.tasks.process_single_event")
class Pin10NegativeSinceTest(PastLimitPinTestBase):
    def _balance(self):
        resp = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def _negative_stats(self):
        """The aged-negatives counters, read straight off billing's
        `queries.py` contract.

        These used to be read through GET /metering/ops/ingest-health, which
        composed them onto the ingest pipeline's health surface. That route
        was deleted with the pipeline it watched; the counters were never the
        pipeline's, so the guarantee below outlives it and is asserted
        against the read contract itself — the same way test_patrol_pins.py
        already asserts get_patrol_stats.
        """
        from apps.billing.queries import get_negative_balance_stats
        return get_negative_balance_stats(tenant_id=self.tenant.id)

    def test_negative_since_set_on_crossing_cleared_on_recovery(self, _mock):
        self.assertIsNone(self._balance()["negative_since"])

        # ≥0 → <0 through the real drawdown lane.
        self._record(provider_cost_micros=1_000_000, bills=21_000_000)
        self._drain_durable()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, -1_000_000)
        self.assertIsNotNone(self.wallet.negative_since)
        stamped = self.wallet.negative_since
        body = self._balance()
        self.assertEqual(body["negative_since"], stamped.isoformat())

        # A further negative move PRESERVES the original transition time.
        self._record(provider_cost_micros=1_000_000, bills=2_000_000)
        self._drain_durable()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.negative_since, stamped)

        # A wallet below zero is counted as an aged negative.
        stats = self._negative_stats()
        self.assertEqual(stats["negative_balance_count"], 1)
        self.assertGreaterEqual(stats["oldest_negative_age_seconds"], 0.0)

        # Recovery clears it — nothing else happens (no reminder events, no
        # auto-close; the event catalog carries no such types to emit).
        self._credit(30_000_000)
        self.wallet.refresh_from_db()
        self.assertIsNone(self.wallet.negative_since)
        self.assertIsNone(self._balance()["negative_since"])
        self.assertEqual(self._negative_stats()["negative_balance_count"], 0)


@patch("apps.platform.events.tasks.process_single_event")
class PastLimitQueryFiltersTest(PastLimitPinTestBase):
    def _seed(self):
        # One untagged event, one task-scope tagged event, two customer-scope
        # tagged events (the crossing + one after).
        self._record(provider_cost_micros=1_000_000, bills=1_000_000)
        task = self._task(limit=1_000_000)
        self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                     bills=1_000_000)
        self._record(provider_cost_micros=1_000_000, bills=25_000_000)
        self._record(provider_cost_micros=1_000_000, bills=1_000_000)

    def _usage(self, query=""):
        resp = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage{query}",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        return resp.json()["data"]

    def test_event_filters_compose(self, _mock):
        self._seed()
        self.assertEqual(len(self._usage()), 4)
        past = self._usage("?past_limit=true")
        self.assertEqual(len(past), 3)
        self.assertTrue(all(e["stop_context"] for e in past))
        self.assertEqual(len(self._usage("?past_limit=false")), 1)
        task_scoped = self._usage("?stop_scope=task")
        self.assertEqual(len(task_scoped), 1)
        self.assertEqual(task_scoped[0]["stop_context"][0]["limit"], reasons.TASK_COGS_CEILING)
        episode = self._usage("?episode_seq=1")
        self.assertEqual(len(episode), 2)
        self.assertEqual(len(self._usage("?episode_seq=99")), 0)

    def test_analytics_filters_compose(self, _mock):
        """The #41 filters on the surface that reports totals.

        They asked the usage report until #501 collapsed it; the one economic
        query takes the same three and composes them with every grouping, which
        is the property this case is about rather than the route it was written
        against. The measures are named because that query refuses a request
        that names none.
        """
        self._seed()
        resp = self.http_client.get(
            "/api/v1/metering/analytics/economics",
            {"measures": ["recorded_events", "customer_revenue"],
             "past_limit": "true", "stop_scope": "customer"},
            **self._auth())
        self.assertEqual(resp.status_code, 200, resp.content)
        measures = {entry["measure"]: entry
                    for entry in resp.json()["rows"][0]["measures"]}
        self.assertEqual(measures["recorded_events"]["event_count"], 2)
        self.assertEqual(measures["customer_revenue"]["amount_micros"],
                         26_000_000)
