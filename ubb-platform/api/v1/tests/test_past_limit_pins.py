"""#41 acceptance pins — past-limit accounting.

Spec pins (docs/plans/2026-07-15-one-rule-enforcement-spec.md §L):
  Pin 2 (completes) — events on a killed task carry stop-context per the §H
           schema; the tipping event carries arrived_after=false. Sync,
           batch, and async-settle parity.
  Pin 9  — the past-limit report reconstructs an episode end-to-end in ONE
           call: stop → itemized events → totals in both denominations →
           resume. Soft-floor episodes appear as marker rows with no
           itemized events.
  Pin 10 — negative_since set on the ≥0 → <0 transition, cleared on
           recovery; the ops surface counts aged negatives.
  Plus: the past_limit / stop_scope / episode_seq filters compose on the
           event and analytics surfaces.
"""
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.services import TaskService
from apps.platform.tenants.models import Tenant, TenantApiKey

FLOOR = 5_000_000       # hard floor: the stop line is -5M
SOFT = 2_000_000        # soft floor: the wind-down line is -2M

# The §H schema — the EXACT per-entry key set, pinned.
_CONTEXT_KEYS = {"limit", "stop_scope", "tripped_at", "episode_seq",
                 "task_id", "subtask_id", "arrived_after"}


class PastLimitPinTestBase(TestCase):
    def setUp(self):
        cache.clear()
        from api.v1 import metering_endpoints
        metering_endpoints._TASK_META_CACHE.clear()
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

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _task(self, limit=10_000_000):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            provider_cost_limit_micros=limit,
            billing_owner_id=self.customer.id)

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "request_id": f"req-{uuid.uuid4()}",
            "idempotency_key": f"idem-{uuid.uuid4()}",
        }
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
            f"/api/v1/customers/{self.customer.id}/past-limit-report{query}",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        return resp.json()


@patch("apps.platform.events.tasks.process_single_event")
class Pin2StopContextOnKilledTaskTest(PastLimitPinTestBase):
    def test_tipping_and_late_events_carry_schema_contexts(self, _mock):
        task = self._task(limit=10_000_000)
        tip = self._record(task_id=str(task.id), provider_cost_micros=11_000_000,
                           billed_cost_micros=1_000_000)
        late = self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                            billed_cost_micros=1_000_000)

        # The ack carries the itemized array; the stored row matches it.
        tip_ctx, late_ctx = tip["stop_context"], late["stop_context"]
        self.assertEqual(
            UsageEvent.objects.get(id=tip["event_id"]).stop_context, tip_ctx)
        self.assertEqual(
            UsageEvent.objects.get(id=late["event_id"]).stop_context, late_ctx)

        # §H schema: exact key set, closed vocabulary values.
        for ctx in (tip_ctx, late_ctx):
            self.assertEqual(len(ctx), 1)
            self.assertEqual(set(ctx[0]), _CONTEXT_KEYS)

        # The tipping event tripped the limit — arrived_after=false.
        self.assertEqual(tip_ctx[0]["limit"], "task_limit")
        self.assertEqual(tip_ctx[0]["stop_scope"], "task")
        self.assertEqual(tip_ctx[0]["task_id"], str(task.id))
        self.assertIsNone(tip_ctx[0]["subtask_id"])
        self.assertIsNone(tip_ctx[0]["episode_seq"])
        self.assertFalse(tip_ctx[0]["arrived_after"])
        self.assertIsNotNone(tip_ctx[0]["tripped_at"])

        # The late event points back at the SAME episode: same limit,
        # arrived_after=true, tripped_at = the kill time.
        task.refresh_from_db()
        self.assertEqual(late_ctx[0]["limit"], "task_limit")
        self.assertTrue(late_ctx[0]["arrived_after"])
        self.assertEqual(late_ctx[0]["tripped_at"],
                         task.completed_at.isoformat())

    def test_batch_items_carry_stop_context(self, _mock):
        task = self._task(limit=1_000_000)
        self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                     billed_cost_micros=1_000_000)
        resp = self.http_client.post(
            "/api/v1/metering/usage/batch", data=json.dumps({"events": [{
                "customer_id": str(self.customer.id),
                "request_id": "rb1", "idempotency_key": "ib1",
                "task_id": str(task.id), "provider_cost_micros": 500_000,
                "billed_cost_micros": 500_000,
            }]}), content_type="application/json", **self._auth())
        item = resp.json()["results"][0]
        self.assertTrue(item["ok"])
        self.assertEqual(item["stop_context"][0]["limit"], "task_limit")
        self.assertTrue(item["stop_context"][0]["arrived_after"])

    def test_async_settle_tags_the_event(self, _mock):
        from apps.metering.usage.tasks import settle_raw_events
        tenant = self.tenant
        tenant.products = tenant.products + ["metering_async"]
        tenant.save(update_fields=["products"])
        task = self._task(limit=10_000_000)
        resp = self.http_client.post(
            "/api/v1/metering/usage/ingest", data=json.dumps({"events": [{
                "customer_id": str(self.customer.id),
                "request_id": "ra1", "idempotency_key": "ia1",
                "task_id": str(task.id),
                "provider_cost_micros": 12_000_000,
                "billed_cost_micros": 1_000_000,
            }]}), content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)
        settle_raw_events()
        event = UsageEvent.objects.get()
        # Settle-time detection: the async tipping event carries the same
        # §H context as the sync path's.
        self.assertEqual(event.stop_context[0]["limit"], "task_limit")
        self.assertFalse(event.stop_context[0]["arrived_after"])
        self.assertEqual(set(event.stop_context[0]), _CONTEXT_KEYS)

    def test_replay_returns_the_original_context(self, _mock):
        task = self._task(limit=1_000_000)
        body = {"task_id": str(task.id), "provider_cost_micros": 2_000_000,
                "billed_cost_micros": 500_000,
                "idempotency_key": "replay-me"}
        first = self._record(**body)
        replay = self._record(**body)
        self.assertEqual(replay["event_id"], first["event_id"])
        self.assertEqual(replay["stop_context"], first["stop_context"])


