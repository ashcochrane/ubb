import json
import uuid
import pytest
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestCustomerListEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.c1 = Customer.objects.create(tenant=self.tenant, external_id="cust_1", status="active")
        self.c2 = Customer.objects.create(tenant=self.tenant, external_id="cust_2", status="suspended")

    def test_list_customers(self):
        resp = self.http_client.get("/api/v1/platform/customers", **self.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert "next_cursor" in body
        assert "has_more" in body

    def test_list_customers_filter_by_status(self):
        resp = self.http_client.get("/api/v1/platform/customers?status=active", **self.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["external_id"] == "cust_1"

    def test_list_customers_search(self):
        resp = self.http_client.get("/api/v1/platform/customers?search=cust_2", **self.headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_excludes_other_tenants(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        Customer.objects.create(tenant=other, external_id="other_cust")
        resp = self.http_client.get("/api/v1/platform/customers", **self.headers)
        assert len(resp.json()["data"]) == 2

    def test_list_excludes_soft_deleted(self):
        self.c2.soft_delete()
        resp = self.http_client.get("/api/v1/platform/customers", **self.headers)
        assert len(resp.json()["data"]) == 1


@pytest.mark.django_db
class TestCustomerDetailEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="cust_1")

    def test_get_customer(self):
        resp = self.http_client.get(f"/api/v1/platform/customers/{self.customer.id}", **self.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["external_id"] == "cust_1"
        assert body["status"] == "active"

    def test_get_customer_not_found(self):
        resp = self.http_client.get(f"/api/v1/platform/customers/{uuid.uuid4()}", **self.headers)
        assert resp.status_code == 404


@pytest.mark.django_db
class TestCustomerUpdateEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="cust_1")

    def test_update_metadata(self):
        resp = self.http_client.patch(
            f"/api/v1/platform/customers/{self.customer.id}",
            data=json.dumps({"metadata": {"plan": "pro"}}),
            content_type="application/json",
            **self.headers,
        )
        assert resp.status_code == 200
        self.customer.refresh_from_db()
        assert self.customer.metadata == {"plan": "pro"}

    def test_update_status(self):
        resp = self.http_client.patch(
            f"/api/v1/platform/customers/{self.customer.id}",
            data=json.dumps({"status": "suspended"}),
            content_type="application/json",
            **self.headers,
        )
        assert resp.status_code == 200
        self.customer.refresh_from_db()
        assert self.customer.status == "suspended"


@pytest.mark.django_db
class TestCustomerDeleteEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="cust_1")

    def test_delete_soft_deletes(self):
        resp = self.http_client.delete(
            f"/api/v1/platform/customers/{self.customer.id}", **self.headers,
        )
        assert resp.status_code == 204
        assert Customer.objects.filter(id=self.customer.id).count() == 0
        assert Customer.all_objects.filter(id=self.customer.id).count() == 1
