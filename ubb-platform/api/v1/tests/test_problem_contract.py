"""Seam-2 pins for the #78 contract big-bang: one error dialect.

Every error from every route is RFC 9457 ``application/problem+json`` with a
stable snake_case ``code`` from the checked-in registry
(``openapi/error-codes.json``, beside the committed spec). These tests pin the
registry document and the central handler layer (``api/v1/problems.py``);
per-route conversions are pinned by each route's own suite. ``title`` and
``detail`` are prose, never contractual — pins assert codes and statuses.
"""
import json
import re
import uuid

from django.http import Http404
from django.test import Client, RequestFactory, TestCase
from ninja.errors import (
    AuthenticationError as NinjaAuthenticationError,
    HttpError,
    ValidationError as NinjaValidationError,
)

from core.problems import PROBLEMS, REGISTRY_PATH, VERDICTS, Problem
from apps.platform.tenants.models import Tenant, TenantApiKey

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")
# The status vocabulary #63 settled: 400 malformed/bad cursor, 401, 403,
# 404, 409, 410, 422 semantic validation, 429, problem-rendered 5xx — plus
# 405 for the wrong-method lane the middleware rewrites onto the dialect.
ALLOWED_STATUSES = {400, 401, 403, 404, 405, 409, 410, 422, 429, 500, 503}


def assert_problem(testcase, response, code, status=None):
    """The one shape: problem+json content type, RFC 9457 members, registry
    code, and body status matching the transport status."""
    expected_status = status or PROBLEMS[code]["status"]
    testcase.assertEqual(response.status_code, expected_status)
    testcase.assertEqual(response["Content-Type"], "application/problem+json")
    body = json.loads(response.content)
    testcase.assertEqual(body["code"], code)
    testcase.assertEqual(body["status"], expected_status)
    testcase.assertEqual(body["title"], PROBLEMS[code]["title"])
    testcase.assertTrue(body["type"].endswith("/" + code))
    return body


class RegistryDocumentTest(TestCase):
    """The checked-in registry is deterministic and internally coherent."""

    def test_registry_is_deterministically_serialized(self):
        raw = REGISTRY_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            raw, json.dumps(json.loads(raw), indent=2, sort_keys=True) + "\n"
        )

    def test_problem_codes_are_snake_case_with_valid_statuses(self):
        self.assertTrue(PROBLEMS)
        for code, entry in PROBLEMS.items():
            self.assertRegex(code, SNAKE_CASE)
            self.assertIn(entry["status"], ALLOWED_STATUSES)
            self.assertTrue(entry["title"])

    def test_verdict_words_are_snake_case_and_sorted(self):
        self.assertTrue(VERDICTS)
        for section, words in VERDICTS.items():
            self.assertRegex(section, SNAKE_CASE)
            self.assertEqual(words, sorted(words))
            for word in words:
                self.assertRegex(word, SNAKE_CASE)

    def test_ingest_rejection_words_are_problem_codes(self):
        """Per-event verdicts are data, never problem+json — but their words
        come from the same registry (#63)."""
        self.assertTrue(
            set(VERDICTS["ingest_rejections"]) <= set(PROBLEMS)
        )

    def test_unregistered_code_is_refused_at_raise_time(self):
        with self.assertRaises(ValueError):
            Problem("no_such_code_ever")


