import json

import pytest
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate
from apps.metering.pricing.services.pricing_service import PricingError
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService


@pytest.mark.django_db
class TestRecordUsagePricing:
    def test_backward_compat_caller_cost_unchanged(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=4_000)
        assert r["provider_cost_micros"] == 4_000 and r["billed_cost_micros"] == 4_000

    def test_priced_from_cost_card_when_no_caller_cost(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            metric_name="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=None,
            provider="openai", event_type="chat", usage_metrics={"input_tokens": 1000})
        assert r["provider_cost_micros"] == 5 and r["billed_cost_micros"] == 5
        e = UsageEvent.objects.get(id=r["event_id"])
        assert e.usage_metrics == {"input_tokens": 1000}
        assert e.pricing_provenance["cost_source"] == "rate_card"


# ---- F2.4: strict coverage — units-only events ----

@pytest.mark.django_db
class TestStrictCoverageUnitsOnly:
    """Endpoint-level tests for the units-only strict-mode gate."""

    def _setup(self, strict=False, products=None):
        t = Tenant.objects.create(
            name="StrictT",
            products=products or ["metering"],
            require_cost_card_coverage=strict,
        )
        key_obj, raw_key = TenantApiKey.create_key(t, label="test")
        c = Customer.objects.create(tenant=t, external_id="cust1")
        http = Client()
        auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
        return t, c, http, auth

    def _post(self, http, auth, customer, payload):
        body = {"customer_id": str(customer.id), **payload}
        return http.post(
            "/api/v1/metering/usage",
            data=json.dumps(body),
            content_type="application/json",
            **auth,
        )

    def test_strict_on_units_no_metrics_returns_422(self):
        """strict ON + units=5, no usage_metrics, no provider_cost_micros → 422 pricing_error."""
        t, c, http, auth = self._setup(strict=True)
        resp = self._post(http, auth, c, {
            "request_id": "r1", "idempotency_key": "ik1",
            "units": 5,
        })
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "pricing_error"
        assert "strict cost coverage" in body["detail"]

    def test_strict_off_units_no_metrics_returns_200_zero_cost(self):
        """strict OFF + same payload → 200 with provider_cost_micros=0 (old behavior)."""
        t, c, http, auth = self._setup(strict=False)
        resp = self._post(http, auth, c, {
            "request_id": "r2", "idempotency_key": "ik2",
            "units": 5,
        })
        assert resp.status_code == 200
        assert resp.json()["provider_cost_micros"] == 0

    def test_strict_on_units_with_provider_cost_returns_200(self):
        """strict ON + units=5 + provider_cost_micros=123 → 200 (cost is known)."""
        t, c, http, auth = self._setup(strict=True)
        resp = self._post(http, auth, c, {
            "request_id": "r3", "idempotency_key": "ik3",
            "units": 5, "provider_cost_micros": 123,
        })
        assert resp.status_code == 200
        assert resp.json()["provider_cost_micros"] == 123

    def test_strict_on_zero_units_no_metrics_returns_200(self):
        """strict ON + units=0, no metrics → marker event accepted."""
        t, c, http, auth = self._setup(strict=True)
        resp = self._post(http, auth, c, {
            "request_id": "r4", "idempotency_key": "ik4",
            "units": 0,
        })
        assert resp.status_code == 200

    def test_strict_on_null_units_no_metrics_returns_200(self):
        """strict ON + units omitted, no metrics → marker event accepted."""
        t, c, http, auth = self._setup(strict=True)
        resp = self._post(http, auth, c, {
            "request_id": "r5", "idempotency_key": "ik5",
        })
        assert resp.status_code == 200

    def test_strict_uncovered_metric_still_422_via_existing_gate(self):
        """Regression: strict + usage_metrics with uncovered metric → 422 (existing gate)."""
        t, c, http, auth = self._setup(strict=True)
        # Add a cost card for the tenant so we can enable strict mode, but use a
        # different metric in the event so it's still uncovered.
        Rate.objects.create(tenant=t, card_type="cost", provider="", event_type="",
            metric_name="dummy_covered", rate_per_unit_micros=1, unit_quantity=1)
        resp = self._post(http, auth, c, {
            "request_id": "r6", "idempotency_key": "ik6",
            "usage_metrics": {"uncovered_metric": 5},
        })
        assert resp.status_code == 422
        assert resp.json()["error"] == "pricing_error"

    def test_strict_422_fires_before_usageevent_creation_idempotency_retry_succeeds(self):
        """F2.4 idempotency: strict 422 fires before UsageEvent row exists.
        A corrected retry with the same idempotency_key must succeed (no row to replay).
        """
        t, c, http, auth = self._setup(strict=True)
        # First attempt: units=5, no metrics → 422, no row created.
        resp1 = self._post(http, auth, c, {
            "request_id": "r7", "idempotency_key": "ik7",
            "units": 5,
        })
        assert resp1.status_code == 422
        assert not UsageEvent.objects.filter(
            tenant=t, customer=c, idempotency_key="ik7").exists(), (
            "UsageEvent must NOT exist after a strict-mode 422")

        # Corrected retry with SAME idempotency_key: provide provider_cost_micros.
        resp2 = self._post(http, auth, c, {
            "request_id": "r7", "idempotency_key": "ik7",
            "units": 5, "provider_cost_micros": 500,
        })
        assert resp2.status_code == 200, (
            f"Corrected retry must succeed (got {resp2.status_code}): {resp2.json()}")
        assert resp2.json()["provider_cost_micros"] == 500
        assert UsageEvent.objects.filter(
            tenant=t, customer=c, idempotency_key="ik7").count() == 1
