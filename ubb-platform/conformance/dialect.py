"""The error dialect as data — pure helpers, no Django, no schemathesis.

``docs/conventions/api-contract.md`` documents the error contract globally
rather than per-route: every error renders as RFC 9457 problem+json, and a
fixed set of 4xx statuses may appear on any operation without being listed
in its ``responses`` map. These helpers turn that prose into checkable
predicates for the conformance sweep (checks.py); test_dialect.py pins them.
"""
import json
from pathlib import Path

# ubb-platform/conformance/dialect.py -> the git root (the
# api.v1.openapi_export idiom, without importing Django here).
_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "openapi" / "error-codes.json"

# The out-of-band statuses of the dialect, derived from the checked-in code
# registry — the same file core.problems loads, so the sweep and the app
# cannot disagree about what "contract" means. Every 4xx a registered code
# renders as may appear on any operation undocumented; 5xx is deliberately
# excluded — internal_error/service_unavailable name the *rendering*, but a
# server error during the sweep is always a finding.
OUT_OF_BAND_STATUSES = frozenset(
    entry["status"]
    for entry in json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))[
        "problems"
    ].values()
    if entry["status"] < 500
)

PROBLEM_CONTENT_TYPE = "application/problem+json"

# RFC 9457 members the dialect always emits (`detail` is optional prose).
REQUIRED_MEMBERS = ("type", "title", "status", "code")


def status_violation(status, documented):
    """One-line description of the lie, or None when `status` is fine.

    `documented` is the operation's declared response-status set (strings,
    as OpenAPI keys them). A status is fine when the operation documents it
    or the dialect allows it out-of-band; anything else — an undocumented
    success code, a redirect, any 5xx — contradicts the document.
    """
    if str(status) in documented:
        if status >= 500:
            return None  # documented 5xx (e.g. a /ready 503) — not a lie
        return None
    if status in OUT_OF_BAND_STATUSES:
        return None
    if status >= 500:
        return (
            f"{status}: server errors are never part of the contract "
            "(internal_error means an unhandled exception)"
        )
    return (
        f"{status} is neither documented on this operation nor allowed "
        "out-of-band by the error dialect (docs/conventions/api-contract.md)"
    )


def envelope_violations(status, content_type, body, headers):
    """RFC 9457 violations for an error response; [] when conforming.

    Success responses are out of scope (the documented-response schema
    checks cover those). For status >= 400 the dialect's promise is
    absolute — "no endpoint builds an error body by hand" — so any
    non-problem+json error is a finding regardless of documentation.
    `headers` is a plain str->str mapping; lookup is case-insensitive.
    """
    if status < 400:
        return []
    violations = []
    media = (content_type or "").split(";")[0].strip().lower()
    if media != PROBLEM_CONTENT_TYPE:
        violations.append(
            f"content-type {content_type!r} — the dialect promises "
            f"{PROBLEM_CONTENT_TYPE} on every error"
        )
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        violations.append("body is not valid JSON")
        return violations
    if not isinstance(parsed, dict):
        violations.append("body is not a JSON object")
        return violations
    missing = [m for m in REQUIRED_MEMBERS if m not in parsed]
    if missing:
        violations.append(f"missing problem members: {', '.join(missing)}")
    if "status" in parsed and parsed["status"] != status:
        violations.append(
            f"problem body says status {parsed['status']} but the wire "
            f"status is {status}"
        )
    if status == 429:
        lowered = {k.lower(): v for k, v in headers.items()}
        if "retry-after" not in lowered:
            violations.append(
                "429 without Retry-After — the dialect promises it always")
    return violations
