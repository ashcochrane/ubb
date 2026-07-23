"""End-to-end Stage 3: usage drawdown → Redis budget counter → threshold webhook
→ pre-call gate, across the advisory→enforcing flip. Exercises the real seams
(handle_usage_recorded_billing, BudgetService, RiskService) wired together."""
import uuid
from dataclasses import asdict

import pytest
from django.core.cache import cache

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import UsageRecorded
from apps.billing.wallets.models import Wallet
from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.budget_service import BudgetService
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.handlers import handle_usage_recorded_billing
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
class TestBudgetEndToEnd:
    def setup_method(self):
        cache.clear()

    def _draw(self, tenant, customer, billed, n):
        # Mirror production: the UsageEvent is durably committed before the drawdown handler runs.
        UsageEvent.objects.create(
            tenant=tenant, customer=customer, request_id=f"r{n}", idempotency_key=f"i{n}",
            provider_cost_micros=billed, billed_cost_micros=billed)
        event = OutboxEvent.objects.create(
            event_type="usage.recorded", tenant_id=tenant.id,
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id, customer_id=customer.id,
                event_id=str(uuid.uuid4()), cost_micros=billed)))
        handle_usage_recorded_billing(str(event.id), event.payload)

    def test_advisory_alerts_then_enforcing_blocks(self):
        tenant = Tenant.objects.create(name="LocalScouta", products=["metering", "billing"],
                                       stripe_connected_account_id="acct_x")
        customer = Customer.objects.create(tenant=tenant, external_id="cust1")
        w = Wallet.objects.create(customer=customer)
        w.balance_micros = 1_000_000_000  # well funded — credit gate always passes here
        w.save(update_fields=["balance_micros"])
        BudgetConfig.objects.create(tenant=tenant, customer=customer,
                                    cap_micros=1_000_000, enforce_mode="advisory")

        # --- advisory: usage crosses 50% → one alert, gate still allows ---
        self._draw(tenant, customer, 600_000, 1)
        assert BudgetService.current_spend(tenant.id, customer.id) == 600_000
        assert OutboxEvent.objects.filter(
            event_type="budget.threshold_reached", payload__level=50).count() == 1
        assert RiskService.check(customer)["allowed"] is True  # advisory never blocks

        # --- flip to enforcing (config-only), drive over the cap → gate blocks ---
        BudgetConfig.objects.filter(tenant=tenant, customer=customer).update(enforce_mode="enforcing")
        self._draw(tenant, customer, 500_000, 2)  # 1_100_000 total > 1_000_000 cap
        assert BudgetService.current_spend(tenant.id, customer.id) == 1_100_000
        res = RiskService.check(customer)
        assert res["allowed"] is False and res["reason"] == "budget_exceeded"
