"""Tests for effective_at-based cost accumulator bucketing + repairing reconcile."""
import datetime

import pytest
from django.utils import timezone

from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.subscriptions.economics.models import CustomerCostAccumulator
from apps.subscriptions.handlers import handle_usage_recorded_subscriptions


@pytest.mark.django_db
def test_payload_fast_path_buckets_by_effective_at_without_db_read():
    """F4.2 fast path: the payload's effective_at wins — no UsageEvent row is
    needed at all (event_id deliberately bogus so the fallback getter would
    return None and the old code would have bucketed into the CURRENT month)."""
    t = Tenant.objects.create(name="T", products=["metering", "subscriptions"])
    c = Customer.objects.create(tenant=t, external_id="c1")
    backdated = timezone.now().replace(day=1) - datetime.timedelta(days=2)
    prior_month_start = backdated.date().replace(day=1)

    handle_usage_recorded_subscriptions("outbox-1", {
        "tenant_id": str(t.id), "customer_id": str(c.id),
        "cost_micros": 1_000_000, "provider_cost_micros": 800_000,
        "billed_cost_micros": 1_000_000,
        "event_id": "evt-not-a-uuid",
        "effective_at": backdated.isoformat(),
    })

    acc = CustomerCostAccumulator.objects.get(
        tenant=t, customer=c, period_start=prior_month_start)
    assert acc.total_billed_cost_micros == 1_000_000


@pytest.mark.django_db
def test_unparseable_payload_effective_at_falls_back_to_getter():
    """Garbage payload effective_at → fall back to the contract getter."""
    t = Tenant.objects.create(name="T", products=["metering", "subscriptions"])
    c = Customer.objects.create(tenant=t, external_id="c1")
    backdated = timezone.now().replace(day=1) - datetime.timedelta(days=2)
    prior_month_start = backdated.date().replace(day=1)
    e = UsageEvent.objects.create(
        tenant=t, customer=c, request_id="r1", idempotency_key="i1",
        provider_cost_micros=1, billed_cost_micros=2)
    UsageEvent.objects.filter(id=e.id).update(effective_at=backdated)

    handle_usage_recorded_subscriptions("outbox-1", {
        "tenant_id": str(t.id), "customer_id": str(c.id),
        "cost_micros": 2, "provider_cost_micros": 1, "billed_cost_micros": 2,
        "event_id": str(e.id),
        "effective_at": "not-a-timestamp",
    })

    assert CustomerCostAccumulator.objects.filter(
        tenant=t, customer=c, period_start=prior_month_start).exists()


@pytest.mark.django_db
def test_reconcile_covers_two_months_back():
    """A backfill 2 calendar months back (legal inside a 60-day window) is
    repaired by reconcile_cost_accumulators — the horizon is current + 2."""
    from apps.subscriptions.tasks import reconcile_cost_accumulators

    t = Tenant.objects.create(name="T", products=["metering", "subscriptions"])
    c = Customer.objects.create(tenant=t, external_id="c1")
    cur_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_start = (cur_start - datetime.timedelta(days=1)).replace(day=1)
    # Land INSIDE month-2 (its last day), still within any 60-day window.
    two_back = prev_start - datetime.timedelta(days=1)
    two_back_start = two_back.date().replace(day=1)

    e = UsageEvent.objects.create(
        tenant=t, customer=c, request_id="r1", idempotency_key="i1",
        provider_cost_micros=111, billed_cost_micros=222)
    UsageEvent.objects.filter(id=e.id).update(effective_at=two_back)

    reconcile_cost_accumulators()

    acc = CustomerCostAccumulator.objects.get(
        tenant=t, customer=c, period_start=two_back_start)
    assert acc.total_provider_cost_micros == 111
    assert acc.total_billed_cost_micros == 222
    assert acc.event_count == 1


