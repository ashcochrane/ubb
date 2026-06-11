"""Seat-roster change hooks.

Platform never imports products: a product that needs to react to roster
changes (e.g. subscriptions pushing the new live seat quantity to Stripe)
registers a listener in its AppConfig.ready(). Listeners are invoked
synchronously at the roster-mutation site — the subscriptions listener
defers internally via transaction.on_commit, so the registry adds no timing
change over the old direct call (same function, same on_commit binding to
the roster-change transaction). No products installed = no listeners = no-op.
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
