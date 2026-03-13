import pytest
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet


@pytest.mark.django_db
class TestWalletOverviewEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.c1 = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.c2 = Customer.objects.create(tenant=self.tenant, external_id="c2")
        self.w1 = Wallet.objects.create(customer=self.c1, balance_micros=5_000_000)
        self.w2 = Wallet.objects.create(customer=self.c2, balance_micros=500_000)

    def test_list_wallets(self):
        resp = self.http_client.get("/api/v1/platform/wallets", **self.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2

    def test_low_balance_filter(self):
        resp = self.http_client.get("/api/v1/platform/wallets?max_balance_micros=1000000", **self.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["customer_external_id"] == "c2"

    def test_excludes_other_tenants(self):
        other = Tenant.objects.create(name="Other", products=["metering", "billing"])
        oc = Customer.objects.create(tenant=other, external_id="oc")
        Wallet.objects.create(customer=oc, balance_micros=999)
        resp = self.http_client.get("/api/v1/platform/wallets", **self.headers)
        assert len(resp.json()["data"]) == 2
