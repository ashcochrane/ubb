"""One-rule enforcement — the #37 acceptance pins (spec §L, task legs).

Pin 1  — the tipping event lands and bills: sync task limit, async task limit
         at settle.
Pin 2  — events on a killed task land, bill, and count into both totals.
Pin 3  — a below-floor event lands and bills; Wallet carries no floor CHECK
         (ADR-002 pin).
Pin 7  — every recorded event answers 200; no code path returns 429/409 for a
         usage report.
Pin 14 — only the provider (COGS) total races the task limit; both totals on
         the record and the response.
Pin 15 — the coverage gate refuses `cost_coverage_required` with coverage
         off, passes with it on.
Pin 16 — the tag fallback is removed: tags={"task": ...} with no task_id gets
         no unit attribution, no limit, no kill.
Pin 17 — the clean-cut sweep: no run-era event type in the catalog, neither
         retired Redis key family is ever written, the old per-task cap
         config is gone, and no API/SDK/event surface answers to a run-era
         name.
"""
import json
import uuid
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, Client

from apps.billing.gating.models import RiskConfig
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import RawIngestEvent, UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.models import Task
from apps.platform.tasks.services import TaskService
from apps.platform.tenants.models import Tenant, TenantApiKey


class OneRulePinTestBase(TestCase):
    def setUp(self):
        cache.clear()
        from api.v1 import metering_endpoints
        metering_endpoints._TASK_META_CACHE.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="OneRule", products=["metering", "billing", "metering_async"],
            billing_mode="prepaid",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=100_000_000)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _task(self, limit=10_000_000, floor=None, balance=100_000_000):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit, floor_snapshot_micros=floor,
            billing_owner_id=self.customer.id)

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "request_id": f"req-{uuid.uuid4()}",
            "idempotency_key": f"idem-{uuid.uuid4()}",
        }
        data.update(extra)
        return self.http_client.post(
            "/api/v1/metering/usage", data=json.dumps(data),
            content_type="application/json", **self._auth())

    def _limit_events(self):
        return OutboxEvent.objects.filter(event_type="task.limit_exceeded")


@patch("apps.platform.events.tasks.process_single_event")
class Pin1SyncTippingEventTest(OneRulePinTestBase):
    def test_tipping_event_lands_bills_and_kills(self, _mock):
        task = self._task(limit=10_000_000)
        resp = self._record(task_id=str(task.id),
                            provider_cost_micros=11_000_000,
                            billed_cost_micros=15_000_000)

        # The event that crossed the limit answers 200 and is durably
        # recorded + billed — never rolled back.
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        event = UsageEvent.objects.get(id=body["event_id"])
        self.assertEqual(event.billed_cost_micros, 15_000_000)
        self.assertEqual(event.provider_cost_micros, 11_000_000)
        self.assertEqual(event.task_id, task.id)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="usage.recorded").count(), 1)

        # Both totals include the tipping event; the task flipped to killed.
        task.refresh_from_db()
        self.assertEqual(task.total_provider_cost_micros, 11_000_000)
        self.assertEqual(task.total_billed_cost_micros, 15_000_000)
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.metadata["kill_reason"], "task_limit")

        # The stop verdict rides the 200; the fan-out event fired exactly once.
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_limit")
        self.assertEqual(body["stop_scope"], "task")
        self.assertEqual(body["task_total_provider_cost_micros"], 11_000_000)
        self.assertEqual(body["task_total_billed_cost_micros"], 15_000_000)
        self.assertEqual(self._limit_events().count(), 1)
        payload = self._limit_events().get().payload
        self.assertEqual(payload["reason"], "task_limit")
        self.assertEqual(payload["task_id"], str(task.id))
        self.assertEqual(payload["total_provider_cost_micros"], 11_000_000)
        self.assertEqual(payload["provider_cost_limit_micros"], 10_000_000)


