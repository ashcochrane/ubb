from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.billing.wallets.models import CustomerBillingProfile, Wallet


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
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
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
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=0,
        )
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 0)

    def test_check_returns_null_task_id_by_default(self):
        result = RiskService.check(self.customer)
        self.assertIsNone(result["task_id"])


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


class RiskServiceTaskTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="u1"
        )
        RiskConfig.objects.create(tenant=self.tenant)
        BillingTenantConfig.objects.create(
            tenant=self.tenant,
            default_task_floor_snapshot_micros=-5_000_000,
        )

    def _enable_coverage(self):
        # The tenant-config API requires an active cost rate card to flip
        # this; tests set the model field directly (per the #37 brief).
        self.tenant.require_cost_card_coverage = True
        self.tenant.save(update_fields=["require_cost_card_coverage"])

    def test_check_with_create_task_returns_task_id(self):
        # No explicit limit and no RiskConfig default -> uncapped task; the
        # floor snapshot comes from the tenant billing config.
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        result = RiskService.check(self.customer, create_task=True)
        self.assertTrue(result["allowed"])
        self.assertIsNotNone(result["task_id"])
        self.assertIsNone(result["provider_cost_limit_micros"])
        self.assertEqual(result["floor_snapshot_micros"], -5_000_000)

        # Verify the Task was created in DB
        task = Task.objects.get(id=result["task_id"])
        self.assertEqual(task.status, "active")
        self.assertEqual(task.balance_snapshot_micros, 20_000_000)
        self.assertEqual(task.customer_id, self.customer.id)
        self.assertIsNone(task.provider_cost_limit_micros)
        self.assertEqual(task.floor_snapshot_micros, -5_000_000)

    def test_explicit_limit_refused_without_coverage(self):
        # A resolved non-null COGS limit with require_cost_card_coverage off
        # is refused at the gate — no task is created.
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        result = RiskService.check(
            self.customer, create_task=True,
            provider_cost_limit_micros=10_000_000,
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "cost_coverage_required")
        self.assertIsNone(result["task_id"])
        self.assertEqual(Task.objects.count(), 0)

    def test_default_limit_refused_without_coverage(self):
        # The tenant-default limit resolves non-null too — same refusal.
        config = self.tenant.risk_config
        config.default_task_provider_cost_limit_micros = 7_000_000
        config.save(update_fields=["default_task_provider_cost_limit_micros"])
        result = RiskService.check(self.customer, create_task=True)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "cost_coverage_required")
        self.assertEqual(Task.objects.count(), 0)

    def test_explicit_limit_with_coverage_creates_limited_task(self):
        self._enable_coverage()
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        result = RiskService.check(
            self.customer, create_task=True,
            provider_cost_limit_micros=10_000_000,
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["provider_cost_limit_micros"], 10_000_000)
        self.assertEqual(result["floor_snapshot_micros"], -5_000_000)
        task = Task.objects.get(id=result["task_id"])
        self.assertEqual(task.provider_cost_limit_micros, 10_000_000)
        self.assertEqual(task.floor_snapshot_micros, -5_000_000)

    def test_tenant_default_limit_applies_when_no_explicit_limit(self):
        self._enable_coverage()
        config = self.tenant.risk_config
        config.default_task_provider_cost_limit_micros = 7_000_000
        config.save(update_fields=["default_task_provider_cost_limit_micros"])
        result = RiskService.check(self.customer, create_task=True)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["provider_cost_limit_micros"], 7_000_000)
        task = Task.objects.get(id=result["task_id"])
        self.assertEqual(task.provider_cost_limit_micros, 7_000_000)

    def test_check_denied_does_not_create_task(self):
        Wallet.objects.create(customer=self.customer, balance_micros=-6_000_000)
        result = RiskService.check(self.customer, create_task=True)
        self.assertFalse(result["allowed"])
        self.assertIsNone(result["task_id"])
        self.assertEqual(Task.objects.count(), 0)

    def test_check_without_create_task_returns_null_task_id(self):
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        result = RiskService.check(self.customer, create_task=False)
        self.assertTrue(result["allowed"])
        self.assertIsNone(result["task_id"])
        self.assertEqual(Task.objects.count(), 0)

    def test_check_create_task_with_metadata_and_external_id(self):
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        result = RiskService.check(
            self.customer,
            create_task=True,
            task_metadata={"workflow": "search"},
            external_task_id="ext-abc",
        )
        task = Task.objects.get(id=result["task_id"])
        self.assertEqual(task.metadata, {"workflow": "search"})
        self.assertEqual(task.external_task_id, "ext-abc")

    def test_check_create_task_no_wallet_snapshots_zero(self):
        # No wallet created — balance defaults to 0
        result = RiskService.check(self.customer, create_task=True)
        self.assertTrue(result["allowed"])
        task = Task.objects.get(id=result["task_id"])
        self.assertEqual(task.balance_snapshot_micros, 0)


