"""Fix 1: negative usage_metrics values must be rejected.

Pydantic schema validator on RecordUsageRequest — endpoint returns 422,
unconditionally (any card shape, strict mode or not).
"""
import json

import pytest
from django.test import Client

from apps.metering.pricing.models import Rate
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey


def _setup_http():
    tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
    _, raw_key = TenantApiKey.create_key(tenant, label="test")
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    http = Client()
    auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
    return tenant, customer, http, auth


def _post(http, auth, customer, payload):
    body = {"customer_id": str(customer.id), **payload}
    return http.post(
        "/api/v1/metering/usage",
        data=json.dumps(body),
        content_type="application/json",
        **auth,
    )


@pytest.mark.django_db
class TestNegativeMetricSchemaRejection:
    """Endpoint returns 422 for any negative usage_metrics value."""

    def test_negative_metric_returns_422(self):
        """Schema rejects the negative metric before pricing runs."""
        tenant, customer, http, auth = _setup_http()
        Rate.objects.create(
            tenant=tenant, card_type="price", metric_name="calls",
            pricing_model="per_unit", rate_per_unit_micros=10, unit_quantity=1,
        )
        resp = _post(http, auth, customer, {
            "request_id": "r1", "idempotency_key": "k1",
            "usage_metrics": {"calls": -5},
        })
        assert resp.status_code == 422

    def test_negative_metric_strict_mode_returns_422(self):
        """Strict mode does not change the rejection — negative is always invalid."""
        tenant = Tenant.objects.create(
            name="Strict", products=["metering"], require_cost_card_coverage=True)
        _, raw_key = TenantApiKey.create_key(tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        Rate.objects.create(
            tenant=tenant, card_type="cost", metric_name="tok",
            pricing_model="per_unit", rate_per_unit_micros=1, unit_quantity=1,
        )
        http = Client()
        auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
        resp = _post(http, auth, customer, {
            "request_id": "r3", "idempotency_key": "k3",
            "usage_metrics": {"tok": -100},
        })
        assert resp.status_code == 422

    def test_zero_metric_accepted(self):
        """Zero is valid (boundary check — ge=0)."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r4", "idempotency_key": "k4",
            "usage_metrics": {"calls": 0},
        })
        assert resp.status_code == 200

    def test_positive_metric_accepted(self):
        """Positive value passes validation."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r5", "idempotency_key": "k5",
            "usage_metrics": {"calls": 1},
        })
        assert resp.status_code == 200

    def test_one_negative_among_many_metrics_returns_422(self):
        """Even if only one metric is negative the whole request is rejected."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r6", "idempotency_key": "k6",
            "usage_metrics": {"good": 10, "bad": -1},
        })
        assert resp.status_code == 422
