"""Unit pins for the pure dialect helpers the conformance checks build on.

These run before the fuzz sweep in the conformance job (same pytest
invocation, plain unit tests — no Django, no schemathesis), so a broken
helper fails fast and loudly rather than silently blessing every response.
"""
from conformance.dialect import (
    OUT_OF_BAND_STATUSES,
    envelope_violations,
    status_violation,
)

PROBLEM = b'{"type": "https://ubb.dev/errors/forbidden", "title": "Forbidden", "status": 403, "code": "forbidden"}'


class TestStatusViolation:
    def test_documented_status_is_fine(self):
        assert status_violation(201, {"201"}) is None

    def test_dialect_status_is_fine_undocumented(self):
        # The error dialect (docs/conventions/api-contract.md) is documented
        # globally, not per-route: any route may answer with these.
        for status in sorted(OUT_OF_BAND_STATUSES):
            assert status_violation(status, {"200"}) is None

    def test_dialect_is_exactly_the_contracted_set(self):
        # Derived from openapi/error-codes.json (4xx only). If the registry
        # legitimately gains a 4xx status, update this pin with it — the
        # sweep's notion of "contract" must only ever change visibly.
        assert OUT_OF_BAND_STATUSES == frozenset(
            {400, 401, 403, 404, 405, 409, 410, 422, 429})

    def test_undocumented_2xx_is_a_lie(self):
        assert "202" in status_violation(202, {"200"})

    def test_server_error_is_always_a_finding(self):
        # 5xx is never contractual — even though the dialect names
        # internal_error/service_unavailable, a fuzzed 500 is a defect.
        assert status_violation(500, {"200"}) is not None

    def test_documented_5xx_passes_the_status_check(self):
        # A documented 503 isn't a lie about the document; the separate
        # not_a_server_error check still reports every 5xx.
        assert status_violation(503, {"503"}) is None

    def test_undocumented_redirect_is_a_lie(self):
        assert status_violation(301, {"200"}) is not None


class TestEnvelopeViolations:
    def test_success_responses_are_out_of_scope(self):
        assert envelope_violations(200, "text/html", b"<html>", {}) == []

    def test_conforming_problem_passes(self):
        assert envelope_violations(
            403, "application/problem+json", PROBLEM, {}) == []

    def test_content_type_parameters_are_tolerated(self):
        assert envelope_violations(
            403, "application/problem+json; charset=utf-8", PROBLEM, {}) == []

    def test_wrong_content_type_is_a_violation(self):
        violations = envelope_violations(403, "application/json", PROBLEM, {})
        assert any("application/problem+json" in v for v in violations)

    def test_html_error_page_is_a_violation(self):
        violations = envelope_violations(
            500, "text/html", b"<html>Server Error</html>", {})
        assert any("not valid JSON" in v for v in violations)

    def test_non_object_body_is_a_violation(self):
        violations = envelope_violations(
            400, "application/problem+json", b'["nope"]', {})
        assert any("JSON object" in v for v in violations)

    def test_missing_members_are_violations(self):
        violations = envelope_violations(
            404, "application/problem+json",
            b'{"detail": "gone fishing"}', {})
        assert any("type" in v and "code" in v for v in violations)

    def test_status_member_must_match_wire_status(self):
        body = PROBLEM.replace(b"403", b"404")
        violations = envelope_violations(
            403, "application/problem+json", body, {})
        assert any("404" in v and "403" in v for v in violations)

    def test_429_requires_retry_after(self):
        # "429 always with Retry-After" — part of the documented dialect.
        body = PROBLEM.replace(b"403", b"429")
        violations = envelope_violations(
            429, "application/problem+json", body, {})
        assert any("Retry-After" in v for v in violations)
        assert envelope_violations(
            429, "application/problem+json", body,
            {"Retry-After": "1"}) == []

    def test_header_lookup_is_case_insensitive(self):
        body = PROBLEM.replace(b"403", b"429")
        assert envelope_violations(
            429, "application/problem+json", body,
            {"retry-after": "1"}) == []
