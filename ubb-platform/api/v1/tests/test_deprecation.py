"""Deprecation machinery (ADR-003 §4, #86 Stage-5): the Sunset-header
middleware + the deprecated-route registry.

Two invariants this suite pins:

* **Zero routes deprecated at launch.** The machinery stands ready; the registry
  is empty and no operation in the committed spec is ``deprecated: true``. The
  first real deprecation is process (add a registry entry + the spec flag), not
  engineering.
* **Spec flag and runtime header stay coupled.** ADR-003 §4 gives every
  deprecation BOTH ``deprecated: true`` in the spec AND a ``Sunset`` header. The
  consistency test binds the two facets so a future deprecation cannot set one
  without the other.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from django.test import Client, TestCase
from django.utils.http import http_date

from api.v1.deprecation import (
    DEPRECATED_ROUTES,
    DeprecatedRoute,
    find_deprecated_route,
    register_deprecated_route,
)

# openapi/v1.json lives at the git root: ubb/openapi/v1.json.
# this file is ubb/ubb-platform/api/v1/tests/test_deprecation.py.
SPEC_PATH = Path(__file__).resolve().parents[4] / "openapi" / "v1.json"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _spec_deprecated_operations():
    doc = json.loads(SPEC_PATH.read_text())
    return {
        (method.upper(), path)
        for path, item in doc["paths"].items()
        for method, op in item.items()
        if method in HTTP_METHODS and op.get("deprecated")
    }


class RegistryEmptyAtLaunchTest(TestCase):
    def test_registry_is_empty_at_launch(self):
        # Acceptance criterion: zero routes deprecated at launch.
        self.assertEqual(DEPRECATED_ROUTES, [])

    def test_spec_marks_nothing_deprecated_at_launch(self):
        self.assertEqual(_spec_deprecated_operations(), set())

    def test_registry_and_spec_deprecations_are_consistent(self):
        # deprecated:true in the spec <=> a registry entry (same method+path).
        # Both empty now; this guards the first real deprecation.
        registry = {(r.method, r.path_template) for r in DEPRECATED_ROUTES}
        self.assertEqual(_spec_deprecated_operations(), registry)


class TemplateMatchingTest(TestCase):
    def test_literal_path_matches_exactly(self):
        r = DeprecatedRoute("GET", "/api/v1/health", date(2026, 12, 31))
        self.assertTrue(r.matches("GET", "/api/v1/health"))
        self.assertFalse(r.matches("POST", "/api/v1/health"))
        self.assertFalse(r.matches("GET", "/api/v1/health/extra"))

    def test_path_param_matches_one_segment_only(self):
        r = DeprecatedRoute("GET", "/api/v1/margin/{customer_id}", date(2026, 12, 31))
        self.assertTrue(r.matches("GET", "/api/v1/margin/8d4a2b92-eb9c-4e09-899b-abc"))
        # a {param} is exactly one segment: it must not swallow a subpath...
        self.assertFalse(r.matches("GET", "/api/v1/margin/abc/trend"))
        # ...nor match the bare collection root.
        self.assertFalse(r.matches("GET", "/api/v1/margin/"))

    def test_method_is_normalised_to_upper(self):
        r = DeprecatedRoute("get", "/api/v1/health", date(2026, 1, 1))
        self.assertEqual(r.method, "GET")
        self.assertTrue(r.matches("get", "/api/v1/health"))


class SunsetHeaderFormatTest(TestCase):
    def test_sunset_value_is_rfc8594_httpdate(self):
        r = DeprecatedRoute("GET", "/api/v1/health", date(2026, 12, 31))
        expected = http_date(datetime(2026, 12, 31, tzinfo=timezone.utc).timestamp())
        self.assertEqual(r.sunset_header(), expected)
        self.assertEqual(r.sunset_header(), "Thu, 31 Dec 2026 00:00:00 GMT")


class FindDeprecatedRouteTest(TestCase):
    def test_returns_none_when_registry_empty(self):
        self.assertIsNone(find_deprecated_route("GET", "/api/v1/health"))


class SunsetMiddlewareTest(TestCase):
    """The middleware is exercised through the real request stack against the
    public /api/v1/health route, temporarily registered as deprecated."""

    def setUp(self):
        self.client = Client()

    def _deprecate(self, method, path_template, sunset, link=None):
        route = register_deprecated_route(method, path_template, sunset, link=link)
        # Keep the module-level registry empty for every other test.
        self.addCleanup(DEPRECATED_ROUTES.remove, route)
        return route

    def test_sunset_header_emitted_on_deprecated_route(self):
        self._deprecate("GET", "/api/v1/health", date(2026, 12, 31))
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Sunset"], "Thu, 31 Dec 2026 00:00:00 GMT")

    def test_no_sunset_header_when_route_not_deprecated(self):
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Sunset", resp)

    def test_sunset_link_header_when_link_provided(self):
        self._deprecate(
            "GET", "/api/v1/health", date(2027, 1, 1),
            link="https://ubb.example/docs/api-compatibility",
        )
        resp = self.client.get("/api/v1/health")
        self.assertEqual(
            resp["Link"],
            '<https://ubb.example/docs/api-compatibility>; rel="sunset"',
        )

    def test_header_only_on_the_deprecated_method(self):
        # Deprecating POST /health must not stamp a GET /health response.
        self._deprecate("POST", "/api/v1/health", date(2027, 1, 1))
        resp = self.client.get("/api/v1/health")
        self.assertNotIn("Sunset", resp)
