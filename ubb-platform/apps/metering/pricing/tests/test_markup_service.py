import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import TenantMarkup
from apps.metering.pricing.services.markup_service import MarkupService


@pytest.mark.django_db
class TestMarkupService:
    def test_no_markup_returns_provider_cost(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 100_000

    def test_tenant_default_markup_applied(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=20_000_000)  # 20%
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 120_000

    def test_customer_override_beats_tenant_default(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=20_000_000)
        TenantMarkup.objects.create(tenant=t, customer=c, markup_percentage_micros=50_000_000)
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 150_000

    def test_fixed_uplift_added(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=0, fixed_uplift_micros=500)
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 100_500
