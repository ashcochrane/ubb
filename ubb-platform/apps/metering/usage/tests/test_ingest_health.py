from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import RawIngestEvent


def _mk_raw(tenant, customer, status="pending", age_seconds=0, attempts=0):
    raw = RawIngestEvent.objects.create(
        tenant=tenant, customer=customer, billing_owner_id=customer.id,
        idempotency_key=f"k-{status}-{age_seconds}-{attempts}",
        payload={}, status=status, attempts=attempts,
    )
    if age_seconds:
        RawIngestEvent.objects.filter(id=raw.id).update(
            created_at=timezone.now() - timedelta(seconds=age_seconds))
    return raw


class IngestHealthServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Health")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="h1")

    def test_metrics_across_statuses(self):
        from apps.metering.usage.services.ingest_health import ingest_health
        _mk_raw(self.tenant, self.customer, "pending", age_seconds=300)
        _mk_raw(self.tenant, self.customer, "pending", age_seconds=60, attempts=2)
        _mk_raw(self.tenant, self.customer, "settled")
        _mk_raw(self.tenant, self.customer, "duplicate")
        _mk_raw(self.tenant, self.customer, "failed")
        h = ingest_health()
        self.assertEqual(h["pending_count"], 2)
        self.assertEqual(h["retrying_count"], 1)
        self.assertEqual(h["failed_count"], 1)
        self.assertGreaterEqual(h["oldest_pending_age_seconds"], 300)
        self.assertLess(h["oldest_pending_age_seconds"], 330)

    def test_empty_pipeline_zeroes(self):
        from apps.metering.usage.services.ingest_health import ingest_health
        h = ingest_health()
        self.assertEqual(h["pending_count"], 0)
        self.assertEqual(h["oldest_pending_age_seconds"], 0.0)

    def test_tenant_filter(self):
        from apps.metering.usage.services.ingest_health import ingest_health
        other_t = Tenant.objects.create(name="Other")
        other_c = Customer.objects.create(tenant=other_t, external_id="o1")
        _mk_raw(self.tenant, self.customer, "pending")
        _mk_raw(other_t, other_c, "pending")
        self.assertEqual(ingest_health(tenant_id=self.tenant.id)["pending_count"], 1)
        self.assertEqual(ingest_health()["pending_count"], 2)


@override_settings(UBB_INGEST_SETTLE_LAG_WARN_SECONDS=120,
                   UBB_INGEST_QUEUE_DEPTH_WARN=3)
class MonitorIngestHealthTaskTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="HealthMon")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="hm1")

    def _run(self):
        from apps.metering.usage.tasks import monitor_ingest_health
        return monitor_ingest_health()

    def test_healthy_logs_info(self):
        _mk_raw(self.tenant, self.customer, "pending", age_seconds=5)
        with self.assertLogs("ubb.metering", level="INFO") as logs:
            self._run()
        self.assertTrue(any("ingest.health" in m for m in logs.output))
        self.assertFalse(any(m.startswith(("WARNING", "ERROR")) for m in logs.output))

    def test_lag_breach_warns(self):
        _mk_raw(self.tenant, self.customer, "pending", age_seconds=200)
        with self.assertLogs("ubb.metering", level="WARNING") as logs:
            self._run()
        self.assertTrue(any(m.startswith("WARNING") for m in logs.output))

    def test_depth_5x_breach_errors(self):
        for i in range(16):  # depth warn 3, 5x = 15
            _mk_raw(self.tenant, self.customer, "pending", age_seconds=i + 1)
        with self.assertLogs("ubb.metering", level="ERROR") as logs:
            self._run()
        self.assertTrue(any(m.startswith("ERROR") for m in logs.output))

    def test_any_failed_errors_every_cycle(self):
        _mk_raw(self.tenant, self.customer, "failed")
        for _ in range(2):  # stays loud on repeat runs — deliberate
            with self.assertLogs("ubb.metering", level="ERROR") as logs:
                self._run()
            self.assertTrue(any(m.startswith("ERROR") for m in logs.output))