@patch("apps.platform.events.tasks.process_single_event")
class Pin9PastLimitReportTest(PastLimitPinTestBase):
    def test_report_reconstructs_episodes_end_to_end(self, _mock):
        # -- the task-limit episode: tipping event + one late event.
        task = self._task(limit=10_000_000)
        self._record(task_id=str(task.id), provider_cost_micros=11_000_000,
                     billed_cost_micros=6_000_000)
        self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                     billed_cost_micros=3_000_000)

        # -- the customer-floor episode: the fast lane opens it on the
        #    crossing event (balance 20M - 9M - 17M = -6M < -5M), one more
        #    event lands during the episode.
        self._record(provider_cost_micros=1_000_000, billed_cost_micros=17_000_000)
        self._record(provider_cost_micros=1_000_000, billed_cost_micros=1_000_000)

        # -- the durable lane sees the same drawdowns (soft floor's ONLY
        #    detector; the hard-floor crossing loses the dedup to the fast
        #    lane), then the balance recovers through the credit endpoint.
        self._drain_durable()
        self._credit(30_000_000)

        report = self._report()
        self.assertEqual(report["customer_id"], str(self.customer.id))
        by_family = {}
        for ep in report["episodes"]:
            by_family.setdefault(ep["family"], []).append(ep)
        self.assertEqual(
            {f: len(v) for f, v in by_family.items()},
            {"task": 1, "floor_stop": 1, "soft_floor": 1})

        # Task episode: the tripping limit, tripped-at, itemized events,
        # totals in BOTH denominations; a kill never "resumes".
        ep = by_family["task"][0]
        task.refresh_from_db()
        self.assertEqual(ep["limit"], "task_limit")
        self.assertEqual(ep["stop_scope"], "task")
        self.assertEqual(ep["task_id"], str(task.id))
        self.assertIsNone(ep["subtask_id"])
        self.assertEqual(ep["provider_cost_limit_micros"], 10_000_000)
        self.assertEqual(ep["tripped_at"], task.completed_at.isoformat())
        self.assertIsNone(ep["resumed_at"])
        self.assertEqual([e["arrived_after"] for e in ep["events"]],
                         [False, True])
        self.assertEqual(ep["event_count"], 2)
        self.assertEqual(ep["total_provider_cost_micros"], 13_000_000)
        self.assertEqual(ep["total_billed_cost_micros"], 9_000_000)

        # Customer-floor episode: stop → itemized events → resume, keyed on
        # the signal ledger's episode id.
        ep = by_family["floor_stop"][0]
        self.assertEqual(ep["limit"], "customer_floor")
        self.assertEqual(ep["stop_scope"], "customer")
        self.assertEqual(ep["episode_seq"], 1)
        self.assertIsNotNone(ep["tripped_at"])
        self.assertIsNotNone(ep["resumed_at"])
        self.assertEqual([e["arrived_after"] for e in ep["events"]],
                         [False, True])
        self.assertEqual(ep["total_billed_cost_micros"], 18_000_000)
        self.assertEqual(ep["total_provider_cost_micros"], 2_000_000)

        # Soft-floor episode: a crossed/cleared MARKER row — no itemized
        # events, nothing is "past limit" under a soft floor.
        ep = by_family["soft_floor"][0]
        self.assertEqual(ep["events"], [])
        self.assertEqual(ep["event_count"], 0)
        self.assertIsNone(ep["limit"])
        self.assertEqual(ep["episode_seq"], 1)
        self.assertIsNotNone(ep["tripped_at"])
        self.assertIsNotNone(ep["resumed_at"])

        # Totals per limit, both denominations — "exactly what was spent
        # past the limit and why", one call.
        self.assertEqual(report["totals_per_limit"], {
            "task_limit": {"billed_cost_micros": 9_000_000,
                           "provider_cost_micros": 13_000_000,
                           "event_count": 2},
            "customer_floor": {"billed_cost_micros": 18_000_000,
                               "provider_cost_micros": 2_000_000,
                               "event_count": 2},
        })

    def test_window_filters_episodes(self, _mock):
        task = self._task(limit=1_000_000)
        self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                     billed_cost_micros=1_000_000)
        report = self._report("?since=2099-01-01T00:00:00Z")
        self.assertEqual(report["episodes"], [])
        report = self._report("?until=2000-01-01T00:00:00Z")
        self.assertEqual(report["episodes"], [])

    def test_unknown_customer_404s(self, _mock):
        resp = self.http_client.get(
            f"/api/v1/customers/{uuid.uuid4()}/past-limit-report",
            **self._auth())
        self.assertEqual(resp.status_code, 404)


