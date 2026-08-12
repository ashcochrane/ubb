"""Fix 1: negative measurements values must be rejected.

Pydantic schema validator on RecordUsageRequest — endpoint returns 422,
unconditionally (any card shape, strict mode or not).

BOTH HALVES OF THE RULE LIVE HERE (#274). The bag was renamed to the canonical
measurement vocabulary and this validator moved with it *unchanged*, which is a
claim with two sides: what it refuses, and what it still lets through. The first
class below is the refusal. The second is the other side — the three things a
caller may still send that a reader of the rename might reasonably assume it
started refusing, and does not. Slice 3 owns every behaviour a declaration
selects; until then an unmatched quantity is accepted here and contributes
nothing downstream, and that is a decision rather than an omission.
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
    """Endpoint returns 422 for any negative measurements value."""

    def test_negative_quantity_returns_422(self):
        """Schema rejects the negative quantity before pricing runs."""
        tenant, customer, http, auth = _setup_http()
        Rate.objects.create(
            tenant=tenant, card_type="price", measurement_key="calls",
            pricing_model="per_unit", rate_per_unit_micros=10, unit_quantity=1,
        )
        resp = _post(http, auth, customer, {
            "request_id": "r1", "idempotency_key": "k1",
            "measurements": {"calls": -5},
        })
        assert resp.status_code == 422

    def test_negative_quantity_strict_mode_returns_422(self):
        """Strict mode does not change the rejection — negative is always invalid."""
        tenant = Tenant.objects.create(
            name="Strict", products=["metering"], require_cost_card_coverage=True)
        _, raw_key = TenantApiKey.create_key(tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        Rate.objects.create(
            tenant=tenant, card_type="cost", measurement_key="tok",
            pricing_model="per_unit", rate_per_unit_micros=1, unit_quantity=1,
        )
        http = Client()
        auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
        resp = _post(http, auth, customer, {
            "request_id": "r3", "idempotency_key": "k3",
            "measurements": {"tok": -100},
        })
        assert resp.status_code == 422

    def test_zero_quantity_accepted(self):
        """Zero is valid (boundary check — ge=0)."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r4", "idempotency_key": "k4",
            "measurements": {"calls": 0},
        })
        assert resp.status_code == 200

    def test_positive_quantity_accepted(self):
        """Positive value passes validation."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r5", "idempotency_key": "k5",
            "measurements": {"calls": 1},
        })
        assert resp.status_code == 200

    def test_one_negative_among_many_quantities_returns_422(self):
        """Even if only one quantity is negative the whole request is rejected."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r6", "idempotency_key": "k6",
            "measurements": {"good": 10, "bad": -1},
        })
        assert resp.status_code == 422


@pytest.mark.django_db
class TestTheRenameTightenedNothing:
    """What the bag still accepts, stated so the rename cannot be misread (#274).

    The field is now named for the declarations its keys are keys into, and the
    obvious inference from that name is that an undeclared key stops being
    allowed. It does not. Naming the field made the mismatch DESCRIBABLE; slice 3
    is what makes it visible, and every case below is the interim behaviour it
    will change.

    These are the boundary, not the design: each one is here because a reader of
    the rename could reasonably believe it had already moved.
    """

    def test_a_key_no_declaration_matches_is_still_accepted(self):
        """The silent-and-free case, unchanged and now under a truer name.

        No declaration exists for this key and none is consulted; the request
        is accepted and the quantity contributes nothing to either amount.
        `test_record_usage_pricing.py` carries the money side of the same fact.
        """
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r7", "idempotency_key": "k7",
            "measurements": {"nothing_declares_this": 5000},
        })
        assert resp.status_code == 200
        assert resp.json()["provider_cost_micros"] == 0

    def test_a_key_of_any_shape_is_still_accepted(self):
        """No key pattern arrived with the name.

        Mixed case, a hyphen, a space and a single character: the neighbouring
        bag had a lowercase-snake rule and #273 established that such a rule is
        a grouping constraint wearing a validation hat. None was imposed here.
        """
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r8", "idempotency_key": "k8",
            "measurements": {"Input-Tokens": 1, "cost centre": 2, "x": 3},
        })
        assert resp.status_code == 200

    def test_an_absent_bag_is_still_accepted(self):
        """A posting may still measure nothing at all. Absence is not a refusal."""
        tenant, customer, http, auth = _setup_http()
        resp = _post(http, auth, customer, {
            "request_id": "r9", "idempotency_key": "k9",
            "provider_cost_micros": 4_000,
        })
        assert resp.status_code == 200