@pytest.mark.django_db
def test_backdated_event_buckets_by_effective_at_not_wallclock():
    """A backdated UsageEvent must land in the prior-month accumulator, not today's."""
    t = Tenant.objects.create(name="T", products=["metering", "subscriptions"])
    c = Customer.objects.create(tenant=t, external_id="c1")

    # Push effective_at back into the prior calendar month
    backdated = timezone.now().replace(day=1) - datetime.timedelta(days=2)
    prior_month_start = backdated.date().replace(day=1)

    e = UsageEvent.objects.create(
        tenant=t, customer=c, request_id="r1", idempotency_key="i1",
        provider_cost_micros=800_000, billed_cost_micros=1_000_000,
    )
    # auto_now_add blocks direct assignment; bypass via queryset .update()
    UsageEvent.objects.filter(id=e.id).update(effective_at=backdated)

    handle_usage_recorded_subscriptions("outbox-1", {
        "tenant_id": str(t.id),
        "customer_id": str(c.id),
        "cost_micros": 1_000_000,
        "provider_cost_micros": 800_000,
        "billed_cost_micros": 1_000_000,
        "event_id": str(e.id),
    })

    acc = CustomerCostAccumulator.objects.get(
        tenant=t, customer=c, period_start=prior_month_start
    )
    assert acc.total_provider_cost_micros == 800_000
    assert acc.total_billed_cost_micros == 1_000_000


@pytest.mark.django_db
def test_reconcile_cost_accumulators_repairs_wrong_bucket():
    """reconcile_cost_accumulators() corrects a prior-month accumulator to match the ledger."""
    from apps.subscriptions.tasks import reconcile_cost_accumulators

    t = Tenant.objects.create(name="T2", products=["metering", "subscriptions"])
    c = Customer.objects.create(tenant=t, external_id="c2")

    # Create a backdated UsageEvent in the prior calendar month
    backdated = timezone.now().replace(day=1) - datetime.timedelta(days=2)
    prior_month_start = backdated.date().replace(day=1)

    e = UsageEvent.objects.create(
        tenant=t, customer=c, request_id="r2", idempotency_key="i2",
        provider_cost_micros=500_000, billed_cost_micros=700_000,
    )
    UsageEvent.objects.filter(id=e.id).update(effective_at=backdated)

    # Deliberately create a *wrong* accumulator (simulates the old wall-clock bug
    # having placed the event in the current month instead of prior month).
    today = timezone.now().date()
    cur_start = today.replace(day=1)
    if today.month == 12:
        cur_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        cur_end = today.replace(month=today.month + 1, day=1)

    CustomerCostAccumulator.objects.create(
        tenant=t, customer=c,
        period_start=cur_start, period_end=cur_end,
        total_provider_cost_micros=500_000,
        total_billed_cost_micros=700_000,
        event_count=1,
    )

    # Run the reconcile — it should create the correct prior-month accumulator
    # AND zero out the stale current-month one (bidirectional reconcile).
    reconcile_cost_accumulators()

    # Prior-month accumulator must now reflect the ledger
    acc = CustomerCostAccumulator.objects.get(
        tenant=t, customer=c, period_start=prior_month_start
    )
    assert acc.total_provider_cost_micros == 500_000
    assert acc.total_billed_cost_micros == 700_000
    assert acc.event_count == 1

    # The stale current-month accumulator must have been ZEROED (event is not in
    # that period).  This is the bidirectional fix: existing accumulators whose
    # ledger value is 0 must be updated to 0/0/0, not left at stale positive values.
    cur_acc = CustomerCostAccumulator.objects.get(
        tenant=t, customer=c, period_start=cur_start
    )
    assert cur_acc.total_provider_cost_micros == 0, (
        f"stale accumulator was not zeroed: provider={cur_acc.total_provider_cost_micros}"
    )
    assert cur_acc.total_billed_cost_micros == 0, (
        f"stale accumulator was not zeroed: billed={cur_acc.total_billed_cost_micros}"
    )
    assert cur_acc.event_count == 0, (
        f"stale accumulator was not zeroed: event_count={cur_acc.event_count}"
    )
