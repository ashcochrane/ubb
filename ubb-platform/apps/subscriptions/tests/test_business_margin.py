import datetime
import pytest
from unittest.mock import patch
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.subscriptions.economics.services import MarginService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


@pytest.mark.django_db
def test_compute_business_sums_seats():
    t = Tenant.objects.create(name="T", products=["metering", "billing"], billing_mode="postpaid")
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="allocated")
    s1 = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
    s2 = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
    UsageEvent.objects.create(tenant=t, customer=s1, request_id="r1", idempotency_key="i1",
                              provider_cost_micros=200_000, billed_cost_micros=500_000)
    UsageEvent.objects.create(tenant=t, customer=s2, request_id="r2", idempotency_key="i2",
                              provider_cost_micros=100_000, billed_cost_micros=300_000)
    d = MarginService.compute_business(t.id, biz, PS, PE)
    assert d["totals"]["gross_margin_micros"] == 500_000  # (500k+300k) billed − (200k+100k) provider
    assert len(d["seats"]) == 2


class BusinessMarginEndpointTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="BizCo", products=["metering", "billing"],
                                            billing_mode="postpaid")
        _, self.key = TenantApiKey.create_key(self.tenant, label="test")
        self.biz = Customer.objects.create(tenant=self.tenant, external_id="biz",
                                           account_type="business", billing_topology="allocated")
        self.s1 = Customer.objects.create(tenant=self.tenant, external_id="alice",
                                          account_type="seat", parent=self.biz)
        self.s2 = Customer.objects.create(tenant=self.tenant, external_id="bob",
                                          account_type="seat", parent=self.biz)
        with patch("apps.platform.events.tasks.process_single_event"):
            from apps.metering.usage.services.usage_service import UsageService
            UsageService.record_usage(
                tenant=self.tenant, customer=self.s1, request_id="r1", idempotency_key="i1",
                provider_cost_micros=200_000, billed_cost_micros=500_000, provider="openai")
            UsageService.record_usage(
                tenant=self.tenant, customer=self.s2, request_id="r2", idempotency_key="i2",
                provider_cost_micros=100_000, billed_cost_micros=300_000, provider="openai")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_business_margin_endpoint(self):
        r = self.http.get("/api/v1/margin/business/biz", **self._auth())
        assert r.status_code == 200
        body = r.json()
        assert "totals" in body
        assert "gross_margin_micros" in body["totals"]
        assert len(body["seats"]) == 2