@patch("apps.platform.events.tasks.process_single_event")
class Pin1AsyncSettleTest(OneRulePinTestBase):
    def test_async_task_limit_detected_at_settle(self, _mock):
        from apps.metering.usage.tasks import settle_raw_events

        task = self._task(limit=10_000_000)
        resp = self.http_client.post(
            "/api/v1/metering/usage/ingest",
            data=json.dumps({"events": [{
                "customer_id": str(self.customer.id),
                "request_id": "r-async", "idempotency_key": "i-async",
                "task_id": str(task.id),
                "provider_cost_micros": 12_000_000,
                "billed_cost_micros": 12_000_000,
            }]}),
            content_type="application/json", **self._auth())

        # Accept never rejects for limit reasons and never kills.
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["results"][0]["accepted"])
        task.refresh_from_db()
        self.assertEqual(task.status, "active")
        self.assertEqual(self._limit_events().count(), 0)

        # Settle runs the accumulate primitive with exact costs -> the same
        # verdicts, kill flow, and event as the sync path.
        settle_raw_events()
        raw = RawIngestEvent.objects.get()
        self.assertEqual(raw.status, "settled")
        self.assertEqual(raw.task_id, task.id)
        event = UsageEvent.objects.get()
        self.assertEqual(event.task_id, task.id)
        self.assertEqual(event.provider_cost_micros, 12_000_000)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.total_provider_cost_micros, 12_000_000)
        self.assertEqual(self._limit_events().count(), 1)
        self.assertEqual(self._limit_events().get().payload["reason"], "task_limit")


@patch("apps.platform.events.tasks.process_single_event")
class Pin2KilledTaskStillCountsTest(OneRulePinTestBase):
    def test_events_on_killed_task_land_bill_and_count(self, _mock):
        task = self._task(limit=10_000_000)
        # Trip the limit (kills the task) ...
        self._record(task_id=str(task.id), provider_cost_micros=11_000_000,
                     billed_cost_micros=11_000_000)
        # ... then a late event arrives on the killed task.
        resp = self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                            billed_cost_micros=3_000_000)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_not_active")
        self.assertEqual(body["stop_scope"], "task")

        # The late event landed, billed, and counted into BOTH totals.
        self.assertEqual(UsageEvent.objects.count(), 2)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.total_provider_cost_micros, 13_000_000)
        self.assertEqual(task.total_billed_cost_micros, 14_000_000)
        self.assertEqual(body["task_total_provider_cost_micros"], 13_000_000)
        self.assertEqual(body["task_total_billed_cost_micros"], 14_000_000)
        # No re-announcement for late events: still exactly one kill event.
        self.assertEqual(self._limit_events().count(), 1)


