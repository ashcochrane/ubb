import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
def test_record_usage_pins_business_owner_for_pooled_seat():
    t = Tenant.objects.create(name="T")
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business", billing_topology="pooled")
    seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
    r = UsageService.record_usage(t, seat, "r1", "i1", provider_cost_micros=1000)
    e = UsageEvent.objects.get(id=r["event_id"])
    assert e.billing_owner_id == biz.id  # pinned to the business at write time
