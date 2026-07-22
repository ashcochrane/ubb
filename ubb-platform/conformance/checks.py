"""Repo-specific schemathesis checks, built on the pure dialect helpers.

Two checks replace schemathesis's built-in ``status_code_conformance``,
which would flag every out-of-band 401/403/404/… as undocumented — but the
error dialect (docs/conventions/api-contract.md) is documented globally,
not per-route, so those are contract, not lies. What IS a lie:

* ``documented_or_dialect_status`` — a status neither in the operation's
  ``responses`` map nor in the dialect's out-of-band set (undocumented
  success codes, redirects, and undocumented 5xx — while every 5xx,
  documented or not, is also reported by ``not_a_server_error``);
* ``problem_json_envelope`` — an error response that breaks the dialect's
  "every error is RFC 9457 problem+json" promise (wrong content type,
  non-JSON body, missing members, status mismatch, 429 sans Retry-After).
"""
from conformance.dialect import envelope_violations, status_violation


def _headers(response):
    """schemathesis Response.headers is str -> list[str]; flatten it."""
    return {key: value[0] for key, value in response.headers.items() if value}


def documented_or_dialect_status(ctx, response, case):
    documented = set(case.operation.definition.raw.get("responses", {}))
    violation = status_violation(response.status_code, documented)
    assert violation is None, (
        f"{case.operation.label}: {violation}"
    )


def problem_json_envelope(ctx, response, case):
    headers = _headers(response)
    content_type = next(
        (v for k, v in headers.items() if k.lower() == "content-type"), None)
    violations = envelope_violations(
        response.status_code,
        content_type,
        response.content,
        headers,
    )
    assert not violations, (
        f"{case.operation.label}: {response.status_code} breaks the "
        "problem+json envelope: " + "; ".join(violations)
    )
