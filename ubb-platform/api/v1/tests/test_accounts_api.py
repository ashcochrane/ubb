import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.mark.django_db
class TestAccountsAPI:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="BizTest",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_biz",
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def _post(self, data):
        return self.client.post(
            "/api/v1/platform/customers",
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def _get(self, path):
        return self.client.get(
            path,
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def test_create_business(self):
        resp = self._post(
            {"external_id": "biz", "account_type": "business", "billing_topology": "pooled"}
        )
        assert resp.status_code == 201
        assert resp.json()["external_id"] == "biz"

    def test_create_seat(self):
        # first create the parent business
        self._post(
            {"external_id": "biz", "account_type": "business", "billing_topology": "pooled"}
        )
        resp = self._post(
            {"external_id": "s1", "account_type": "seat", "parent_external_id": "biz"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["external_id"] == "s1"

        from apps.platform.customers.models import Customer
        biz = Customer.objects.get(tenant=self.tenant, external_id="biz")
        seat = Customer.objects.get(tenant=self.tenant, external_id="s1")
        assert seat.parent_id == biz.id

    def test_create_seat_triggers_roster_sync(self):
        # The endpoint, not just the model layer, must push the seat-quantity
        # sync — the lazy import inside create_customer is the wire-up under test.
        from unittest.mock import patch

        self._post(
            {"external_id": "biz", "account_type": "business", "billing_topology": "pooled"}
        )
        with patch(
            "apps.subscriptions.orchestration.seats.sync_seat_quantity_on_commit"
        ) as spy:
            resp = self._post(
                {"external_id": "s2", "account_type": "seat", "parent_external_id": "biz"}
            )
        assert resp.status_code == 201
        spy.assert_called_once()
        from apps.platform.customers.models import Customer
        biz = Customer.objects.get(tenant=self.tenant, external_id="biz")
        assert spy.call_args.args[0].id == biz.id

    def test_create_seat_without_parent_returns_422(self):
        resp = self._post({"external_id": "orphan", "account_type": "seat"})
        assert resp.status_code == 422

    def test_create_individual_backward_compat(self):
        resp = self._post({"external_id": "ind"})
        assert resp.status_code == 201
        assert resp.json()["external_id"] == "ind"

        from apps.platform.customers.models import Customer
        cust = Customer.objects.get(tenant=self.tenant, external_id="ind")
        assert cust.account_type == "individual"

    def test_get_business_view(self):
        # create biz
        self._post(
            {"external_id": "biz", "account_type": "business", "billing_topology": "pooled"}
        )
        # create seat under biz
        self._post(
            {"external_id": "s1", "account_type": "seat", "parent_external_id": "biz"}
        )

        resp = self._get("/api/v1/platform/accounts/business/biz")
        assert resp.status_code == 200
        data = resp.json()
        seat_ids = [s["external_id"] for s in data["seats"]]
        assert "s1" in seat_ids
        assert "pooled_balance_micros" in data
