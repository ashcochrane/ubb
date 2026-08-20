import pytest
from django.db import IntegrityError
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.platform.plans.models import Plan


@pytest.mark.django_db
def test_billing_plan_roundtrip_and_unique_key():
    t = Tenant.objects.create(name="T", products=["metering", "billing"])
    p = a_plan(tenant=t, key="pro", name="Pro",
        access_fee_micros=50_000_000, per_seat_micros=8_000_000, interval="month")
    assert Plan.objects.get(id=p.id).access_fee_micros == 50_000_000
    with pytest.raises(IntegrityError):
        a_plan(tenant=t, key="pro", name="Dup")
