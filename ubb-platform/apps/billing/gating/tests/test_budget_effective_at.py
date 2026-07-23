"""F4.2 budget basis: live Redis counter is current-wall-clock-month only;
budgets themselves are effective-month (rebuild is effective_at-filtered)."""
import datetime
import uuid

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.budget_service import BudgetService
from apps.billing.gating.services.live_counter import Door
from apps.billing.handlers import handle_usage_recorded_billing
from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant


def _setup():
    # Postpaid: no wallet drawdown branch, but the budget tail still runs.
    t = Tenant.objects.create(name="T", products=["metering", "billing"],
                              billing_mode="postpaid")
    c = Customer.objects.create(tenant=t, external_id="c1")
    BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000)
    return t, c


def _draw(t, c, billed, n, effective_at=None):
    """Mirror production: the UsageEvent is durably committed (with its
    effective_at) before the outbox handler runs."""
    e = UsageEvent.objects.create(
        tenant=t, customer=c, request_id=f"r{n}", idempotency_key=f"i{n}",
        provider_cost_micros=billed, billed_cost_micros=billed)
    if effective_at is not None:
        UsageEvent.objects.filter(id=e.id).update(effective_at=effective_at)
    payload = {"tenant_id": str(t.id), "customer_id": str(c.id),
               "event_id": str(e.id), "cost_micros": billed}
    if effective_at is not None:
        payload["effective_at"] = effective_at.isoformat()
    handle_usage_recorded_billing(str(uuid.uuid4()), payload)


@pytest.mark.django_db
class TestBudgetEffectiveMonthBasis:
    def setup_method(self):
        cache.clear()

    def test_prior_month_backfill_leaves_live_counter_untouched(self):
        t, c = _setup()
        _draw(t, c, 100_000, 1)  # current month → counter = 100_000
        assert Door.budget(c.id) == 100_000

        prior = timezone.now().replace(day=1) - datetime.timedelta(days=2)
        _draw(t, c, 50_000, 2, effective_at=prior)
        # The live counter must NOT have been inflated by the prior-month event.
        assert Door.budget(c.id) == 100_000

    def test_same_month_backdated_event_increments(self):
        t, c = _setup()
        _draw(t, c, 100_000, 1)
        backdated_same_month = timezone.now() - datetime.timedelta(hours=1)
        if backdated_same_month.month != timezone.now().month:
            backdated_same_month = timezone.now()  # month boundary edge: stay in-month
        _draw(t, c, 50_000, 2, effective_at=backdated_same_month)
        assert Door.budget(c.id) == 150_000

    def test_legacy_payload_without_effective_at_increments(self):
        t, c = _setup()
        e = UsageEvent.objects.create(
            tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            billed_cost_micros=70_000)
        handle_usage_recorded_billing(str(uuid.uuid4()), {
            "tenant_id": str(t.id), "customer_id": str(c.id),
            "event_id": str(e.id), "cost_micros": 70_000})  # no effective_at key
        assert Door.budget(c.id) == 70_000

    def test_rebuild_equals_effective_filtered_total(self):
        """The hourly rebuild (source of truth) counts ONLY current-effective
        events — the backfilled prior-month event is excluded."""
        t, c = _setup()
        _draw(t, c, 300_000, 1)
        prior = timezone.now().replace(day=1) - datetime.timedelta(days=2)
        _draw(t, c, 200_000, 2, effective_at=prior)

        cache.clear()  # force the rebuild path
        BudgetService.reconcile_customer(c)
        assert BudgetService.current_spend(t.id, c.id) == 300_000
