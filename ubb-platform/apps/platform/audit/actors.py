"""Audit actors — who performed a recorded action (ADR-004 §4).

The audit ledger answers "who did what, when, to which resource". This module
owns the *who*: the four actor kinds live from day one, the immutable ``Actor``
snapshot a record stores, and the request-scoped contextvar the auth seam
captures into — read once at ``record()`` time so mutation sites never pass "who"
by hand. It is the ``correlation_id`` pattern applied to identity: captured once
at one seam (``core/auth.py`` for tenant principals, ``core/widget_auth.py`` for
end customers), zero call-site plumbing.

Kept deliberately free of model imports so the auth seams can capture an actor
with no risk of an import cycle: the builders take plain strings, and the
concrete Member / TenantApiKey / Customer stays where it is already imported.
"""
import contextvars
from dataclasses import dataclass

# Actor kinds — an OPEN enum (ADR-004 §4): the feed and its clients must tolerate
# it growing. Four are live from day one; ``system`` is reserved for the deferred
# system-initiated actions (auto-top-up firing, suspensions, patrol repairs — out
# of scope for v1, §3) and is used here only as the honest label for a record
# with no resolvable principal.
MEMBER = "member"
API_KEY = "api_key"
OPERATOR = "operator"
END_CUSTOMER = "end_customer"
SYSTEM = "system"  # reserved / deferred — see ADR-004 §3, §4

# An operator is a UBB staffer acting on a tenant's account. The feed records
# *that* staff acted, never *which* staffer — every operator action renders under
# this one name (ADR-004 §4).
OPERATOR_DISPLAY = "UBB operator"


@dataclass(frozen=True)
class Actor:
    """An immutable snapshot of the acting principal, taken at action time.

    ``display`` is captured at the moment of the action, so a later rename or
    deletion never rewrites history (ADR-004 §4). ``id`` is the stable identifier
    of the principal within its kind (a Member / key / Customer UUID), or ``""``
    when the kind has no stable id — a token-bearing operator has no principal
    row.
    """
    kind: str
    id: str
    display: str


def member_actor(member_id, email):
    """A Clerk-verified Member. Display snapshot is the email it acted under."""
    return Actor(kind=MEMBER, id=str(member_id), display=email or "")


def api_key_actor(key_id, label):
    """A tenant API key. Display snapshot is the key's label, falling back to a
    generic name so an unlabelled key still reads sensibly in the feed."""
    return Actor(kind=API_KEY, id=str(key_id), display=label or "API key")


def operator_actor(operator_id=""):
    """A UBB operator (support/staff). Always rendered ``UBB operator`` — the
    audit trail records that staff acted, never which staffer (ADR-004 §4)."""
    return Actor(kind=OPERATOR, id=str(operator_id or ""), display=OPERATOR_DISPLAY)


def end_customer_actor(customer_id, external_id):
    """A widget-authenticated end customer (e.g. a self-serve top-up). Display
    snapshot is the tenant's own handle for them (``external_id``)."""
    return Actor(kind=END_CUSTOMER, id=str(customer_id), display=external_id or "")


# Request-scoped capture. Default None => unattributed (record() falls back to
# the reserved ``system`` kind). The mirror of ``core.logging.correlation_id_var``.
_actor_var: contextvars.ContextVar = contextvars.ContextVar("audit_actor", default=None)


def set_current_actor(actor):
    """Capture the acting principal for the rest of this request (auth seam)."""
    _actor_var.set(actor)


def get_current_actor():
    """The actor captured this request, or ``None`` (unauthenticated / system)."""
    return _actor_var.get()


def clear_current_actor():
    """Reset the actor at request end so a pooled worker thread never leaks one
    request's principal into the next unauthenticated request on the same thread
    (the ``CorrelationIdMiddleware`` reset pattern; see RequestActorMiddleware)."""
    _actor_var.set(None)
