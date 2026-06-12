"""F4.2: platform fees accrue in the ARRIVAL period. reconcile_period must no
longer drift-correct backdated events OUT of the period they arrived in —
matching the wall-clock accumulate_usage counter."""
import datetime

import pytest
from django.utils import timezone

from apps.billing.tenant_billing.services import TenantBillingService
from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestPlatformFeeArrivalBasis:
    def test_reconcile_keeps_backdated_arrivals_in_current_period(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"])
        c = Customer.objects.create(tenant=t, external_id="c1")

        # Live accumulator counted both events when they ARRIVED (now).
        TenantBillingService.accumulate_usage(t, 100)
        TenantBillingService.accumulate_usage(t, 100)
        period = TenantBillingService.get_or_create_current_period(t)
        period.refresh_from_db()
        assert period.total_usage_cost_micros == 200
        assert period.event_count == 2

        # One event is effective THIS month, the other is a backfill into the
        # PRIOR month — but both arrived (created_at) this month.
        UsageEvent.objects.create(
            tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            billed_cost_micros=100)
        e2 = UsageEvent.objects.create(
            tenant=t, customer=c, request_id="r2", idempotency_key="i2",
            billed_cost_micros=100)
        prior = timezone.now().replace(day=1) - datetime.timedelta(days=2)
        UsageEvent.objects.filter(id=e2.id).update(effective_at=prior)

        TenantBillingService.reconcile_period(period)
        period.refresh_from_db()
        # Arrival basis: the backdated event STAYS in this period — no drift
        # "correction" away from what accumulate_usage already counted.
        # (Under the old effective basis this would have recomputed to 100/1.)
        assert period.total_usage_cost_micros == 200
        assert period.event_count == 2
