import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestPlatformCustomerCRUD:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def test_create_customer(self):
        resp = self.client.post(
            "/api/v1/platform/customers",
            data={"external_id": "ext1", "stripe_customer_id": "cus_123"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 201
        assert resp.json()["external_id"] == "ext1"

    def test_create_customer_conflict(self):
        from apps.platform.customers.models import Customer
        Customer.objects.create(
            tenant=self.tenant, external_id="ext1",
        )
        resp = self.client.post(
            "/api/v1/platform/customers",
            data={"external_id": "ext1", "stripe_customer_id": "cus_123"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 409
