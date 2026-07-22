"""#102 pins: malformed UUID identifiers answer 4xx problems, never 500.

The guard is one shared seam — ``core/identifiers.py``'s ``UUIDIdentifier``
annotated type validates at the router boundary, and the central validation
handler (``api/v1/problems.py``) maps the failure by channel:

* **path** — a malformed UUID cannot name a resource, so it answers the same
  bare 404 ``not_found`` problem as a nonexistent one;
* **query / body** — invalid input, not a resource miss: 422
  ``validation_error`` with the usual sanitized error list.

These pins exercise the live surface per channel; the committed OpenAPI
document does not change (the type renders as a bare ``string``), which
``test_openapi_contract.py`` already pins.
"""
import json
import uuid

from django.test import Client, TestCase

from api.v1.tests.test_problem_contract import assert_problem
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey

# Every path-channel operation of the issue's 22 (19 of them; the other
# three are the two query ops below and the referrers body op), with a
# minimally valid body where the operation takes one — the 404 lane
# requires the malformed identifier to be the *only* boundary failure.
PATH_OPERATIONS = [
    ("PUT", "/api/v1/billing/customers/0/auto-top-up",
     {"is_enabled": False, "trigger_threshold_micros": 0,
      "top_up_amount_micros": 10_000}),
    ("GET", "/api/v1/billing/customers/0/balance", None),
    ("POST", "/api/v1/billing/customers/0/refund",
     {"usage_event_id": str(uuid.uuid4()), "idempotency_key": "k"}),
    ("POST", "/api/v1/billing/customers/0/top-up",
     {"amount_micros": 10_000, "success_url": "https://x/s",
      "cancel_url": "https://x/c", "idempotency_key": "k"}),
    ("GET", "/api/v1/billing/customers/0/transactions", None),
    ("POST", "/api/v1/billing/customers/0/withdraw",
     {"amount_micros": 10_000, "idempotency_key": "k"}),
    ("GET", "/api/v1/customers/0/past-limit-report", None),
    ("GET", "/api/v1/metering/customers/0/usage", None),
    ("DELETE", "/api/v1/referrals/referrals/0", None),
    ("GET", "/api/v1/referrals/referrals/0/ledger", None),
    ("GET", "/api/v1/referrals/referrers/0", None),
    ("GET", "/api/v1/referrals/referrers/0/earnings", None),
    ("GET", "/api/v1/referrals/referrers/0/referrals", None),
    ("GET", "/api/v1/subscriptions/customers/0/invoices", None),
    ("GET", "/api/v1/subscriptions/customers/0/subscription", None),
    ("DELETE", "/api/v1/webhooks/configs/0", None),
    ("PATCH", "/api/v1/webhooks/configs/0", {}),
    ("GET", "/api/v1/webhooks/configs/0/deliveries", None),
    ("POST", "/api/v1/webhooks/configs/0/rotate-secret",
     {"new_secret": "s" * 32}),
]

QUERY_OPERATIONS = [
    "/api/v1/metering/analytics/usage",
    "/api/v1/metering/analytics/usage/timeseries",
]


class UUIDIdentifierPinBase(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="UUIDPins",
            products=["metering", "billing", "subscriptions", "referrals"],
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}


class PathChannelTest(UUIDIdentifierPinBase):
    """Path identifiers: malformed ≡ nonexistent — the schemathesis repro
    from the issue (``GET /billing/customers/0/balance`` → 500)."""

    def test_malformed_path_identifier_is_a_404_problem(self):
        response = self.http_client.get(
            "/api/v1/billing/customers/0/balance", **self.auth
        )
        body = assert_problem(self, response, "not_found")
        self.assertNotIn("detail", body)


class QueryChannelTest(UUIDIdentifierPinBase):
    """Query identifiers: invalid input, not a resource miss — 422 with the
    usual sanitized error list (the issue's ``?customer_id=0`` repro)."""

    def test_malformed_query_identifier_is_a_422_problem(self):
        response = self.http_client.get(
            "/api/v1/metering/analytics/usage", {"customer_id": "0"}, **self.auth
        )
        body = assert_problem(self, response, "validation_error")
        self.assertEqual(
            body["errors"],
            [{"loc": ["query", "customer_id"],
              "msg": "value is not a valid UUID identifier",
              "type": "uuid_identifier"}],
        )


class BodyChannelTest(UUIDIdentifierPinBase):
    """Body identifiers: 422 like any other invalid field (the issue's
    empty-string repro, plus /attribute — same defect found in the fix
    sweep, not on the issue's list of 22)."""

    def _post(self, url, payload):
        return self.http_client.post(
            url, data=payload, content_type="application/json", **self.auth
        )

    def test_malformed_body_identifier_is_a_422_problem(self):
        response = self._post(
            "/api/v1/referrals/referrers", '{"customer_id": ""}'
        )
        body = assert_problem(self, response, "validation_error")
        self.assertEqual(
            body["errors"],
            [{"loc": ["body", "payload", "customer_id"],
              "msg": "value is not a valid UUID identifier",
              "type": "uuid_identifier"}],
        )

    def test_attribute_body_identifier_is_guarded_too(self):
        response = self._post(
            "/api/v1/referrals/attribute", '{"customer_id": "0", "code": "x"}'
        )
        assert_problem(self, response, "validation_error")


class OperationSweepTest(UUIDIdentifierPinBase):
    """Every operation the issue lists answers its channel's problem —
    the in-suite mirror of the schemathesis finding, one subTest per op."""

    def test_every_path_operation_answers_404(self):
        for method, url, body in PATH_OPERATIONS:
            with self.subTest(f"{method} {url}"):
                response = self.http_client.generic(
                    method, url,
                    data=json.dumps(body) if body is not None else "",
                    content_type="application/json", **self.auth,
                )
                assert_problem(self, response, "not_found")

    def test_every_query_operation_answers_422(self):
        for url in QUERY_OPERATIONS:
            with self.subTest(url):
                response = self.http_client.get(
                    url, {"customer_id": "0"}, **self.auth
                )
                assert_problem(self, response, "validation_error")


class MixedErrorOrderingTest(UUIDIdentifierPinBase):
    """Malformed ≡ nonexistent extends to ordering: when anything else also
    failed validation, the request stays in the 422 lane — exactly what a
    well-formed-but-unknown identifier gets (validation answers first, the
    lookup never runs)."""

    def test_malformed_path_id_with_invalid_body_stays_422(self):
        response = self.http_client.put(
            "/api/v1/billing/customers/0/auto-top-up", data="{}",
            content_type="application/json", **self.auth,
        )
        assert_problem(self, response, "validation_error")


class UnchangedBehaviorTest(UUIDIdentifierPinBase):
    """Well-formed identifiers are untouched by the guard: unknown answers
    the same 404 as before, known reaches the 2xx path (the issue's
    no-2xx-change scope line)."""

    def test_wellformed_unknown_identifier_still_404s(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{uuid.uuid4()}/balance", **self.auth
        )
        assert_problem(self, response, "not_found")

    def test_wellformed_known_identifier_still_succeeds(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="pin-customer"
        )
        response = self.http_client.get(
            f"/api/v1/billing/customers/{customer.id}/balance", **self.auth
        )
        self.assertEqual(response.status_code, 200)
