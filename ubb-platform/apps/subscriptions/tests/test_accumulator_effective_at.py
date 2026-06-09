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
