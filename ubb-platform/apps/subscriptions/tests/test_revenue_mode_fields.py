import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
def test_revenue_mode_columns_exist_with_defaults():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    assert c.revenue_mode == ""  # blank = derive from billing_mode
    from apps.subscriptions.economics.models import CustomerEconomics
    import datetime
    e = CustomerEconomics.objects.create(tenant=t, customer=c,
        period_start=datetime.date(2026, 6, 1), period_end=datetime.date(2026, 7, 1))
    assert e.revenue_mode == "" and e.total_revenue_micros == 0