@patch("apps.platform.events.tasks.process_single_event")
class Pin10NegativeSinceTest(PastLimitPinTestBase):
    OPS = {"HTTP_X_OPS_TOKEN": "s3cret"}

    def _balance(self):
        resp = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_negative_since_set_on_crossing_cleared_on_recovery(self, _mock):
        self.assertIsNone(self._balance()["negative_since"])

        # ≥0 → <0 through the real drawdown lane.
        self._record(provider_cost_micros=1_000_000, billed_cost_micros=21_000_000)
        self._drain_durable()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, -1_000_000)
        self.assertIsNotNone(self.wallet.negative_since)
        stamped = self.wallet.negative_since
        body = self._balance()
        self.assertEqual(body["negative_since"], stamped.isoformat())

        # A further negative move PRESERVES the original transition time.
        self._record(provider_cost_micros=1_000_000, billed_cost_micros=2_000_000)
        self._drain_durable()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.negative_since, stamped)

        # The ops surface counts aged negatives.
        resp = self.http_client.get("/api/v1/metering/ops/ingest-health", **self.OPS)
        self.assertEqual(resp.status_code, 200)
        ops = resp.json()
        self.assertEqual(ops["negative_balance_count"], 1)
        self.assertGreaterEqual(ops["oldest_negative_age_seconds"], 0.0)

        # Recovery clears it — nothing else happens (no reminder events, no
        # auto-close; the event catalog carries no such types to emit).
        self._credit(30_000_000)
        self.wallet.refresh_from_db()
        self.assertIsNone(self.wallet.negative_since)
        self.assertIsNone(self._balance()["negative_since"])
        resp = self.http_client.get("/api/v1/metering/ops/ingest-health", **self.OPS)
        self.assertEqual(resp.json()["negative_balance_count"], 0)


@patch("apps.platform.events.tasks.process_single_event")
class PastLimitQueryFiltersTest(PastLimitPinTestBase):
    def _seed(self):
        # One untagged event, one task-scope tagged event, two customer-scope
        # tagged events (the crossing + one after).
        self._record(provider_cost_micros=1_000_000, billed_cost_micros=1_000_000)
        task = self._task(limit=1_000_000)
        self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                     billed_cost_micros=1_000_000)
        self._record(provider_cost_micros=1_000_000, billed_cost_micros=25_000_000)
        self._record(provider_cost_micros=1_000_000, billed_cost_micros=1_000_000)

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
        self.assertEqual(task_scoped[0]["stop_context"][0]["limit"], "task_limit")
        episode = self._usage("?episode_seq=1")
        self.assertEqual(len(episode), 2)
        self.assertEqual(len(self._usage("?episode_seq=99")), 0)

    def test_analytics_filters_compose(self, _mock):
        self._seed()
        resp = self.http_client.get(
            "/api/v1/metering/analytics/usage?past_limit=true&stop_scope=customer",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_events"], 2)
        self.assertEqual(body["total_billed_cost_micros"], 26_000_000)
