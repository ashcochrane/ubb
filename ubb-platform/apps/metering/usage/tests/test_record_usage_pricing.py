import json

import pytest
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import Posting
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
        e = Posting.objects.get(id=r["event_id"])
        assert e.usage_metrics == {"input_tokens": 1000}
        assert e.pricing_provenance["cost_source"] == "rate_card"


# ---- Strict coverage at the door ----

@pytest.mark.django_db
class TestStrictCoverage:
    """Endpoint-level tests for strict cost-card coverage.

    F2.4's SECOND REFUSAL RETIRED WITH ITS INPUT (#272). It rejected an event
    that declared a nameless magnitude with no metric name to resolve a rate
    card against; that magnitude was the posting's inline unit total, and a
    caller can no longer state it at all. The refusal is therefore unexpressible
    rather than relaxed, and the four cases that drove it are gone.

    What is asserted instead is the pair that decides whether anything was lost:
    an event with nothing to price is a marker and is accepted (which is what
    every such request already was, at zero or omitted), and an event that DOES
    name a quantity UBB cannot cost is refused exactly as before — before any
    row exists, and replayable under the same idempotency key.
    """

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

    def test_strict_on_nothing_to_price_is_a_marker_event(self):
        """strict ON, no quantities, no caller cost → 200, a marker event."""
        t, c, http, auth = self._setup(strict=True)
        resp = self._post(http, auth, c, {
            "request_id": "r5", "idempotency_key": "ik5",
        })
        assert resp.status_code == 200
        assert resp.json()["provider_cost_micros"] == 0

    def test_strict_on_caller_cost_with_no_metrics_returns_200(self):
        """strict ON + provider_cost_micros → 200; cost is explicitly known."""
        t, c, http, auth = self._setup(strict=True)
        resp = self._post(http, auth, c, {
            "request_id": "r3", "idempotency_key": "ik3",
            "provider_cost_micros": 123,
        })
        assert resp.status_code == 200
        assert resp.json()["provider_cost_micros"] == 123

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
        assert resp.json()["code"] == "pricing_error"

    def test_strict_422_fires_before_posting_creation_idempotency_retry_succeeds(self):
        """F2.4 idempotency: a strict 422 fires before the Posting row exists.
        A corrected retry with the same idempotency_key must succeed (no row to
        replay). Driven off the refusal that survives #272 — an uncosted metric
        — because the one it was written against no longer has an input.
        """
        t, c, http, auth = self._setup(strict=True)
        Rate.objects.create(tenant=t, card_type="cost", provider="", event_type="",
            metric_name="dummy_covered", rate_per_unit_micros=1, unit_quantity=1)
        # First attempt: a metric with no cost card → 422, no row created.
        resp1 = self._post(http, auth, c, {
            "request_id": "r7", "idempotency_key": "ik7",
            "usage_metrics": {"uncovered_metric": 5},
        })
        assert resp1.status_code == 422
        assert not Posting.objects.filter(
            tenant=t, customer=c, idempotency_key="ik7").exists(), (
            "Posting must NOT exist after a strict-mode 422")

        # Corrected retry with SAME idempotency_key: state the cost outright
        # instead of naming a quantity UBB has no card for. (Supplying the cost
        # AND keeping the uncosted metric would still be refused — the caller-
        # cost branch runs the same coverage check, deliberately.)
        resp2 = self._post(http, auth, c, {
            "request_id": "r7", "idempotency_key": "ik7",
            "provider_cost_micros": 500,
        })
        assert resp2.status_code == 200, (
            f"Corrected retry must succeed (got {resp2.status_code}): {resp2.json()}")
        assert resp2.json()["provider_cost_micros"] == 500
        assert Posting.objects.filter(
            tenant=t, customer=c, idempotency_key="ik7").count() == 1
