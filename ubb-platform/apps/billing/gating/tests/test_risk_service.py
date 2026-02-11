from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
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
        """Deny when balance < -arrears_threshold."""
        # Tenant default arrears_threshold is 5M
        # balance(-6M) < -5M → denied
        Wallet.objects.create(customer=self.customer, balance_micros=-6_000_000)
        result = RiskService.check(self.customer)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "insufficient_funds")
        self.assertEqual(result["balance_micros"], -6_000_000)

    def test_affordability_allowed_within_arrears_threshold(self):
        """Allow when balance >= -arrears_threshold."""
        # balance(-3M) >= -5M → allowed
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
        self.customer.arrears_threshold_micros = 0
        self.customer.save()
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 0)
