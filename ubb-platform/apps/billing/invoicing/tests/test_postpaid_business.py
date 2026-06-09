import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


@pytest.mark.django_db
def test_business_aggregates_across_seats_one_line_per_seat():
    t = Tenant.objects.create(name="T", billing_mode="postpaid", products=["metering", "billing"])
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="allocated")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    s2 = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
    UsageEvent.objects.create(tenant=t, customer=s1, request_id="r1", idempotency_key="i1",
                              provider_cost_micros=1, billed_cost_micros=800_000)
    UsageEvent.objects.create(tenant=t, customer=s2, request_id="r2", idempotency_key="i2",
                              provider_cost_micros=1, billed_cost_micros=300_000)
    total, lines = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
    assert total == 1_100_000 and sum(a for _, a in lines) == total
    assert dict(lines)["alice"] == 800_000 and dict(lines)["bob"] == 300_000
