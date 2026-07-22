"""The sweep: every operation of the committed spec, fuzzed in-process.

The schema is loaded from ``openapi/v1.json`` — the committed document IS
the thing under test (ADR-002), never the runtime ``/openapi.json`` — and
calls go straight into Django's WSGI app, so the sweep needs no server and
runs anywhere the platform suite runs.

Checks per response:

* ``not_a_server_error`` / ``response_schema_conformance`` /
  ``response_headers_conformance`` / ``content_type_conformance`` —
  schemathesis built-ins. Content-type is per documented status (an
  out-of-band status has no response definition, so it skips); it became
  runnable once #104 made the document declare ``application/problem+json``
  on error responses — the media type the wire always served;
* ``documented_or_dialect_status`` + ``problem_json_envelope`` — the
  repo dialect, see checks.py. The built-in ``status_code_conformance``
  is deliberately not run: it can't know about the globally-documented
  out-of-band statuses.

Coverage is best-effort per run: ``max_examples=10`` fuzzed inputs per
operation, unseeded — "no findings" means this run found nothing, not a
proof of conformance. Depth is a knob, not a redesign.
"""
import schemathesis
from hypothesis import HealthCheck, settings

from api.v1.openapi_export import COMMITTED_SPEC_PATH
from conformance.checks import documented_or_dialect_status, problem_json_envelope
from config.wsgi import application
from schemathesis.checks import not_a_server_error
from schemathesis.specs.openapi.checks import (
    content_type_conformance,
    response_headers_conformance,
    response_schema_conformance,
)

schema = schemathesis.openapi.from_path(COMMITTED_SPEC_PATH)
# The same trick from_wsgi() uses: attaching the app routes every call
# through the in-process WSGI transport (werkzeug test client).
schema.app = application

CHECKS = [
    not_a_server_error,
    content_type_conformance,
    response_schema_conformance,
    response_headers_conformance,
]
DIALECT_CHECKS = [problem_json_envelope, documented_or_dialect_status]


@schema.parametrize()
@settings(
    max_examples=10,
    deadline=None,  # a per-example deadline just makes the report flaky
    suppress_health_check=list(HealthCheck),
)
def test_conformance(case, conformance_principal):
    case.call_and_validate(
        headers=conformance_principal.headers_for(case),
        checks=CHECKS,
        additional_checks=DIALECT_CHECKS,
    )
