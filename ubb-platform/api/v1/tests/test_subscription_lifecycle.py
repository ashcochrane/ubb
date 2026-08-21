import pytest
from django.test import Client

from apps.platform.customers.models import Customer
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestLifecycleRoutesMoved:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"],
            stripe_connected_account_id="acct_test", charges_enabled=True,
            default_currency="usd")
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        Customer.objects.create(tenant=self.tenant, external_id="c1")
        a_plan(tenant=self.tenant, key="lite", name="Lite")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, data=None):
        return self.client.post(path, data=data or {},
                                content_type="application/json", **self._auth())

    def test_old_platform_routes_are_gone(self):
        assert self._post("/api/v1/platform/plans",
                          {"key": "x", "name": "X"}).status_code == 404
        assert self._post("/api/v1/platform/customers/c1/subscribe",
                          {"plan_key": "lite"}).status_code == 404

    def test_subscribe_lives_on_the_subscriptions_router(self):
        r = self._post("/api/v1/subscriptions/customers/c1/subscribe",
                       {"plan_key": "lite", "seats": 0})
        # Markup-only plan: assigned, but no Stripe subscription created.
        assert r.status_code == 200
        assert r.json()["subscription_id"] is None

    def test_lifecycle_requires_billing_product(self):
        other = Tenant.objects.create(name="M", products=["metering"])
        _, key = TenantApiKey.create_key(other)
        r = self.client.post("/api/v1/subscriptions/customers/c1/subscribe",
                             data={"plan_key": "lite"},
                             content_type="application/json",
                             HTTP_AUTHORIZATION=f"Bearer {key}")
        assert r.status_code == 403
