"""#103 pins: doc-legal scalars that violate a storage constraint answer
422 ``validation_error``, never 500.

The committed document types these fields loosely (unbounded ``integer``,
open ``string``), so values the contract accepts can still violate a
database constraint — NUL bytes in text, int4 overflow, varchar overflow —
and surface as the driver's ``django.db.utils.DataError``. One central
mapping in ``api/v1/problems.py`` answers the whole family, including
future fields, as 422 (the caller's value is the problem, not a server
fault). Only ``DataError`` takes that lane: every other database error
(integrity, operational, …) keeps the 500 ``internal_error`` lane.

The body carries a stable sanitized detail — the driver's own message can
name column types or echo input, so it never reaches the wire. The
committed OpenAPI document does not change (422 is a dialect-wide
out-of-band status; ``test_openapi_contract.py`` pins drift).
"""
import json

from django.db import DatabaseError, DataError, IntegrityError, OperationalError
from django.test import Client, RequestFactory, TestCase

from api.v1.tests.test_problem_contract import assert_problem
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey

# The wire detail for the whole family (pinned literally: it is contract
# surface, not an implementation symbol).
DATA_ERROR_DETAIL = (
    "A value in the request cannot be stored: it is out of range, "
    "too long, or contains unsupported characters."
)


class DataErrorPinBase(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="DataErrorPins",
            products=["metering", "billing", "subscriptions", "referrals"],
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _request(self, method, url, payload):
        return self.http_client.generic(
            method, url, data=json.dumps(payload),
            content_type="application/json", **self.auth,
        )

    def assert_data_error_problem(self, response):
        body = assert_problem(self, response, "validation_error")
        self.assertEqual(body["detail"], DATA_ERROR_DETAIL)
        return body


class NulByteTest(DataErrorPinBase):
    """Shape 1 — NUL (0x00) bytes in doc-legal strings: psycopg refuses
    text containing NUL client-side (the sweep's customer-create and
    postpaid-config repros)."""

    def test_nul_byte_in_customer_external_id_is_a_422_problem(self):
        response = self._request(
            "POST", "/api/v1/platform/customers", {"external_id": "x\x00y"}
        )
        self.assert_data_error_problem(response)
        # The write rolled back with the transaction — nothing half-created.
        self.assertFalse(Customer.objects.filter(tenant=self.tenant).exists())

    def test_nul_byte_in_postpaid_config_is_a_422_problem(self):
        response = self._request(
            "PUT", "/api/v1/billing/postpaid-config",
            {"usage_line_item_group_by": "x\x00y"},
        )
        self.assert_data_error_problem(response)


class IntegerOverflowTest(DataErrorPinBase):
    """Shape 2 — a doc-legal (unbounded) integer overflowing an int4
    column: the sweep's margin-threshold repro, its exact value."""

    def test_int4_overflow_in_margin_threshold_is_a_422_problem(self):
        response = self._request(
            "PUT", "/api/v1/margin/threshold",
            {"min_margin_pct": 5.0,
             "consecutive_periods": 2210830884174572288,
             "provider_cost_spike_pct": 25.0},
        )
        self.assert_data_error_problem(response)


class LengthOverflowTest(DataErrorPinBase):
    """Shape 3 — a doc-legal open string overflowing a varchar column:
    the sweep's plan-creation repro (``interval`` is varchar(5))."""

    def test_varchar_overflow_in_plan_interval_is_a_422_problem(self):
        response = self._request(
            "POST", "/api/v1/platform/plans",
            {"key": "pin-plan", "name": "Pin Plan", "interval": "quarterly"},
        )
        self.assert_data_error_problem(response)


class OnlyDataErrorTakesTheValidationLaneTest(TestCase):
    """The scope pin: the mapping catches ``DataError`` and nothing else —
    its DatabaseError siblings (and the bare parent) keep the 500 lane.
    Exercised at the dispatch seam (``api.on_exception`` resolves handlers
    by exception MRO) because sibling errors have no doc-legal HTTP repro.
    """

    def setUp(self):
        self.request = RequestFactory().post("/api/v1/platform/customers")

    def _dispatch(self, exc):
        from api.v1.api import api

        return api.on_exception(self.request, exc)

    def test_data_error_maps_to_422_validation_error(self):
        response = self._dispatch(DataError("integer out of range"))
        body = assert_problem(self, response, "validation_error")
        self.assertEqual(body["detail"], DATA_ERROR_DETAIL)

    def test_sibling_database_errors_stay_internal_error(self):
        for exc in (
            DatabaseError("boom"),
            IntegrityError("duplicate key"),
            OperationalError("connection lost"),
        ):
            with self.subTest(type(exc).__name__):
                response = self._dispatch(exc)
                assert_problem(self, response, "internal_error")

    def test_driver_message_never_reaches_the_body(self):
        # The driver's text can name column types ("character varying(5)")
        # or echo input — the wire body must carry only the stable detail.
        response = self._dispatch(
            DataError("value too long for type character varying(5)")
        )
        body = assert_problem(self, response, "validation_error")
        self.assertNotIn("character varying", json.dumps(body))
        self.assertEqual(body["detail"], DATA_ERROR_DETAIL)
