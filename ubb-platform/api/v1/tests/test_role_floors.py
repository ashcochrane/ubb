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
    ("POST", "/metering/tasks/{task_id}/close"),
    # spend pre-check (may start a task)
    ("POST", "/billing/pre-check"),
    # money IN (driver's amendment: paying into your own wallet is day-to-day)
    ("POST", "/billing/customers/{customer_id}/top-up"),
    # customers, accounts & subscription lifecycle
    ("POST", "/platform/customers"),
    ("POST", "/subscriptions/customers/{external_id}/subscribe"),
    ("POST", "/subscriptions/customers/{external_id}/seats"),
    ("POST", "/subscriptions/customers/{external_id}/subscription/cancel"),
    ("POST", "/subscriptions/customers/{external_id}/subscription/pause"),
    ("POST", "/subscriptions/customers/{external_id}/subscription/resume"),
    ("POST", "/subscriptions/sync"),
    # plan membership (#7 plan-as-kernel): putting a customer on a plan is a
    # day-to-day lifecycle write, same footing as /subscribe beside it — it
    # never touches Stripe or a plan's commercial terms.
    ("POST", "/customers/{external_id}/plan"),
    # referrals: register a referrer / attribute a referral
    ("POST", "/referrals/referrers"),
    ("POST", "/referrals/attribute"),
}

# Guard against a vacuous pass (path-resolution breakage seeing zero routes).
# 108 pre-existing tenant routes + 2 member management routes (#80) + the #82
# audit feed (GET /audit/records, Read floor) + the 3 webhook lifecycle routes
# (#83: PATCH edit, POST rotate-secret [Admin], GET deliveries [Read]) = 114,
# less the 2 duplicate tenant billing GETs (billing-periods/invoices) removed
# in the #86 sweep — their canonical Read-floored twins live on the tenant
# mount.
#
# plan-as-kernel (#7): +6 for the /api/v1/plans + /customers/{id}/plan routes
# = 118; then task 8 deletes platform_router's duplicate POST /platform/plans
# + PATCH /platform/plans/{key} (superseded by plan_router's #7 routes) and
# moves the 5 lifecycle verbs onto subscriptions_router (a rename, not a net
# add/remove): 118 - 2 = 116.
#
# unified grouping model: +3 (task 3) PUT /metering/grouping-fields [Admin — the
# plan owner's ruling: the grouping vocabulary feeds rate selection (D1), a
# pricing-rule change like markup.set/rate_card.*, so it takes the Admin
# default and needs no _WRITE_ROUTES entry], GET /metering/grouping-fields [Read],
# GET /metering/grouping-fields/{key}/values [Read]. +2 (task 7) PUT
# /metering/task-types [Admin — same ruling: a task type's ceiling prices
# usage], GET /metering/task-types [Read]. +2 (task 14) GET /metering/tasks
# and GET /metering/tasks/{task_id} [Read] — the task read surface over the
# materialized cost rollups. +1 (task 16) GET /metering/analytics/tasks
# [Read] — the per-task-type unit economics rollup. 116 + 8 = 124.
#
# one published way to report usage (slice 1): -1, POST /metering/usage/ingest
# is deleted as this slice's one reviewed contract break, taking its Write
# entry above with it. 124 - 1 = 123. The exempt count did NOT move on that
# ticket: the ingest route was floored, not exempt.
#
# The exempt count moves HERE instead: GET /metering/ops/ingest-health is
# deleted with the pipeline it watched, so _EXEMPT_EXACT loses its only ops
# entry and the exempt total goes 11 - 1 = 10. The floored count is untouched
# — an exempt route was never in it.
#
# the Event Type catalogue reaches the contract (slice 2, #267): +17, and NOT
# ONE of them needs a _WRITE_ROUTES entry. Six Read GETs (/providers,
# /event-categories, /event-types, /event-types/{key}, its measurements and
# its reported-cost mapping) and eleven Admin writes. The Admin default is the
# ruling the two registries beside it already carry — a declaration decides
# how usage is costed, which makes it a pricing-rule change rather than a
# day-to-day data operation — and it applies to the satellites too, because a
# supplier is what supplier COGS attribution keys on. 123 + 17 = 140.
#
# a markup charge can be explained (slice 4, #357): +3, the tenant's default
# markup rung — one Read GET and two Admin writes, and NEITHER write needs a
# _WRITE_ROUTES entry. Declaring the percentage every unruled event is charged
# at, and withdrawing it so those events stop being priced at all, decide what a
# customer pays; that is the same footing as the markup routes beside them and
# as the two registries above, not a day-to-day data operation. 140 + 3 = 143.
#
# every change to a Pricing Book is a publish (slice 4, #358): +5, and no
# _WRITE_ROUTES entry either. Two Read GETs (a book's pending changes, and one
# of them with its diff) and three Admin writes — declaring a change,
# publishing it and discarding it. The Admin floor is the one the immediate
# reprice route beside them already carries and for the same reason: this is
# the act that decides what every customer priced by that book is charged.
# Declaring writes no rule, and it is still Admin — a draft is the first half of
# that act, and a floor that let anyone stage a price change for an Admin to
# approve would be a floor on the wrong half. 143 + 5 = 148.
#
# 148 -> 151 with #361's customer override: two Admin writes and one Read GET.
# Declaring a customer's own rule and withdrawing it decide what one named
# customer is charged, which is the same act as the five above at a narrower
# scope, so they take the same floor. The GET answers what a customer would be
# charged without the deal — a read a client makes to offer a starting point,
# and one that decides nothing. 148 + 3 = 151.
#
# 151 -> 152 with #363's Resolution Run: one Admin write, and the floor is
# argued rather than guessed (ruling 12a). A run writes money-adjacent numbers
# into periods whose reporting is already closed; under the receipt's sealing
# rule its write is a one-time completion, so it is IRREVERSIBLE and there is no
# second act to undo one with; and what it completes is a customer-facing money
# figure. Irreversible plus money-adjacent is the highest floor this table has.
# 151 + 1 = 152.
#
# 152 -> 155 with #364's three recovery reads: the queue of everything that went
# unresolved, what recovering a filter would be worth per customer, and what
# waiving has cost. All three are Read GETs and none needs a _WRITE_ROUTES entry,
# because none of them is a write at all — and that is the ruling rather than a
# consequence of them happening to be reads. The customer adjustment is the only
# one of the four recovery mechanisms that moves money, two documents forbid it
# being automatic, and Stripe owns the billing engine UBB never reimplements: so
# these produce a figure with its receipts and there is no button that bills.
# The Read floor is the carve's default for a GET and it is right here for the
# ordinary reason — they decide nothing. The act they project, which does not,
# keeps its Admin floor one line above. 152 + 3 = 155.
#
# ⚠ AND THEN TWO LEFT, WHICH IS THE FIRST TIME THIS COUNT HAS FALLEN (#367).
# The immediate add-a-rule and retire-a-rule routes are deleted — both are
# declared changes on a publish now — so two Admin-floored routes went with
# them. Neither was carved and neither was exempt, so the exempt count below is
# untouched. 155 - 2 = 153.
_EXPECTED_FLOORED = 153
_EXPECTED_EXEMPT = 10


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
