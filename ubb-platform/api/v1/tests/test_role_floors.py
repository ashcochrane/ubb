"""The #74 carve table, as a walker over the live API (identity build 2, #80).

Seam 3 (the ADR-001 boundary walker's sibling): enumerate every operation on
the one ``NinjaAPI`` and prove its role floor matches the carve table in #74 —
a route added without a floor, or with the wrong one, fails here. The floors
themselves are the ``@role_floor`` decorators in the composition layer; this
test is the independent statement they must agree with, so the carve is
machine-checked, not trusted to a reviewer's eye.

The carve, restated as rules (the machine form of #74's table):

* The **/me widget surface** (``end_customer_token``), the schema-hidden **ops**
  route, and the unauthenticated **health/ready** probes are not tenant
  principals — they carry NO floor.
* Every **GET** on the tenant surface floors at **Read** — *including* money,
  ledgers, invoices, margin, analytics — with exactly one deliberate exception:
  ``GET /tenant/invitations`` is **Admin** (#62's literal "invitations
  create/list/revoke, Admin-gated"; the members list beside it stays Read).
* Every **write** floors at **Admin** (changes the rules or moves money) EXCEPT
  the enumerated **Write** routes below (day-to-day data ops, plus the driver's
  amendment that a customer top-up — money *into* your own wallet — is Write).
"""
from api.v1.api import api

# --- the carve, as data -----------------------------------------------------

# Not tenant principals -> no floor.
_EXEMPT_PREFIXES = ("/me/",)
_EXEMPT_EXACT = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/metering/ops/ingest-health"),
}

# The single GET that floors above Read (deliberate, per #62).
_GET_ADMIN_EXCEPTIONS = {("GET", "/tenant/invitations")}

# Every write that floors at Write, not Admin. Everything else that mutates is
# Admin. Keeping the Write set explicit (it is the minority) pins the whole
# write side of the carve: any mutation not listed here MUST be Admin.
_WRITE_ROUTES = {
    # usage ingestion & tasks
    ("POST", "/metering/usage"),
    ("POST", "/metering/usage/batch"),
    ("POST", "/metering/usage/ingest"),
    ("POST", "/metering/tasks/{task_id}/close"),
    # spend pre-check (may start a task)
    ("POST", "/billing/pre-check"),
    # money IN (driver's amendment: paying into your own wallet is day-to-day)
    ("POST", "/billing/customers/{customer_id}/top-up"),
    # customers, accounts & subscription lifecycle
    ("POST", "/platform/customers"),
    ("POST", "/platform/customers/{external_id}/subscribe"),
    ("POST", "/platform/customers/{external_id}/seats"),
    ("POST", "/platform/customers/{external_id}/subscription/cancel"),
    ("POST", "/platform/customers/{external_id}/subscription/pause"),
    ("POST", "/platform/customers/{external_id}/subscription/resume"),
    ("POST", "/subscriptions/sync"),
    # referrals: register a referrer / attribute a referral
    ("POST", "/referrals/referrers"),
    ("POST", "/referrals/attribute"),
}

# Guard against a vacuous pass (path-resolution breakage seeing zero routes).
# 108 pre-existing tenant routes + 2 member management routes (#80) + the #82
# audit feed (GET /audit/records, Read floor).
_EXPECTED_FLOORED = 111
_EXPECTED_EXEMPT = 11


def _iter_ops():
    """(method, full_path, floor) for every live operation on the API.

    ``full_path`` is the mount-prefixed path without the ``/api/v1`` root, e.g.
    ``/tenant/invitations`` — the same shape the carve sets are keyed on.
    """
    for prefix, router in api._routers:
        for path, path_view in router.path_operations.items():
            segments = [s for s in (prefix.strip("/"), path.strip("/")) if s]
            full = "/" + "/".join(segments)
            for op in path_view.operations:
                floor = getattr(op.view_func, "_role_floor", None)
                for method in op.methods:
                    yield method, full, floor


def _is_exempt(method, full):
    return full.startswith(_EXEMPT_PREFIXES) or (method, full) in _EXEMPT_EXACT


def _expected_floor(method, full):
    """The floor the carve demands for a (non-exempt) tenant route."""
    if method == "GET":
        return "admin" if (method, full) in _GET_ADMIN_EXCEPTIONS else "read"
    return "write" if (method, full) in _WRITE_ROUTES else "admin"


def test_walker_sees_the_whole_surface():
    """Fail loudly if introspection breaks rather than passing vacuously."""
    floored = exempt = 0
    for method, full, floor in _iter_ops():
        if _is_exempt(method, full):
            exempt += 1
        else:
            floored += 1
    assert floored == _EXPECTED_FLOORED, (
        f"expected {_EXPECTED_FLOORED} floored routes, saw {floored} — the carve "
        f"or the surface changed; update the carve table with #74")
    assert exempt == _EXPECTED_EXEMPT, (
        f"expected {_EXPECTED_EXEMPT} exempt routes, saw {exempt}")


def test_exempt_routes_carry_no_floor():
    """/me, ops, and health/ready are not tenant principals — no floor binds."""
    offenders = [
        f"{m} {p} = {floor!r}"
        for m, p, floor in _iter_ops()
        if _is_exempt(m, p) and floor is not None
    ]
    assert not offenders, "exempt routes must not carry a role floor:\n" + "\n".join(offenders)


def test_every_tenant_route_floor_matches_the_carve():
    """The load-bearing pin: each route's declared floor == the #74 carve."""
    mismatches = []
    for method, full, floor in _iter_ops():
        if _is_exempt(method, full):
            continue
        if floor is None:
            mismatches.append(f"{method} {full}: NO FLOOR (expected "
                              f"{_expected_floor(method, full)})")
            continue
        expected = _expected_floor(method, full)
        if floor != expected:
            mismatches.append(f"{method} {full}: floor={floor} expected={expected}")
    assert not mismatches, (
        "role floors disagree with the #74 carve table:\n" + "\n".join(mismatches))


def test_every_get_is_read_except_the_documented_exception():
    """Money is visible to Read: no GET floors above Read but invitations list."""
    offenders = []
    for method, full, floor in _iter_ops():
        if method != "GET" or _is_exempt(method, full):
            continue
        if (method, full) in _GET_ADMIN_EXCEPTIONS:
            assert floor == "admin", f"{full} should be the Admin GET exception"
            continue
        if floor != "read":
            offenders.append(f"{method} {full} = {floor}")
    assert not offenders, "GET routes must floor at Read:\n" + "\n".join(offenders)
