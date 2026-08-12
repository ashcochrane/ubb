import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import Posting


@pytest.mark.django_db
def test_the_open_bag_no_longer_lifts_into_dim_columns():
    """Task 9: the reserved-label lifting (dim2 <- ["service"], dim3 <-
    ["agent"], dim1 <- ["product"]) is deleted — the open bag is free-form
    labelling only, never dimension attribution. dim1 only fills from
    an explicit declared dimension (``dimension_slots``), never from the bag."""
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=1000,
                                  metadata={"service": "search", "agent": "planner", "product": "p1"})
    e = Posting.objects.get(id=r["event_id"])
    assert e.grouping_field_2 == ""
    assert e.grouping_field_3 == ""
    assert e.grouping_field_1 == ""

@pytest.mark.django_db
def test_declared_dim1_fills_dim1_a_label_does_not():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=1000,
                                  dimension_slots={"grouping_field_1": "explicit"},
                                  metadata={"product": "fromlabel", "service": "s"})
    e = Posting.objects.get(id=r["event_id"])
    assert e.grouping_field_1 == "explicit"
    assert e.grouping_field_2 == ""
