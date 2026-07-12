import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.accounts import resolve_billing_owner, resolve_billing_owner_id


@pytest.mark.django_db
class TestResolver:
    def test_individual_resolves_to_self(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert resolve_billing_owner_id(c) == c.id

    def test_pooled_seat_resolves_to_business(self):
        t = Tenant.objects.create(name="T")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        assert resolve_billing_owner_id(seat) == biz.id

    def test_allocated_seat_resolves_to_self(self):
        t = Tenant.objects.create(name="T")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="allocated")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        assert resolve_billing_owner_id(seat) == seat.id

    def test_customer_method_matches_billing_resolver(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        t = Tenant.objects.create(name="T2")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        assert seat.resolve_billing_owner().id == biz.id
        ind = Customer.objects.create(tenant=t, external_id="i1")
        assert ind.resolve_billing_owner().id == ind.id
