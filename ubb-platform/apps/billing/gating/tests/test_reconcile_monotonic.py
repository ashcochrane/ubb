"""P1 (D8/I7): BudgetService.reconcile_customer is a monotonic MAX-merge.

The old reconcile did an absolute set(durable_total); mid-burst that could
set the counter BACKWARD below an in-flight record_usage_spend INCR the
durable ledger had not yet recorded — a lost update that re-allowed over-cap
spend. The fix is the live counter's atomic Lua MAX-merge (#111 D3b retired
the old two-dialect Django-cache/raw-client hack — the budget counter now
lives on the module's own raw key). These tests pin the merge semantics and
the one-key contract every budget op shares.
"""
import pytest
from django.core.cache import cache

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.budget_service import BudgetService
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant


def _setup():
    t = Tenant.objects.create(name="T", products=["metering", "billing"],
                              billing_mode="postpaid")
    c = Customer.objects.create(tenant=t, external_id="c1")
    BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=10_000_000)
    return t, c


def _durable_event(t, c, billed, n):
    """A committed UsageEvent contributes to the durable (Postgres) total that
    reconcile reads via get_customer_cost_totals (effective_at = now = in
    current month)."""
    UsageEvent.objects.create(
        tenant=t, customer=c, request_id=f"r{n}", idempotency_key=f"i{n}",
        provider_cost_micros=billed, billed_cost_micros=billed)


@pytest.mark.django_db
class TestReconcileMonotonic:
    def setup_method(self):
        cache.clear()

    def test_every_budget_op_targets_the_one_counter(self):
        # The one-key contract the merge relies on: the drawdown INCR
        # (budget_incr), the read (current_spend), and the MAX-merge all
        # address the SAME counter — the successor of the old D9 cross-client
        # probe, whose two-dialect key contract #111 D3b retired.
        t, c = _setup()
        Door.set_budget(c.id, 4242)
        old, new, _label = LiveCounter.budget_incr(t.id, c.id, 8)
        assert (old, new) == (4242, 4250)
        assert BudgetService.current_spend(t.id, c.id) == 4250
        assert Door.budget(c.id) == 4250

    def test_reconcile_never_lowers_inmonth_counter(self):
        t, c = _setup()
        # Counter is high (e.g. in-flight spend already counted); durable total
        # is 0 (no committed events yet). MAX-merge must keep the high value.
        Door.set_budget(c.id, 100_000_000)
        BudgetService.reconcile_customer(c)
        assert BudgetService.current_spend(t.id, c.id) == 100_000_000

    def test_reconcile_raises_to_durable_when_counter_drifted_low(self):
        t, c = _setup()
        _durable_event(t, c, 50_000_000, 1)  # durable total = 50M
        Door.set_budget(c.id, 10)  # counter drifted low
        BudgetService.reconcile_customer(c)
        assert BudgetService.current_spend(t.id, c.id) == 50_000_000

    def test_reconcile_concurrent_with_record_spend_no_lost_update(self):
        # Models the race: durable ledger has 30M committed, but the live
        # counter already reflects a further in-flight INCR (60M) the durable
        # read has not yet caught up to. The OLD absolute set(30M) would erase
        # the in-flight 30M; the MAX-merge must preserve 60M.
        t, c = _setup()
        _durable_event(t, c, 30_000_000, 1)  # durable total = 30M
        Door.set_budget(c.id, 60_000_000)  # in-flight ahead
        BudgetService.reconcile_customer(c)
        assert BudgetService.current_spend(t.id, c.id) == 60_000_000

    def test_reconcile_seeds_absent_key_to_durable_total(self):
        # Month-rollover / cold-key case: absent key -> seed to durable total.
        t, c = _setup()
        _durable_event(t, c, 25_000_000, 1)
        BudgetService.reconcile_customer(c)  # key absent after cache.clear()
        assert BudgetService.current_spend(t.id, c.id) == 25_000_000
