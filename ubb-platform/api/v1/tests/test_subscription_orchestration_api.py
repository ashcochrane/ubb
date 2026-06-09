"""Wave 4 — plan + subscribe + seats platform API.

A tenant defines a billing plan, subscribes an end-customer (access fee + seats),
and changes seat count — all self-serve. Stripe is mocked at the orchestrator's
``stripe.*`` for the subscribe / set_seats calls.
"""
import contextlib

import pytest
from unittest.mock import patch, MagicMock

from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.subscriptions.models import (
    TenantBillingPlan,
    CustomerSubscriptionItem,
    StripeSubscription,
)


def _fake_sub():
    """A Stripe Subscription dict with two licensed items (access + seat)."""
    return {
        "id": "sub_1",
        "status": "active",
        "currency": "usd",
        "items": {"data": [
            {"id": "si_a", "price": {"id": "price_a", "unit_amount": 5000,
                                     "recurring": {"interval": "month", "usage_type": "licensed"}},
             "quantity": 1},
            {"id": "si_s", "price": {"id": "price_s", "unit_amount": 800,
                                     "recurring": {"interval": "month", "usage_type": "licensed"}},
             "quantity": 10},
        ]},
    }


@pytest.mark.django_db
class TestSubscriptionOrchestrationAPI:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="SubTest",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_sub",
            charges_enabled=True,
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def _post(self, path, data):
        return self.client.post(
            path,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def _make_plan(self, key="pro"):
        return self._post("/api/v1/platform/plans", {
            "key": key, "name": "Pro",
            "access_fee_micros": 50_000_000, "per_seat_micros": 8_000_000,
            "interval": "month",
        })

    def _make_customer(self, external_id="biz"):
        return Customer.objects.create(
            tenant=self.tenant, external_id=external_id, stripe_customer_id="cus_biz",
        )

    @contextlib.contextmanager
    def _mock_stripe_subscribe(self):
        """Mock every Stripe write the subscribe flow performs.

        A plan created through the API is unprovisioned, so subscribe() provisions
        Products/Prices first, then creates the Subscription.
        """
        svc = "apps.subscriptions.orchestration.service.stripe"
        with patch(f"{svc}.Product.create",
                   side_effect=[MagicMock(id="prod_a"), MagicMock(id="prod_s")]), \
             patch(f"{svc}.Price.create",
                   side_effect=[MagicMock(id="price_a"), MagicMock(id="price_s")]), \
             patch(f"{svc}.Subscription.create", return_value=_fake_sub()):
            yield

    # ---- POST /plans ----

    def test_create_plan(self):
        resp = self._make_plan()
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "pro"
        assert data["access_fee_micros"] == 50_000_000
        assert data["per_seat_micros"] == 8_000_000
        assert TenantBillingPlan.objects.filter(tenant=self.tenant, key="pro").exists()

    def test_create_plan_duplicate_key_returns_422(self):
        assert self._make_plan().status_code == 201
        resp = self._make_plan()
        assert resp.status_code == 422

    # ---- POST /customers/{external_id}/subscribe ----

    def test_subscribe(self):
        self._make_plan()
        self._make_customer("biz")
        with self._mock_stripe_subscribe():
            resp = self._post("/api/v1/platform/customers/biz/subscribe",
                              {"plan_key": "pro", "seats": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_id"] == "sub_1"
        # access (5000c x1) + seat (800c x10) = 50_000_000 + 80_000_000 micros
        assert data["amount_micros"] == 130_000_000
        assert data["quantity"] == 10
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_1")
        biz = Customer.objects.get(tenant=self.tenant, external_id="biz")
        assert mirror.customer_id == biz.id

    def test_subscribe_unknown_plan_returns_404(self):
        self._make_customer("biz")
        resp = self._post("/api/v1/platform/customers/biz/subscribe",
                          {"plan_key": "nope", "seats": 1})
        assert resp.status_code in (404, 422)

    def test_subscribe_unknown_customer_returns_404(self):
        self._make_plan()
        resp = self._post("/api/v1/platform/customers/ghost/subscribe",
                          {"plan_key": "pro", "seats": 1})
        assert resp.status_code == 404

    def test_subscribe_not_charge_ready_returns_422(self):
        # tenant without a connected account / charges_enabled -> OrchestrationError
        t2 = Tenant.objects.create(name="Poor", products=["metering"])
        _, raw2 = TenantApiKey.create_key(t2)
        TenantBillingPlan.objects.create(tenant=t2, key="pro", name="Pro",
                                         access_fee_micros=50_000_000)
        Customer.objects.create(tenant=t2, external_id="biz2")
        resp = self.client.post(
            "/api/v1/platform/customers/biz2/subscribe",
            data={"plan_key": "pro", "seats": 1},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw2}",
        )
        assert resp.status_code == 422

    # ---- POST /customers/{external_id}/seats ----

    def test_set_seats(self):
        self._make_plan()
        biz = self._make_customer("biz")
        with self._mock_stripe_subscribe():
            self._post("/api/v1/platform/customers/biz/subscribe",
                       {"plan_key": "pro", "seats": 10})
        with patch("apps.subscriptions.orchestration.service.stripe.SubscriptionItem.modify"):
            resp = self._post("/api/v1/platform/customers/biz/seats", {"seats": 12})
        assert resp.status_code == 200
        assert resp.json()["seats"] == 12
        item = CustomerSubscriptionItem.objects.get(customer=biz, axis="seat")
        assert item.quantity == 12

    def test_set_seats_no_subscription_returns_404(self):
        self._make_plan()
        self._make_customer("biz")
        resp = self._post("/api/v1/platform/customers/biz/seats", {"seats": 5})
        assert resp.status_code == 404
