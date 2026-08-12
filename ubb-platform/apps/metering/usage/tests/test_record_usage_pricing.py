import json

import pytest
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.tests.test_the_measured_quantities_take_the_canonical_name import (  # noqa: E501
    RETIRED_COLUMN)


@pytest.mark.django_db
class TestRecordUsagePricing:
    def test_backward_compat_caller_cost_unchanged(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=4_000)
        assert r["provider_cost_micros"] == 4_000 and r["billed_cost_micros"] == 4_000

    def test_priced_from_cost_card_when_no_caller_cost(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            measurement_key="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=None,
            provider="openai", event_type="chat", measurements={"input_tokens": 1000})
        assert r["provider_cost_micros"] == 5 and r["billed_cost_micros"] == 5
        e = Posting.objects.get(id=r["event_id"])
        assert e.measurements == {"input_tokens": 1000}
        assert e.pricing_provenance["cost_source"] == "rate_card"

    def test_a_stale_callers_quantities_are_dropped_and_it_is_priced_at_zero(self):
        """WHAT THE #274 RENAME COSTS A CALLER THAT HAS NOT MIGRATED.

        The request schema ignores an unknown key rather than refusing it, so a
        caller still sending the retired name is accepted — and this is the case
        where that is not cosmetic. Everything this engine prices from lives in
        that bag, so the same request that costs 5 above costs **nothing** here,
        silently, with a 200 and a posting to show for it.

        The 200 is `test_the_measured_quantities_take_the_canonical_name.py`'s;
        what is added here is the number, against a real cost card, because
        "labels are lost" and "the invoice is wrong" are different sizes of
        consequence and only one of them is this one.
        """
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        rate_in_default_book(t, card_type="cost", provider="openai", event_type="chat",
            measurement_key="input_tokens", rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        http = Client()
        _, raw_key = TenantApiKey.create_key(t, label="test")
        resp = http.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(c.id), "request_id": "r_stale",
                "idempotency_key": "i_stale", "provider": "openai",
                "event_type": "chat",
                RETIRED_COLUMN: {"input_tokens": 1000},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")

        assert resp.status_code == 200
        assert resp.json()["provider_cost_micros"] == 0
        e = Posting.objects.get(idempotency_key="i_stale")
        assert e.measurements == {}


# ---- Strict coverage at the door ----

@pytest.mark.django_db
class TestStrictCoverage:
    """Endpoint-level tests for strict cost-card coverage.

    F2.4's SECOND REFUSAL RETIRED WITH ITS INPUT (#272). It rejected an event
    that declared a nameless magnitude with no quantity name to resolve a rate
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

    def test_a_stale_client_still_sending_the_retired_field_is_accepted(self):
        """WHAT THE RETIREMENT COSTS A CALLER THAT HAS NOT MIGRATED (#272).

        The request schema ignores unknown fields, so a client still posting the
        retired inline total is not rejected — the field is dropped and the
        event records as the marker it now is. Under strict coverage that same
        payload used to be a 422, so a loud refusal became a quiet accept for
        exactly one population: stale callers.

        Pinned rather than left in a comment, because it is the whole migration
        story for anyone reading the reviewed break on the request side. Nothing
        is mis-metered — there was never anything to multiply that number by.
        """
        t, c, http, auth = self._setup(strict=True)
        resp = self._post(http, auth, c, {
            "request_id": "r8", "idempotency_key": "ik8", "units": 5,
        })

        assert resp.status_code == 200
        assert resp.json()["provider_cost_micros"] == 0
        assert "units" not in resp.json()
        posting = Posting.objects.get(tenant=t, customer=c, idempotency_key="ik8")
        assert not hasattr(posting, "units")

    def _card_for_some_other_measurement(self, tenant):
        """A cost card the tenant HAS, for a key the event will not name.

        Strict mode is about coverage, so a tenant with no cards at all would be
        a weaker subject than one whose cards simply miss. Both refusal tests
        below need exactly this, and they need it identical — a second card
        written slightly differently is how a regression test quietly stops
        testing the regression.
        """
        return Rate.objects.create(
            tenant=tenant, card_type="cost", provider="", event_type="",
            measurement_key="dummy_covered", rate_per_unit_micros=1, unit_quantity=1)

    def test_strict_uncovered_metric_still_422_via_existing_gate(self):
        """Regression: strict + measurements with an uncovered quantity → 422 (existing gate)."""
        t, c, http, auth = self._setup(strict=True)
        self._card_for_some_other_measurement(t)
        resp = self._post(http, auth, c, {
            "request_id": "r6", "idempotency_key": "ik6",
            "measurements": {"uncovered_metric": 5},
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "pricing_error"

    def test_strict_422_fires_before_posting_creation_idempotency_retry_succeeds(self):
        """F2.4 idempotency: a strict 422 fires before the Posting row exists.
        A corrected retry with the same idempotency_key must succeed (no row to
        replay). Driven off the refusal that survives #272 — an uncosted quantity
        — because the one it was written against no longer has an input.
        """
        t, c, http, auth = self._setup(strict=True)
        self._card_for_some_other_measurement(t)
        # First attempt: a quantity with no cost card → 422, no row created.
        resp1 = self._post(http, auth, c, {
            "request_id": "r7", "idempotency_key": "ik7",
            "measurements": {"uncovered_metric": 5},
        })
        assert resp1.status_code == 422
        assert not Posting.objects.filter(
            tenant=t, customer=c, idempotency_key="ik7").exists(), (
            "Posting must NOT exist after a strict-mode 422")

        # Corrected retry with SAME idempotency_key: state the cost outright
        # instead of naming a quantity UBB has no card for. (Supplying the cost
        # AND keeping the uncosted quantity would still be refused — the caller-
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
