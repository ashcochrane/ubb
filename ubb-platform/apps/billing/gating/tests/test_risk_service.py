from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.wallets.models import Wallet


class RiskServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="u1")
        RiskConfig.objects.create(tenant=self.tenant, max_requests_per_minute=10, max_concurrent_requests=3)

    def test_active_customer_passes(self):
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])

    def test_suspended_customer_blocked(self):
        self.customer.status = "suspended"
        self.customer.save()
        result = RiskService.check(self.customer)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "insufficient_funds")

    def test_closed_customer_blocked(self):
        self.customer.status = "closed"
        self.customer.save()
        result = RiskService.check(self.customer)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "account_closed")

    def test_no_risk_config_passes(self):
        RiskConfig.objects.all().delete()
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])

    def test_returns_balance_micros(self):
        Wallet.objects.create(customer=self.customer, balance_micros=5_000_000)
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 5_000_000)

    def test_no_wallet_defaults_balance_to_zero(self):
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 0)

    def test_affordability_denied_when_balance_below_negative_threshold(self):
        """Deny when balance < -min_balance."""
        # Tenant default min_balance is 0
        # balance(-6M) < -0 → denied
        Wallet.objects.create(customer=self.customer, balance_micros=-6_000_000)
        result = RiskService.check(self.customer)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "insufficient_funds")
        self.assertEqual(result["balance_micros"], -6_000_000)

    def test_affordability_allowed_within_min_balance(self):
        """Allow when balance >= -min_balance (custom threshold)."""
        # Set a 5M min_balance on tenant so -3M >= -5M → allowed
        self.tenant.min_balance_micros = 5_000_000
        self.tenant.save(update_fields=["min_balance_micros", "updated_at"])
        Wallet.objects.create(customer=self.customer, balance_micros=-3_000_000)
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], -3_000_000)

    def test_affordability_allowed_positive_balance(self):
        """Positive balance is always allowed."""
        Wallet.objects.create(customer=self.customer, balance_micros=100)
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 100)

    def test_affordability_denied_no_wallet_zero_threshold(self):
        """No wallet (balance=0), zero threshold: balance(0) < -0 is false → allowed."""
        self.customer.min_balance_micros = 0
        self.customer.save()
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 0)

    def test_check_returns_null_run_id_by_default(self):
        result = RiskService.check(self.customer)
        self.assertIsNone(result["run_id"])


class RiskServiceRedisFailureTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="u1")
        RiskConfig.objects.create(tenant=self.tenant, max_requests_per_minute=10)

    def test_allows_when_redis_unavailable(self):
        """Pre-check should degrade gracefully when Redis is down."""
        from unittest.mock import patch
        with patch("apps.billing.gating.services.risk_service.cache") as mock_cache:
            mock_cache.get.side_effect = ConnectionError("Redis unavailable")
            result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])


class RiskServiceRunTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test",
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="u1"
        )
        RiskConfig.objects.create(tenant=self.tenant)

    def test_check_with_create_run_returns_run_id(self):
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        result = RiskService.check(self.customer, create_run=True)
        self.assertTrue(result["allowed"])
        self.assertIsNotNone(result["run_id"])
        self.assertEqual(result["cost_limit_micros"], 10_000_000)
        self.assertEqual(result["hard_stop_balance_micros"], -5_000_000)

        # Verify Run was created in DB
        run = Run.objects.get(id=result["run_id"])
        self.assertEqual(run.status, "active")
        self.assertEqual(run.balance_snapshot_micros, 20_000_000)
        self.assertEqual(run.customer_id, self.customer.id)

    def test_check_denied_does_not_create_run(self):
        Wallet.objects.create(customer=self.customer, balance_micros=-6_000_000)
        result = RiskService.check(self.customer, create_run=True)
        self.assertFalse(result["allowed"])
        self.assertIsNone(result["run_id"])
        self.assertEqual(Run.objects.count(), 0)

    def test_check_without_create_run_returns_null_run_id(self):
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        result = RiskService.check(self.customer, create_run=False)
        self.assertTrue(result["allowed"])
        self.assertIsNone(result["run_id"])
        self.assertEqual(Run.objects.count(), 0)

    def test_check_create_run_with_metadata_and_external_id(self):
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        result = RiskService.check(
            self.customer,
            create_run=True,
            run_metadata={"workflow": "search"},
            external_run_id="ext-abc",
        )
        run = Run.objects.get(id=result["run_id"])
        self.assertEqual(run.metadata, {"workflow": "search"})
        self.assertEqual(run.external_run_id, "ext-abc")

    def test_check_create_run_no_wallet_snapshots_zero(self):
        # No wallet created — balance defaults to 0
        result = RiskService.check(self.customer, create_run=True)
        self.assertTrue(result["allowed"])
        run = Run.objects.get(id=result["run_id"])
        self.assertEqual(run.balance_snapshot_micros, 0)
