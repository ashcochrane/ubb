import json

import pytest
from django.test import Client
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
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
class TestTheRecordingRouteAcceptsWhatItCannotCost:
    """Endpoint-level: what the route does with a quantity it has no rate for.

    F2.4's SECOND REFUSAL RETIRED WITH ITS INPUT (#272). It rejected an event
    that declared a nameless magnitude with no quantity name to resolve a rate
    card against; that magnitude was the posting's inline unit total, and a
    caller can no longer state it at all. The refusal is therefore unexpressible
    rather than relaxed, and the four cases that drove it are gone.

    **THE OTHER REFUSAL WENT IN #320, AND IT WENT ON PURPOSE.** An event naming
    a quantity UBB cannot cost used to be answered 422 with no row created. The
    supplier had already run that call and already charged for it, so the
    refusal did not undo the spend — it threw away the record of it. The event
    is now recorded with its cost unresolved, which turns the two cases below
    inside out: the 422 becomes a 200 that says what is missing, and the
    idempotency case that used to prove *no row existed to replay* now proves
    the opposite, which is the more useful fact. A caller cannot correct an
    uncosted posting by re-posting it; the cost settles through one door.

    The tenant setting that made the refusal conditional stopped being read on
    this path here, and is not set below. It outlived this commit by one: its
    last read was the admission gate in
    `billing/gating/services/risk_service.py`, refusing to start a
    COGS-limited unit without it, and #321 deleted the column, that gate and
    its refusal code together.
    """

    def _setup(self, products=None):
        t = Tenant.objects.create(
            name="StrictT",
            products=products or ["metering"],
        )
        key_obj, raw_key = TenantApiKey.create_key(t, label="test")
        c = Customer.objects.create(tenant=t, external_id="cust1")
        # The two bodies below that state the supplier's own cost need the
        # Event Type that declares it arrives on the call (#324); the rest of
        # this class never names it.
        declares_a_caller_supplied_cost(t, DECLARED)
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

    def test_nothing_to_price_is_a_marker_event(self):
        """No quantities, no caller cost → 200, a marker event at a real zero."""
        t, c, http, auth = self._setup()
        resp = self._post(http, auth, c, {
            "request_id": "r5", "idempotency_key": "ik5",
        })
        assert resp.status_code == 200
        assert resp.json()["provider_cost_micros"] == 0
        assert resp.json()["costing_status"] == "known"

    def test_caller_cost_with_no_metrics_returns_200(self):
        """A supplied provider_cost_micros → 200; cost is explicitly known."""
        t, c, http, auth = self._setup()
        resp = self._post(http, auth, c, {
            "request_id": "r3", "idempotency_key": "ik3",
            "event_type": DECLARED, "provider_cost_micros": 123,
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
        t, c, http, auth = self._setup()
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

        A tenant with no cards at all would be a weaker subject than one whose
        cards simply miss. Both tests below need exactly this, and they need it
        identical — a second card written slightly differently is how a
        regression test quietly stops testing the regression.
        """
        return Rate.objects.create(
            tenant=tenant, card_type="cost", provider="", event_type="",
            measurement=declares_a_quantity(tenant, "dummy_covered"),
            rate_per_unit_micros=1, unit_quantity=1)

    def test_an_uncosted_quantity_is_recorded_and_the_body_says_so(self):
        """The inversion of the refusal (#320), at the route.

        The tenant has cost cards; they just do not cover this quantity. The
        call is answered 200, the row exists, and the body carries both halves
        of the answer — that the cost is unresolved, and which declaration to
        fix.
        """
        t, c, http, auth = self._setup()
        self._card_for_some_other_measurement(t)
        resp = self._post(http, auth, c, {
            "request_id": "r6", "idempotency_key": "ik6",
            "measurements": {"uncovered_metric": 5},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider_cost_micros"] is None
        assert body["costing_status"] == "unresolved"
        assert body["uncosted_measurement_keys"] == ["uncovered_metric"]
        assert Posting.objects.filter(
            tenant=t, customer=c, idempotency_key="ik6").count() == 1

    def test_an_uncosted_posting_cannot_be_corrected_by_re_posting_it(self):
        """The idempotency half, inverted — and the more useful fact (#320).

        This test used to prove that a refused event left NO row to replay, so
        the same idempotency key could be reused with a corrected payload. Now
        the row exists, so the key is spent: a second call with a supplied cost
        is a REPLAY and returns the original posting, unresolved and unchanged.

        That is the answer #146 §15 was worried about from the other end. Its
        highest-rated residue was an idempotency unwind on the accept-time
        pricing wrapper — what should happen to a half-recorded event when
        pricing refused. **CONFIRMED ABSENT BY LOOKING, NOT INHERITED:** that
        wrapper was `usage/services/ingest_accept.py`, deleted with the whole
        async accept pipeline in slice 1 (`2ad0bbe`, #237); the services package
        now holds only `usage_service.py` and `stop_context.py`, and the single
        surviving mention of the name in this repository is a comment in
        `api/v1/tests/test_one_rule_pins.py` recording that its list shrank
        rather than substituted. So there is no unwind to write on either count:
        no second recording path, and nothing left to unwind on the one that
        remains. A caller who wants the cost filled in is asking for a
        settlement, which moves the amount and the status together, exactly once
        (`pricing/services/cost_settlement.py`).
        """
        t, c, http, auth = self._setup()
        self._card_for_some_other_measurement(t)
        resp1 = self._post(http, auth, c, {
            "request_id": "r7", "idempotency_key": "ik7",
            "measurements": {"uncovered_metric": 5},
        })
        assert resp1.status_code == 200
        assert resp1.json()["costing_status"] == "unresolved"

        resp2 = self._post(http, auth, c, {
            "request_id": "r7", "idempotency_key": "ik7",
            "event_type": DECLARED, "provider_cost_micros": 500,
        })

        assert resp2.status_code == 200
        assert resp2.json()["event_id"] == resp1.json()["event_id"]
        assert resp2.json()["provider_cost_micros"] is None
        assert resp2.json()["costing_status"] == "unresolved"
        assert Posting.objects.filter(
            tenant=t, customer=c, idempotency_key="ik7").count() == 1
