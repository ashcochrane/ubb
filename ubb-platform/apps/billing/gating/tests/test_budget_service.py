import pytest
from django.core.cache import cache
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.budget_service import BudgetService


@pytest.mark.django_db
class TestBudgetService:
    def setup_method(self):
        cache.clear()

    def _cust(self, **cfg):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        if cfg:
            BudgetConfig.objects.create(tenant=t, customer=c, **cfg)
        return c

    def _usage(self, c, billed, n):
        # Mirror production: the UsageEvent is durably committed BEFORE record_spend runs,
        # so a counter rebuild-on-miss reconstructs to the total that already includes it.
        from apps.metering.usage.models import UsageEvent
        UsageEvent.objects.create(
            tenant=c.tenant, customer=c, request_id=f"r{n}", idempotency_key=f"i{n}",
            provider_cost_micros=billed, billed_cost_micros=billed)

    def test_record_and_current_spend(self):
        c = self._cust(cap_micros=1_000_000)
        self._usage(c, 300_000, 1)  # event committed first (as in production)
        old, new, label = BudgetService.record_spend(c.tenant_id, c.id, 300_000)
        assert (old, new) == (0, 300_000)  # rebuild-on-miss = durable total (300k), already includes the event
        self._usage(c, 200_000, 2)
        old, new, label = BudgetService.record_spend(c.tenant_id, c.id, 200_000)  # incr path
        assert (old, new) == (300_000, 500_000)
        assert BudgetService.current_spend(c.tenant_id, c.id) == 500_000

    def test_current_spend_rebuilds_from_postgres_on_miss(self):
        from unittest.mock import patch
        c = self._cust(cap_micros=1_000_000)
        with patch("apps.billing.gating.services.budget_service.get_customer_cost_totals",
                   return_value={"provider_cost_micros": 0, "billed_cost_micros": 750_000, "event_count": 1}):
            cache.clear()
            assert BudgetService.current_spend(c.tenant_id, c.id) == 750_000

    def test_check_no_config_allows(self):
        c = self._cust()
        assert BudgetService.check(c)["allowed"] is True

    def test_check_zero_cap_inert(self):
        c = self._cust(cap_micros=0, enforce_mode="enforcing")
        BudgetService.record_spend(c.tenant_id, c.id, 999_999_999)
        assert BudgetService.check(c)["allowed"] is True

    def test_advisory_never_denies(self):
        c = self._cust(cap_micros=1_000, enforce_mode="advisory")
        BudgetService.record_spend(c.tenant_id, c.id, 5_000)
        assert BudgetService.check(c)["allowed"] is True

    def test_enforcing_denies_at_cap(self):
        c = self._cust(cap_micros=1_000, enforce_mode="enforcing", hard_stop_pct=100)
        self._usage(c, 999, 1)  # durable event backs the first (miss → rebuild) increment
        BudgetService.record_spend(c.tenant_id, c.id, 999)
        assert BudgetService.check(c)["allowed"] is True   # 999 < 1000
        BudgetService.record_spend(c.tenant_id, c.id, 1)   # incr → 1000 == cap
        res = BudgetService.check(c)
        assert res["allowed"] is False and res["reason"] == "budget_exceeded"
