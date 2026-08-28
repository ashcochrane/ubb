"""Fix 1: negative measurements values must be rejected.

Pydantic schema validator on RecordUsageRequest — endpoint returns 422,
unconditionally (any card shape, strict mode or not).

BOTH HALVES OF THE RULE LIVE HERE (#274). The bag was renamed to the canonical
measurement vocabulary and this validator moved with it *unchanged*, which is a
claim with two sides: what it refuses, and what it still lets through. The first
class below is the refusal. The second is the other side — the three things a
caller may still send that a reader of the rename might reasonably assume it
started refusing, and does not.

Slice 3 arrived for one of those three (#320). An unmatched quantity is still
ACCEPTED — that is the half this class is about and it has not moved — and it
has stopped contributing a silent zero: the posting now says its cost is
unresolved and names the missing rate. Refusing a *rate* that names a quantity
nobody declared is #326's, and refusing the quantity itself is nobody's.
"""
import json

import pytest
from django.test import Client

from apps.metering.pricing.models import Rate
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import declares_a_quantity
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
    """Endpoint returns 422 for any negative measurements value."""

    def test_negative_quantity_returns_422(self):
        """Schema rejects the negative quantity before pricing runs."""
        tenant, customer, http, auth = _setup_http()
        Rate.objects.create(
            tenant=tenant,
            measurement=declares_a_quantity(tenant, "calls"),
            rate_structure="per_unit", rate_per_unit_micros=10, unit_quantity=1,
        )
        resp = _post(http, auth, customer, {
            "idempotency_key": "k1",
            "measurements": {"calls": -5},
        })
        assert resp.status_code == 422

    def test_the_refusal_reaches_the_CALLER_and_names_the_quantity(self):
        """A status code alone does not tell an integrator what to fix (#324).

        The validator has always said which keys were negative; whether that
        sentence reaches the wire is a property of the problem renderer, not of
        the validator, and nothing asserted it. `problems.py` puts pydantic's
        per-error dicts on the body as `errors[]`, so dropping `msg` from that
        projection — a plausible tidy-up, since it is the noisiest of the three
        keys — would leave every status assertion in this module green and take
        the diagnosis away.

        A defect upstream of UBB must not become a negative cost inside it, and
        the caller is the only party who can fix the defect.
        """
        tenant, customer, http, auth = _setup_http()

        resp = _post(http, auth, customer, {
            "idempotency_key": "k2",
            "measurements": {"calls": -5, "fine": 1},
        })

        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "validation_error"
        messages = " ".join(error.get("msg", "") for error in body["errors"])
        assert "calls" in messages, body
        assert "fine" not in messages, body

    # A second case here drove the same rejection with the strict cost-coverage
    # flag on. #320 stopped that flag reaching costing, which made it a
    # duplicate of the case above rather than a second mode of the rule, and
    # #321 deleted the flag: the case goes with it rather than being renamed.
    # The predicate is a request validator (`api/v1/schemas.py`,
    # `measurement_values_nonnegative`) and never consulted the tenant.

    def test_zero_quantity_accepted(self):
        """Zero is valid (boundary check — ge=0)."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "idempotency_key": "k4",
            "measurements": {"calls": 0},
        })
        assert resp.status_code == 200

    def test_positive_quantity_accepted(self):
        """Positive value passes validation."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "idempotency_key": "k5",
            "measurements": {"calls": 1},
        })
        assert resp.status_code == 200

    def test_one_negative_among_many_quantities_returns_422(self):
        """Even if only one quantity is negative the whole request is rejected."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "idempotency_key": "k6",
            "measurements": {"good": 10, "bad": -1},
        })
        assert resp.status_code == 422


@pytest.mark.django_db
class TestTheRenameTightenedNothing:
    """What the bag still accepts, stated so the rename cannot be misread (#274).

    The field is now named for the declarations its keys are keys into, and the
    obvious inference from that name is that an undeclared key stops being
    allowed. It does not — not before slice 3 and not after it. Naming the field
    made the mismatch DESCRIBABLE and #320 made it VISIBLE: the first case below
    now records an unresolved cost where it used to record a zero, and what none
    of the three has become is refused.

    These are the boundary, not the design: each one is here because a reader of
    the rename could reasonably believe it had already moved.
    """

    def test_a_key_no_declaration_matches_is_still_accepted(self):
        """Still accepted — and it has STOPPED BEING FREE (#320).

        This test was written as the interim case: the quantity was accepted
        and contributed a silent zero to the supplier cost. The acceptance is
        the half that survives and is what this class is about; the zero is the
        half slice 3 came for. A quantity nothing costed now leaves the posting
        saying so — no amount, and a reason naming the missing rate — which is
        the *only* change here. The request is not refused, and #326 is where
        refusing a rate that names an undeclared quantity lands.

        Rewritten rather than relaxed: dropping the amount assertion would have
        left the class asserting a 200 that was never in doubt.
        """
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "idempotency_key": "k7",
            "measurements": {"nothing_declares_this": 5000},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider_cost_micros"] is None
        assert body["costing_status"] == "unresolved"
        assert body["uncosted_measurement_keys"] == ["nothing_declares_this"]

    def test_a_key_of_any_shape_is_still_accepted(self):
        """No key pattern arrived with the name.

        Mixed case, a hyphen, a space and a single character: the neighbouring
        bag had a lowercase-snake rule and #273 established that such a rule is
        a grouping constraint wearing a validation hat. None was imposed here.
        """
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "idempotency_key": "k8",
            "measurements": {"Input-Tokens": 1, "cost centre": 2, "x": 3},
        })
        assert resp.status_code == 200

    def test_an_absent_bag_is_still_accepted(self):
        """A posting may still measure nothing at all. Absence is not a refusal.

        The supplier cost this case used to carry went with #324, which made
        stating it admissible only against a declaring Event Type — incidental
        here, and a declaration would have put the subject of the test at one
        remove from the thing it asserts.
        """
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "idempotency_key": "k9",
        })
        assert resp.status_code == 200
