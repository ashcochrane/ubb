"""P1 (D8/I7): BudgetService.reconcile_customer is a monotonic MAX-merge.

The old reconcile did an absolute cache.set(durable_total); mid-burst that
could set the counter BACKWARD below an in-flight record_usage_spend INCR the
durable ledger had not yet recorded — a lost update that re-allowed over-cap
spend. The fix is an atomic Lua MAX-merge on the SAME physical key the Django
cache uses. These tests pin both the merge semantics and the cross-client
key/prefix contract the merge relies on (D9).
"""
import pytest
from django.core.cache import cache

from apps.billing.gating.models import BudgetConfig
from apps.billing.gating.services.budget_service import (
    BudgetService, _key, _period, _raw_redis,
)
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

    def test_raw_client_reads_cache_key(self):
        # D9 contract: the raw redis client + cache.make_key target the SAME
        # physical key, and an int set by the Django cache is a plain integer
        # the raw client (and our Lua) can read. If this ever breaks, the
        # MAX-merge would silently operate on a different/absent key.
        cache.set("budget:probetest", 4242, timeout=300)
        raw = _raw_redis()
        physical = raw.get(cache.make_key("budget:probetest"))
        assert physical == b"4242"

    def test_reconcile_never_lowers_inmonth_counter(self):
        t, c = _setup()
        label, _, _ = _period()
        # Counter is high (e.g. in-flight spend already counted); durable total
        # is 0 (no committed events yet). MAX-merge must keep the high value.
        cache.set(_key(c.id, label), 100_000_000, timeout=300)
        BudgetService.reconcile_customer(c)
        assert BudgetService.current_spend(t.id, c.id) == 100_000_000

    def test_reconcile_raises_to_durable_when_counter_drifted_low(self):
        t, c = _setup()
        label, _, _ = _period()
        _durable_event(t, c, 50_000_000, 1)  # durable total = 50M
        cache.set(_key(c.id, label), 10, timeout=300)  # counter drifted low
        BudgetService.reconcile_customer(c)
        assert BudgetService.current_spend(t.id, c.id) == 50_000_000

    def test_reconcile_concurrent_with_record_spend_no_lost_update(self):
        # Models the race: durable ledger has 30M committed, but the live
        # counter already reflects a further in-flight INCR (60M) the durable
        # read has not yet caught up to. The OLD absolute set(30M) would erase
        # the in-flight 30M; the MAX-merge must preserve 60M.
        t, c = _setup()
        label, _, _ = _period()
        _durable_event(t, c, 30_000_000, 1)  # durable total = 30M
        cache.set(_key(c.id, label), 60_000_000, timeout=300)  # in-flight ahead
        BudgetService.reconcile_customer(c)
        assert BudgetService.current_spend(t.id, c.id) == 60_000_000

    def test_reconcile_seeds_absent_key_to_durable_total(self):
        # Month-rollover / cold-key case: absent key -> seed to durable total.
        t, c = _setup()
        _durable_event(t, c, 25_000_000, 1)
        BudgetService.reconcile_customer(c)  # key absent after cache.clear()
        assert BudgetService.current_spend(t.id, c.id) == 25_000_000
