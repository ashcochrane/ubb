import pytest
from django.core.cache import cache
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.budget_service import BudgetService
from apps.billing.gating.services.live_counter import Door


@pytest.mark.django_db
class TestBudgetReconciliation:
    def setup_method(self):
        cache.clear()

    def test_reconcile_rebuilds_counter_from_ledger(self):
        from apps.billing.gating.tasks import reconcile_budget_counters
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000)
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
                                  provider_cost_micros=400_000, billed_cost_micros=400_000)
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r2", idempotency_key="i2",
                                  provider_cost_micros=350_000, billed_cost_micros=350_000)
        Door.set_budget(c.id, 0)  # corrupt/drifted counter
        reconcile_budget_counters()
        assert BudgetService.current_spend(c.tenant_id, c.id) == 750_000
