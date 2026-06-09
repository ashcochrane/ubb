import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
def test_service_agent_product_derived_from_tags():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=1000,
                                  tags={"service": "search", "agent": "planner", "product": "p1"})
    e = UsageEvent.objects.get(id=r["event_id"])
    assert e.service_id == "search"
    assert e.agent_id == "planner"
    assert e.product_id == "p1"

@pytest.mark.django_db
def test_explicit_product_id_wins_over_tag():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=1000,
                                  product_id="explicit", tags={"product": "fromtag", "service": "s"})
    e = UsageEvent.objects.get(id=r["event_id"])
    assert e.product_id == "explicit"
    assert e.service_id == "s"
