import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
def test_tags_no_longer_lift_into_dim_columns():
    """Task 9: the reserved-tag lifting (dim2 <- tags["service"], dim3 <-
    tags["agent"], dim1 <- tags["product"]) is deleted — tags are free-form
    analytics labels only, never dimension attribution. dim1 only fills from
    an explicit declared dimension (``dimension_slots``), never from tags."""
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=1000,
                                  tags={"service": "search", "agent": "planner", "product": "p1"})
    e = UsageEvent.objects.get(id=r["event_id"])
    assert e.dim2 == ""
    assert e.dim3 == ""
    assert e.dim1 == ""

@pytest.mark.django_db
def test_declared_dim1_fills_dim1_tag_does_not():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=1000,
                                  dimension_slots={"dim1": "explicit"},
                                  tags={"product": "fromtag", "service": "s"})
    e = UsageEvent.objects.get(id=r["event_id"])
    assert e.dim1 == "explicit"
    assert e.dim2 == ""