import pytest
from django.core.cache import cache as django_cache
from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.budget_service import BudgetService
from apps.billing.gating.services.live_counter import LiveCounter


@pytest.mark.django_db
class TestRiskServiceBudget:
    def setup_method(self):
        django_cache.clear()

    def _funded(self, **cfg):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="T", products=["metering", "billing"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c)
        w.balance_micros = 10_000_000  # plenty — affordability passes
        w.save(update_fields=["balance_micros"])
        if cfg:
            BudgetConfig.objects.create(tenant=t, customer=c, **cfg)
        return c

    def _spend(self, c, amount):
        from apps.metering.usage.models import UsageEvent
        UsageEvent.objects.create(tenant=c.tenant, customer=c, request_id="r", idempotency_key="i",
                                  provider_cost_micros=amount, billed_cost_micros=amount)
        LiveCounter.budget_incr(c.tenant_id, c.id, amount)

    def test_no_budget_config_allows(self):
        c = self._funded()
        assert RiskService.check(c)["allowed"] is True

    def test_enforcing_over_cap_denies(self):
        c = self._funded(cap_micros=1_000, enforce_mode="enforcing", hard_stop_pct=100)
        self._spend(c, 1_000)  # at cap
        res = RiskService.check(c)
        assert res["allowed"] is False and res["reason"] == "budget_exceeded"

    def test_advisory_over_cap_allows(self):
        c = self._funded(cap_micros=1_000, enforce_mode="advisory")
        self._spend(c, 5_000)  # way over
        assert RiskService.check(c)["allowed"] is True

    def test_gate_fail_open_when_redis_down_with_budget_config(self):
        # Even with an enforcing budget config, a Redis outage must NOT block the
        # pre-call gate — the money is still guarded by the Postgres credit check.
        from unittest.mock import patch
        c = self._funded(cap_micros=1_000, enforce_mode="enforcing")
        with patch("apps.billing.gating.services.live_counter._client",
                   side_effect=ConnectionError("redis down")):
            res = RiskService.check(c)
        assert res["allowed"] is True

    def test_postpaid_negative_balance_still_allowed(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="pp")
        Wallet.objects.create(customer=c, balance_micros=-9_999_999)  # deep negative
        assert RiskService.check(c)["allowed"] is True  # postpaid never gates on credit balance

    def test_postpaid_budget_cap_still_enforced(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import UsageEvent
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="pp")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=1_000, enforce_mode="enforcing")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i",
                                  provider_cost_micros=1_000, billed_cost_micros=1_000)
        LiveCounter.budget_incr(t.id, c.id, 1_000)
        res = RiskService.check(c)
        assert res["allowed"] is False and res["reason"] == "budget_exceeded"

    def test_suspended_business_gates_its_seat(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PB", products=["metering", "billing"], billing_mode="prepaid")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="pooled", status="suspended")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        res = RiskService.check(seat)
        assert res["allowed"] is False and res["reason"] == "insufficient_funds"

    def test_pooled_seat_affordability_reads_business_wallet(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PB", products=["metering", "billing"], billing_mode="prepaid")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        Wallet.objects.create(customer=biz, balance_micros=-9_999_999)  # business pool deep negative
        assert RiskService.check(seat)["allowed"] is False
