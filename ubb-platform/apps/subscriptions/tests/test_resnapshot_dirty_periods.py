"""F4.2 resnapshot_dirty_periods: prior-month markers older than the settle
floor refresh the margin snapshot then ack; crash keeps the marker; a fresh
marker (accumulator may not have settled — outbox horizon) is not consumed;
a non-prior (clock-skew) marker is skipped WITHOUT ack."""
import datetime
from unittest import mock

import pytest
from django.utils import timezone

from apps.metering.usage.models import BackfillDirtyPeriod
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.subscriptions.economics.models import (
    CustomerCostAccumulator, CustomerEconomics,
)
from apps.subscriptions.tasks import (
    RESNAPSHOT_MARKER_MIN_AGE, resnapshot_dirty_periods,
)


def _setup():
    t = Tenant.objects.create(name="T", products=["metering", "subscriptions"])
    c = Customer.objects.create(tenant=t, external_id="c1")
    cur_start = timezone.now().date().replace(day=1)
    prior_start = (cur_start - datetime.timedelta(days=1)).replace(day=1)
    return t, c, cur_start, prior_start


def _aged_marker(t, c, period_start, age=None):
    """Markers younger than RESNAPSHOT_MARKER_MIN_AGE are deliberately NOT
    consumed (the accumulator is outbox-populated; ~2h43m retry horizon).
    created_at is auto_now_add — the queryset update bypasses it."""
    marker = BackfillDirtyPeriod.objects.create(
        tenant=t, customer=c, period_start=period_start)
    age = age if age is not None else RESNAPSHOT_MARKER_MIN_AGE + datetime.timedelta(hours=1)
    BackfillDirtyPeriod.objects.filter(id=marker.id).update(
        created_at=timezone.now() - age)
    return marker


@pytest.mark.django_db
class TestResnapshotDirtyPeriods:
    def test_prior_month_marker_resnapshots_then_acks(self):
        t, c, cur_start, prior_start = _setup()
        CustomerCostAccumulator.objects.create(
            tenant=t, customer=c, period_start=prior_start, period_end=cur_start,
            total_provider_cost_micros=300, total_billed_cost_micros=900,
            event_count=2)
        _aged_marker(t, c, prior_start)

        resnapshot_dirty_periods()

        econ = CustomerEconomics.objects.get(
            tenant_id=t.id, customer_id=c.id, period_start=prior_start)
        assert econ.provider_cost_micros == 300
        assert econ.usage_billed_micros == 900
        assert econ.period_end == cur_start
        assert BackfillDirtyPeriod.objects.count() == 0

    def test_resnapshot_updates_stale_snapshot(self):
        """An existing (stale) prior-month snapshot is UPDATED, not duplicated."""
        t, c, cur_start, prior_start = _setup()
        CustomerEconomics.objects.create(
            tenant_id=t.id, customer_id=c.id, period_start=prior_start,
            period_end=cur_start, provider_cost_micros=1, usage_billed_micros=1,
            total_revenue_micros=0, gross_margin_micros=-1, margin_percentage=0)
        CustomerCostAccumulator.objects.create(
            tenant=t, customer=c, period_start=prior_start, period_end=cur_start,
            total_provider_cost_micros=500, total_billed_cost_micros=700,
            event_count=1)
        _aged_marker(t, c, prior_start)

        resnapshot_dirty_periods()

        econs = CustomerEconomics.objects.filter(
            tenant_id=t.id, customer_id=c.id, period_start=prior_start)
        assert econs.count() == 1
        assert econs.get().provider_cost_micros == 500

    def test_crash_keeps_marker_for_retry(self):
        t, c, cur_start, prior_start = _setup()
        _aged_marker(t, c, prior_start)
        with mock.patch(
                "apps.subscriptions.economics.services.MarginService.snapshot_customer",
                side_effect=RuntimeError("boom")):
            resnapshot_dirty_periods()  # must not raise out of the task
        assert BackfillDirtyPeriod.objects.count() == 1  # retried next hour

        # The retry (no crash) succeeds and acks.
        resnapshot_dirty_periods()
        assert BackfillDirtyPeriod.objects.count() == 0

    def test_fresh_marker_not_consumed(self):
        """A marker younger than RESNAPSHOT_MARKER_MIN_AGE is NOT consumed: the
        accumulator the snapshot would read is outbox-populated, and a dispatch
        can still be in flight for ~2h43m — acking now could freeze a stale
        prior-month snapshot forever."""
        t, c, cur_start, prior_start = _setup()
        BackfillDirtyPeriod.objects.create(
            tenant=t, customer=c, period_start=prior_start)  # created NOW
        with mock.patch(
                "apps.subscriptions.economics.services.MarginService.snapshot_customer"
        ) as snap:
            resnapshot_dirty_periods()
        snap.assert_not_called()
        assert BackfillDirtyPeriod.objects.count() == 1  # left for a later run

    def test_current_month_marker_skipped_without_ack(self):
        """Markers are only ever written for PRIOR months, so a current-month
        marker is reachable only via clock skew — acking it would discard work.
        It must be left IN PLACE (consumed once the month genuinely rolls)."""
        t, c, cur_start, prior_start = _setup()
        _aged_marker(t, c, cur_start)
        with mock.patch(
                "apps.subscriptions.economics.services.MarginService.snapshot_customer"
        ) as snap:
            resnapshot_dirty_periods()
        snap.assert_not_called()
        assert BackfillDirtyPeriod.objects.count() == 1  # NOT acked

    def test_one_failing_marker_does_not_block_others(self):
        t, c, cur_start, prior_start = _setup()
        c2 = Customer.objects.create(tenant=t, external_id="c2")
        _aged_marker(t, c, prior_start)
        _aged_marker(t, c2, prior_start)
        from apps.subscriptions.economics.services import MarginService
        real = MarginService.snapshot_customer

        def fail_for_c1(tenant_id, customer_id, period_start, period_end):
            if str(customer_id) == str(c.id):
                raise RuntimeError("boom")
            return real(tenant_id, customer_id, period_start, period_end)

        with mock.patch(
                "apps.subscriptions.economics.services.MarginService.snapshot_customer",
                side_effect=fail_for_c1):
            resnapshot_dirty_periods()
        assert BackfillDirtyPeriod.objects.filter(customer=c).count() == 1
        assert BackfillDirtyPeriod.objects.filter(customer=c2).count() == 0
