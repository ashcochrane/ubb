import pytest
from django.test import Client

from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestPlanEndpoints:
    def setup_method(self):
        # products=["metering", "billing"] is REQUIRED: plan routes gate on
        # ProductAccess("billing"), so a metering-only tenant gets 403.
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, data):
        return self.client.post(path, data=data, content_type="application/json",
                                **self._auth())

    def _get(self, path):
        return self.client.get(path, **self._auth())

    def test_create_plan_with_all_three_axes(self):
        r = self._post("/api/v1/plans", {
            "key": "enterprise", "name": "Enterprise",
            "access_fee_micros": 100_000_000, "per_seat_micros": 10_000_000,
            "markup_percentage_micros": 20_000_000, "interval": "month"})
        assert r.status_code == 201
        body = r.json()
        assert body["key"] == "enterprise"
        assert body["markup_percentage_micros"] == 20_000_000

    def test_create_markup_only_plan(self):
        r = self._post("/api/v1/plans", {
            "key": "personal-lite", "name": "Personal Lite",
            "markup_percentage_micros": 50_000_000})
        assert r.status_code == 201
        assert r.json()["access_fee_micros"] == 0

    def test_duplicate_key_is_409(self):
        self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})
        r = self._post("/api/v1/plans", {"key": "pro", "name": "Pro"})
        assert r.status_code == 409

    def test_invalid_interval_is_422(self):
        r = self._post("/api/v1/plans", {"key": "p", "name": "P", "interval": "day"})
        assert r.status_code == 422

    def test_list_plans(self):
        Plan.objects.create(tenant=self.tenant, key="a", name="A")
        Plan.objects.create(tenant=self.tenant, key="b", name="B")
        r = self._get("/api/v1/plans")
        assert r.status_code == 200
        assert [p["key"] for p in r.json()["plans"]] == ["a", "b"]

    def test_get_plan_by_key(self):
        Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        assert self._get("/api/v1/plans/pro").status_code == 200
        assert self._get("/api/v1/plans/nope").status_code == 404

    def test_patch_updates_markup_without_touching_stripe(self):
        Plan.objects.create(tenant=self.tenant, key="lite", name="Lite",
                            markup_percentage_micros=50_000_000)
        r = self.client.patch("/api/v1/plans/lite",
                              data={"markup_percentage_micros": 60_000_000},
                              content_type="application/json", **self._auth())
        assert r.status_code == 200
        assert r.json()["markup_percentage_micros"] == 60_000_000

    def test_assign_customer_to_plan(self):
        Plan.objects.create(tenant=self.tenant, key="lite", name="Lite")
        Customer.objects.create(tenant=self.tenant, external_id="c1")
        r = self._post("/api/v1/customers/c1/plan", {"plan_key": "lite"})
        assert r.status_code == 200
        assert CustomerPlanAssignment.objects.filter(plan__key="lite").exists()

    def test_archive_refuses_an_assigned_plan(self):
        plan = Plan.objects.create(tenant=self.tenant, key="lite", name="Lite")
        c = Customer.objects.create(tenant=self.tenant, external_id="c1")
        CustomerPlanAssignment.objects.create(tenant=self.tenant, customer=c, plan=plan)
        r = self.client.delete("/api/v1/plans/lite", **self._auth())
        assert r.status_code == 409

    def test_tenant_without_billing_is_403(self):
        other = Tenant.objects.create(name="M", products=["metering"])
        _, key = TenantApiKey.create_key(other)
        r = self.client.get("/api/v1/plans", HTTP_AUTHORIZATION=f"Bearer {key}")
        assert r.status_code == 403