@patch("apps.platform.events.tasks.process_single_event")
class Pin3BelowFloorLandsTest(OneRulePinTestBase):
    def test_below_floor_event_lands_bills_and_signals(self, _mock):
        # Floor snapshot: balance snapshot 5M, floor 0 — a 6M event drives
        # the estimated balance below the floor.
        task = self._task(limit=None, floor=0, balance=5_000_000)
        resp = self._record(task_id=str(task.id), provider_cost_micros=6_000_000,
                            billed_cost_micros=6_000_000)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "customer_floor")
        self.assertEqual(body["stop_scope"], "task")
        # Landed and billed — the ledger records what was spent, not what a
        # wall wished had been spent.
        event = UsageEvent.objects.get(id=body["event_id"])
        self.assertEqual(event.billed_cost_micros, 6_000_000)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.metadata["kill_reason"], "customer_floor")

    def test_wallet_carries_no_floor_check(self, _mock):
        # ADR-002: DB constraints enforce accounting facts, never spend
        # policy — the wallet must accept a negative balance.
        for constraint in Wallet._meta.constraints:
            self.assertNotIn("balance", constraint.name.lower())
        self.wallet.balance_micros = -42_000_000
        self.wallet.save(update_fields=["balance_micros"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, -42_000_000)


@patch("apps.platform.events.tasks.process_single_event")
class Pin7TwoHundredAlwaysTest(OneRulePinTestBase):
    def test_no_usage_report_path_answers_429_or_409(self, _mock):
        task = self._task(limit=1_000_000)
        # Tipping event, then two more on the killed task — singles.
        for i in range(3):
            resp = self._record(task_id=str(task.id),
                                provider_cost_micros=2_000_000,
                                billed_cost_micros=2_000_000)
            self.assertEqual(resp.status_code, 200)
            self.assertNotIn("hard_stop", resp.json())

        # Batch parity: every item on the killed task still lands with ok=True.
        events = [{
            "customer_id": str(self.customer.id),
            "request_id": f"rb{i}", "idempotency_key": f"ib{i}",
            "task_id": str(task.id), "provider_cost_micros": 500_000,
        } for i in range(2)]
        resp = self.http_client.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": events}),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["succeeded"], 2)
        for item in body["results"]:
            self.assertTrue(item["ok"])
            self.assertEqual(item["stop_reason"], "task_not_active")

        # Every report recorded: 3 singles + 2 batch items.
        self.assertEqual(UsageEvent.objects.count(), 5)
        task.refresh_from_db()
        self.assertEqual(task.event_count, 5)


@patch("apps.platform.events.tasks.process_single_event")
class Pin14DenominationTest(OneRulePinTestBase):
    def test_only_the_provider_total_races_the_limit(self, _mock):
        task = self._task(limit=10_000_000)
        # Billed way past the limit, provider under it -> nothing fires.
        resp = self._record(task_id=str(task.id), provider_cost_micros=1_000_000,
                            billed_cost_micros=50_000_000)
        body = resp.json()
        self.assertFalse(body["stop"])
        task.refresh_from_db()
        self.assertEqual(task.status, "active")
        self.assertEqual(self._limit_events().count(), 0)

        # Both totals on the record and the response, denominationally explicit.
        self.assertEqual(task.total_billed_cost_micros, 50_000_000)
        self.assertEqual(task.total_provider_cost_micros, 1_000_000)
        self.assertEqual(body["task_total_billed_cost_micros"], 50_000_000)
        self.assertEqual(body["task_total_provider_cost_micros"], 1_000_000)

        # The provider total crossing is what kills.
        resp = self._record(task_id=str(task.id), provider_cost_micros=9_500_000,
                            billed_cost_micros=1)
        self.assertTrue(resp.json()["stop"])
        self.assertEqual(resp.json()["stop_reason"], "task_limit")
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")


class Pin15CoverageGateTest(OneRulePinTestBase):
    def _pre_check(self, **extra):
        data = {"customer_id": str(self.customer.id), "start_task": True}
        data.update(extra)
        return self.http_client.post(
            "/api/v1/billing/pre-check", data=json.dumps(data),
            content_type="application/json", **self._auth())

    def test_explicit_limit_refused_without_coverage(self):
        resp = self._pre_check(provider_cost_limit_micros=5_000_000)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["reason"], "cost_coverage_required")
        self.assertEqual(Task.objects.count(), 0)

    def test_default_limit_refused_without_coverage(self):
        RiskConfig.objects.create(
            tenant=self.tenant, default_task_provider_cost_limit_micros=7_000_000)
        resp = self._pre_check()
        body = resp.json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["reason"], "cost_coverage_required")
        self.assertEqual(Task.objects.count(), 0)

    def test_limit_passes_with_coverage_on(self):
        self.tenant.require_cost_card_coverage = True
        self.tenant.save(update_fields=["require_cost_card_coverage"])
        RiskConfig.objects.create(
            tenant=self.tenant, default_task_provider_cost_limit_micros=7_000_000)

        # Explicit limit wins over the default.
        body = self._pre_check(provider_cost_limit_micros=5_000_000).json()
        self.assertTrue(body["allowed"])
        task = Task.objects.get(id=body["task_id"])
        self.assertEqual(task.provider_cost_limit_micros, 5_000_000)
        self.assertEqual(body["provider_cost_limit_micros"], 5_000_000)

        # Absent an explicit limit, the tenant default applies.
        body = self._pre_check().json()
        self.assertTrue(body["allowed"])
        self.assertEqual(body["provider_cost_limit_micros"], 7_000_000)

    def test_uncapped_start_needs_no_coverage(self):
        body = self._pre_check().json()
        self.assertTrue(body["allowed"])
        task = Task.objects.get(id=body["task_id"])
        self.assertIsNone(task.provider_cost_limit_micros)


@patch("apps.platform.events.tasks.process_single_event")
class Pin16TagFallbackRemovedTest(OneRulePinTestBase):
    def test_task_tag_gets_no_attribution_no_limit_no_kill(self, _mock):
        task = self._task(limit=1)  # would trip on any attributed event
        resp = self._record(tags={"task": str(task.id)},
                            provider_cost_micros=5_000_000,
                            billed_cost_micros=5_000_000)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body["task_id"])
        self.assertIsNone(body["task_total_provider_cost_micros"])
        self.assertFalse(body["stop"])

        event = UsageEvent.objects.get(id=body["event_id"])
        self.assertIsNone(event.task_id)
        self.assertEqual(event.tags, {"task": str(task.id)})  # analytics only
        task.refresh_from_db()
        self.assertEqual(task.status, "active")
        self.assertEqual(task.event_count, 0)
        self.assertEqual(self._limit_events().count(), 0)


# --- Pin 17: the clean-cut sweep -------------------------------------------

# Run-era tokens that must not answer on any wire/config/SDK surface. The
# label-cap reason string and the 429 error code are included: they retired
# with the 429 and are deliberately never reused.
_RUN_ERA_TOKENS = (
    "run_id", "run.limit_exceeded", "RunLimitExceeded", "hard_stop_exceeded",
    "run_not_active", "start_run", "close_run", "external_run_id",
    "run_metadata", "run_total_cost_micros", "ubb:runcost", "ubb:taskcost",
    "max_cost_per_task_micros", "run_cost_limit_micros",
    "hard_stop_balance_micros", "cost_limit_exceeded",
    "balance_floor_exceeded", "task_limit_exceeded", "run_stale_seconds",
)

