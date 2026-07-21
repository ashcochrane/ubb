"""``@records_audit`` — the route-level declaration the sweep pin reads (#82).

The audit twin of ``@role_floor`` (``core.auth``), and the same trust model: a
pure marker that sets an attribute on the view function, enforced by an
independent walker over the live API (``api/v1/tests/test_audit_sweep.py``).
The walker demands that **every principal-initiated mutating route** carries this
marker or is on the reviewable exemption list — so a new mutation added without
an audit record turns CI red, exactly as ADR-001's boundary walker guards the
import matrix.

Placement mirrors ``@role_floor`` — directly below the route decorator (and below
``@role_floor`` where both apply)::

    @tenant_router.post("/api-keys", response=...)
    @role_floor(ADMIN)
    @records_audit("api_key.created")
    def create_api_key(request, ...): ...

The marker declares *which* actions the route may write; the actual ``record()``
call lives in the handler body (or, for an async mutation like the sandbox reset,
in the task it enqueues) with the curated per-action metadata the ledger stores.
Kept a pure marker — it never wraps the function — so it composes with
``functools.wraps`` in either order and never hides ``_role_floor``.

The declared names are validated against the registry at import time, so a typo
or an unregistered action fails loudly at startup rather than at first request.
"""
from apps.platform.audit.actions import is_registered_action


def records_audit(*actions):
    """Mark a view as writing one or more registered audit actions.

    ``actions`` must be non-empty and every name must be registered in
    ``apps.platform.audit.actions.AUDIT_ACTIONS`` — otherwise this raises at
    import time (the module fails to load), keeping the declared vocabulary and
    the ledger's vocabulary from drifting.
    """
    if not actions:
        raise ValueError("records_audit() requires at least one action name")
    unknown = [a for a in actions if not is_registered_action(a)]
    if unknown:
        raise ValueError(
            f"unregistered audit action(s) {unknown!r} — add them to "
            f"apps.platform.audit.actions.AUDIT_ACTIONS (additive-only)"
        )

    def decorator(view_func):
        # Pure marker: set-and-return. functools.wraps(update_wrapper) copies
        # __dict__ upward, so a @role_floor wrapper above inherits this too.
        existing = getattr(view_func, "_audit_actions", ())
        view_func._audit_actions = tuple(existing) + tuple(actions)
        return view_func

    return decorator