class CentralHandlerTest(TestCase):
    """The handler layer, exercised through ninja's on_exception seam."""

    def setUp(self):
        self.request = RequestFactory().get("/api/v1/anything")

    def _handle(self, exc):
        from api.v1.api import api

        return api.on_exception(self.request, exc)

    def test_problem_renders_with_extensions_and_detail(self):
        response = self._handle(
            Problem(
                "would_overdraw",
                detail="floor is 10_000_000 micros",
                extensions={"floor_micros": 10_000_000, "balance_micros": 5},
            )
        )
        body = assert_problem(self, response, "would_overdraw")
        self.assertEqual(body["detail"], "floor is 10_000_000 micros")
        self.assertEqual(body["floor_micros"], 10_000_000)
        self.assertEqual(body["balance_micros"], 5)

    def test_problem_headers_reach_the_response(self):
        response = self._handle(
            Problem("rate_limit_exceeded", headers={"Retry-After": "60"})
        )
        assert_problem(self, response, "rate_limit_exceeded")
        self.assertEqual(response["Retry-After"], "60")

    def test_stray_http_error_maps_by_status(self):
        body = assert_problem(self, self._handle(HttpError(409, "nope")), "conflict")
        self.assertEqual(body["detail"], "nope")
        assert_problem(self, self._handle(HttpError(410, "over")), "gone")

    def test_stray_429_always_carries_retry_after(self):
        response = self._handle(HttpError(429, "slow down"))
        assert_problem(self, response, "rate_limit_exceeded")
        self.assertIn("Retry-After", response)

    def test_unmapped_status_collapses_to_the_nearest_generic(self):
        # The registry pins one status per code, so a foreign status can
        # never be served — 402 has no code and lands as bad_request (400).
        assert_problem(self, self._handle(HttpError(402, "pay up")), "bad_request")

    def test_authentication_error_is_unauthorized_without_detail(self):
        body = assert_problem(
            self, self._handle(NinjaAuthenticationError()), "unauthorized"
        )
        self.assertNotIn("detail", body)

    def test_http404_never_leaks_the_model_name(self):
        body = assert_problem(
            self, self._handle(Http404("No Customer matches the given query.")),
            "not_found",
        )
        self.assertNotIn("detail", body)
        self.assertNotIn("Customer", response_text := json.dumps(body))
        self.assertNotIn("query", response_text)

    def test_validation_error_carries_sanitized_errors(self):
        exc = NinjaValidationError(
            errors=[
                {
                    "loc": ("body", "payload", "amount_micros"),
                    "msg": "Field required",
                    "type": "missing",
                    "input": {"secret": "s3cr3t"},
                    "url": "https://errors.pydantic.dev/2.x/missing",
                }
            ]
        )
        body = assert_problem(self, self._handle(exc), "validation_error")
        self.assertEqual(
            body["errors"],
            [{"loc": ["body", "payload", "amount_micros"],
              "msg": "Field required", "type": "missing"}],
        )
        self.assertNotIn("s3cr3t", json.dumps(body))

    def test_unhandled_exception_is_internal_error_with_nothing_leaked(self):
        response = self._handle(RuntimeError("boom: db password is hunter2"))
        body = assert_problem(self, response, "internal_error")
        self.assertNotIn("detail", body)
        self.assertNotIn("hunter2", response.content.decode())
        self.assertNotIn("RuntimeError", response.content.decode())


class LiveSurfaceTest(TestCase):
    """The handlers are actually installed on the one API — proven over
    real routes through the test client."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Problems")
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_missing_key_is_a_401_problem(self):
        response = self.http_client.get("/api/v1/tenant/config")
        assert_problem(self, response, "unauthorized")

    def test_unknown_object_is_a_404_problem(self):
        response = self.http_client.get(
            f"/api/v1/metering/usage/{uuid.uuid4()}", **self.auth
        )
        assert_problem(self, response, "not_found")

    def test_schema_violation_is_a_422_validation_problem(self):
        response = self.http_client.post(
            "/api/v1/metering/usage", data="{}",
            content_type="application/json", **self.auth,
        )
        body = assert_problem(self, response, "validation_error")
        self.assertTrue(body["errors"])
        self.assertEqual(
            set(body["errors"][0]), {"loc", "msg", "type"}
        )

    def test_malformed_json_is_a_400_problem(self):
        response = self.http_client.post(
            "/api/v1/metering/usage", data="{not json",
            content_type="application/json", **self.auth,
        )
        assert_problem(self, response, "bad_request")

    def test_product_gate_is_a_403_feature_problem(self):
        response = self.http_client.get("/api/v1/referrals/program", **self.auth)
        assert_problem(self, response, "feature_not_enabled")

    def test_wrong_method_is_a_405_problem_with_allow(self):
        """The one error the handlers can't reach — ninja answers a wrong
        method with a plain HttpResponseNotAllowed before any handler runs;
        the middleware rewrites it onto the dialect, keeping Allow."""
        response = self.http_client.delete("/api/v1/tenant/config", **self.auth)
        assert_problem(self, response, "method_not_allowed")
        self.assertIn("GET", response["Allow"])