_PLATFORM_ROOT = Path(__file__).resolve().parents[3]

# The public surfaces the clean cut renames wholesale.
_SURFACE_FILES = [
    _PLATFORM_ROOT / "api" / "v1" / "schemas.py",
    _PLATFORM_ROOT / "api" / "v1" / "metering_endpoints.py",
    _PLATFORM_ROOT / "api" / "v1" / "billing_endpoints.py",
    _PLATFORM_ROOT / "api" / "v1" / "tenant_endpoints.py",
    _PLATFORM_ROOT / "apps" / "platform" / "events" / "schemas.py",
    _PLATFORM_ROOT / "apps" / "platform" / "events" / "catalog.py",
]
_SDK_ROOT = _PLATFORM_ROOT.parent / "ubb-sdk" / "ubb"


class Pin17CleanCutSweepTest(OneRulePinTestBase):
    def test_no_run_era_event_type_in_catalog(self):
        from apps.platform.events import catalog, schemas
        self.assertNotIn("run.limit_exceeded", catalog.WEBHOOK_EVENT_TYPES)
        self.assertIn("task.limit_exceeded", catalog.WEBHOOK_EVENT_TYPES)
        self.assertFalse(hasattr(schemas, "RunLimitExceeded"))

    def test_retired_config_fields_are_gone(self):
        risk_fields = {f.name for f in RiskConfig._meta.get_fields()}
        self.assertNotIn("max_cost_per_task_micros", risk_fields)
        self.assertIn("default_task_provider_cost_limit_micros", risk_fields)

        tenant_fields = {f.name for f in Tenant._meta.get_fields()}
        for gone in ("run_cost_limit_micros", "hard_stop_balance_micros",
                     "run_stale_seconds"):
            self.assertNotIn(gone, tenant_fields)
        self.assertIn("task_stale_seconds", tenant_fields)

        btc_fields = {f.name for f in BillingTenantConfig._meta.get_fields()}
        self.assertNotIn("run_cost_limit_micros", btc_fields)
        self.assertNotIn("hard_stop_balance_micros", btc_fields)
        self.assertIn("default_task_floor_snapshot_micros", btc_fields)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_neither_retired_redis_key_family_is_ever_written(self, _mock):
        # Drive both ingest lanes end to end (the paths that once wrote
        # ubb:runcost:* and ubb:taskcost:*), then scan the whole test Redis DB.
        import redis
        from django.conf import settings
        from apps.metering.usage.tasks import settle_raw_events

        self.tenant.enforcement_mode = "enforcing"
        self.tenant.save(update_fields=["enforcement_mode"])
        task = self._task(limit=1_000_000)
        self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                     billed_cost_micros=2_000_000, tags={"task": "labelled"})
        self.http_client.post(
            "/api/v1/metering/usage/ingest",
            data=json.dumps({"events": [{
                "customer_id": str(self.customer.id),
                "request_id": "r17", "idempotency_key": "i17",
                "task_id": str(task.id), "billed_cost_micros": 3_000_000,
            }]}),
            content_type="application/json", **self._auth())
        settle_raw_events()

        client = redis.from_url(settings.REDIS_URL)
        for family in (b"ubb:runcost:*", b"ubb:taskcost:*"):
            self.assertEqual(list(client.scan_iter(match=family)), [],
                             f"retired key family {family} was written")

    def test_no_surface_answers_to_a_run_era_name(self):
        surface_files = list(_SURFACE_FILES)
        self.assertTrue(_SDK_ROOT.is_dir(), "ubb-sdk checkout expected beside ubb-platform")
        surface_files += sorted(_SDK_ROOT.glob("*.py"))
        for path in surface_files:
            text = path.read_text(encoding="utf-8")
            for token in _RUN_ERA_TOKENS:
                self.assertNotIn(
                    token, text,
                    f"run-era token {token!r} survives in {path.name}")

    def test_task_routes_replaced_run_routes(self):
        task = self._task(limit=None)
        resp = self.http_client.post(
            f"/api/v1/metering/tasks/{task.id}/close", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "completed")
        self.assertIn("total_billed_cost_micros", body)
        self.assertIn("total_provider_cost_micros", body)
        resp = self.http_client.post(
            f"/api/v1/metering/runs/{task.id}/close", **self._auth())
        self.assertEqual(resp.status_code, 404)
