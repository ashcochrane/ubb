from django.test import TestCase
from apps.tenants.models import Tenant
from apps.customers.models import Customer
from apps.gating.models import RiskConfig
from apps.gating.services.risk_service import RiskService


class RiskServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="u1", email="t@t.com")
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
