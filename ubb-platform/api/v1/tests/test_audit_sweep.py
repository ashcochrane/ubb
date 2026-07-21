"""The #82 mutating-route pin: every principal-initiated mutation is audited.

Seam (ADR-001's boundary walker + the #80 role-floor walker are the prior art):
enumerate every mutating operation (POST/PUT/PATCH/DELETE) on the one ``NinjaAPI``
and prove each one either **records** an audit action (carries the
``@records_audit`` marker, all names registered) or is on the **exemption list**
below. A new mutating route with neither turns this red — so the audit ledger
structurally cannot fall behind the mutating surface (ADR-004 §2).

The exemption list is itself the reviewable artifact: the only mutations that do
NOT belong in the tenant-facing audit feed are **usage ingestion + the spend
pre-check** — telemetry, not governance (ADR-004: "usage ingestion excluded").
Everything else — config, membership + key lifecycle, hand-moved money — records.
"""
from api.v1.api import api
from apps.platform.audit.actions import is_registered_action

# --- the carve, as data -----------------------------------------------------

# Mutating routes that deliberately do NOT record — telemetry, not governance.
# Each line is a conscious decision, reviewed here and nowhere else:
_EXEMPT = {
    # Usage ingestion — the firehose of metered telemetry (ADR-004 excludes it).
    ("POST", "/metering/usage"),
    ("POST", "/metering/usage/batch"),
    ("POST", "/metering/usage/ingest"),
    # Task close finalises a metering task — the tail of usage ingestion, and
    # any settlement it triggers is automatic, not a principal moving money.
    ("POST", "/metering/tasks/{task_id}/close"),
    # Spend pre-check — an enforcement read on the hot path that may open a task;
    # telemetry-adjacent, authors no governance/config/money change.
    ("POST", "/billing/pre-check"),
    # Subscription sync — a reconciliation trigger that pulls external Stripe
    # truth; it authors no tenant-side governance decision.
    ("POST", "/subscriptions/sync"),
}

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Guards against a vacuous pass (path-resolution breakage seeing zero routes).
# 52 recording routes + 6 exempt = the whole mutating surface today; a new
# mutation moves one of these and forces a conscious update here.
_EXPECTED_MUTATING = 58
_EXPECTED_EXEMPT = 6


def _iter_mutating_ops():
    """(method, full_path, view_func) for every mutating operation on the API.

    ``full_path`` is the mount-prefixed path without the ``/api/v1`` root — the
    same shape ``_EXEMPT`` is keyed on (mirrors the role-floor walker)."""
    for prefix, router in api._routers:
        for path, path_view in router.path_operations.items():
            segments = [s for s in (prefix.strip("/"), path.strip("/")) if s]
            full = "/" + "/".join(segments)
            for op in path_view.operations:
                for method in op.methods:
                    if method in _MUTATING_METHODS:
                        yield method, full, op.view_func


def test_walker_sees_the_whole_mutating_surface():
    """Fail loudly if introspection breaks rather than passing vacuously."""
    mutating = list(_iter_mutating_ops())
    assert len(mutating) == _EXPECTED_MUTATING, (
        f"expected {_EXPECTED_MUTATING} mutating routes, saw {len(mutating)} — "
        f"the surface changed; audit the new route (mark it @records_audit or "
        f"add it to _EXEMPT) and update this count")
    exempt = [(m, p) for m, p, _ in mutating if (m, p) in _EXEMPT]
    assert len(exempt) == _EXPECTED_EXEMPT, (
        f"expected {_EXPECTED_EXEMPT} exempt mutating routes, saw {len(exempt)}")


def test_every_mutating_route_records_or_is_exempt():
    """The load-bearing pin: no un-audited principal-initiated mutation."""
    offenders = []
    for method, full, view_func in _iter_mutating_ops():
        if (method, full) in _EXEMPT:
            continue
        actions = getattr(view_func, "_audit_actions", None)
        if not actions:
            offenders.append(
                f"{method} {full}: NOT AUDITED — add @records_audit(...) with a "
                f"record() call, or add ({method!r}, {full!r}) to _EXEMPT")
    assert not offenders, (
        "mutating routes that neither record nor are exempt:\n"
        + "\n".join(offenders))


def test_declared_actions_are_registered():
    """Every action a route declares must be in the additive-only registry."""
    offenders = []
    for method, full, view_func in _iter_mutating_ops():
        for action in getattr(view_func, "_audit_actions", ()) or ():
            if not is_registered_action(action):
                offenders.append(f"{method} {full}: unregistered action {action!r}")
    assert not offenders, "unregistered audit actions:\n" + "\n".join(offenders)


def test_exemptions_are_real_mutating_routes():
    """No stale exemption: every _EXEMPT entry maps to a live mutating route,
    so the reviewable list can never quietly cover a route that no longer
    exists (or was renamed by a restructure)."""
    live = {(m, p) for m, p, _ in _iter_mutating_ops()}
    stale = sorted(_EXEMPT - live)
    assert not stale, f"exemptions with no matching live route: {stale}"
