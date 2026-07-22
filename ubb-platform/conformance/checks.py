"""Repo-specific schemathesis checks, built on the pure dialect helpers.

Two checks replace schemathesis's built-in ``status_code_conformance``,
which would flag every out-of-band 401/403/404/… as undocumented — but the
error dialect (docs/conventions/api-contract.md) is documented globally,
not per-route, so those are contract, not lies. What IS a lie:

* ``documented_or_dialect_status`` — a status neither in the operation's
  ``responses`` map nor in the dialect's out-of-band set (undocumented
  success codes, redirects, and any 5xx);
* ``problem_json_envelope`` — an error response that breaks the dialect's
  "every error is RFC 9457 problem+json" promise (wrong content type,
  non-JSON body, missing members, status mismatch, 429 sans Retry-After).
"""
from conformance.dialect import envelope_violations, status_violation


def _headers(response):
    """schemathesis Response.headers is str -> list[str]; flatten it."""
    return {key: value[0] for key, value in response.headers.items() if value}


def _content_type(response):
    for key, value in response.headers.items():
        if key.lower() == "content-type" and value:
            return value[0]
    return None


def documented_or_dialect_status(ctx, response, case):
    documented = set(case.operation.definition.raw.get("responses", {}))
    violation = status_violation(response.status_code, documented)
    assert violation is None, (
        f"{case.operation.label}: {violation}"
    )


def problem_json_envelope(ctx, response, case):
    violations = envelope_violations(
        response.status_code,
        _content_type(response),
        response.content,
        _headers(response),
    )
    assert not violations, (
        f"{case.operation.label}: {response.status_code} breaks the "
        "problem+json envelope: " + "; ".join(violations)
    )
