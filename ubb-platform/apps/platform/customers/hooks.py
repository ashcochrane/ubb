"""Seat-roster change hooks.

Platform never imports products: a product that needs to react to roster
changes (e.g. subscriptions pushing the new live seat quantity to Stripe)
registers a listener in its AppConfig.ready(). Listeners are invoked
synchronously at the roster-mutation site — the subscriptions listener
defers internally via transaction.on_commit, so the registry adds no timing
change over the old direct call (same function, same on_commit binding to
the roster-change transaction). No products installed = no listeners = no-op.

The roster mutations (R10 Stage C4, A-2): a seat created through
``POST /customers``, a seat soft-deleted, a seat suspended (the ``off`` floor,
the enforcing stop, the AR and dispute causes) and a seat reactivated. Each
notifies once, inside its own transaction.
"""

_listeners = []


def register_seat_roster_listener(fn):
    """Register ``fn(business)`` to run on every seat-roster change. Idempotent
    (AppConfig.ready() can run more than once)."""
    if fn not in _listeners:
        _listeners.append(fn)


def notify_seat_roster_changed(business):
    """Invoke every registered listener synchronously with the business Customer."""
    for fn in _listeners:
        fn(business)


def notify_if_a_seat(customer):
    """``customer`` joined or left the active roster — created, soft-deleted,
    suspended or reactivated. When it is a seat, that is a change to its
    business's roster, so notify it; any other customer is no roster's member.

    Every roster mutation calls this (or ``notify_seat_roster_changed``)
    once, inside its own transaction (R10 Stage C4, A-2, RULED Q8)."""
    if customer.account_type == "seat" and customer.parent_id:
        notify_seat_roster_changed(customer.parent)
