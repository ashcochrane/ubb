"""Seat-roster hook registry (F3.3): platform owns the seam, products attach.

Pure registry mechanics (no DB) + one wiring assertion that the subscriptions
listener really was registered by SubscriptionsConfig.ready() during Django
app loading — the boundary inversion that lets platform/billing notify roster
changes without importing subscriptions.
"""
from apps.platform.customers import hooks


class TestSeatRosterHookRegistry:
    def setup_method(self):
        # Isolate the registry for mechanics tests (the REAL subscriptions
        # listener is registered at app loading and would fire on notify);
        # restore the app-ready state afterwards.
        self._saved = list(hooks._listeners)
        hooks._listeners[:] = []

    def teardown_method(self):
        hooks._listeners[:] = self._saved

    def test_register_and_notify_passes_business_through(self):
        calls = []
        hooks.register_seat_roster_listener(calls.append)
        sentinel = object()
        hooks.notify_seat_roster_changed(sentinel)
        assert calls == [sentinel]

    def test_register_is_idempotent(self):
        calls = []
        fn = calls.append
        hooks.register_seat_roster_listener(fn)
        hooks.register_seat_roster_listener(fn)  # ready() may run twice
        hooks.notify_seat_roster_changed("biz")
        assert calls == ["biz"]

    def test_notify_with_no_listeners_is_noop(self):
        hooks.notify_seat_roster_changed(object())  # must not raise

    def test_subscriptions_listener_registered_at_app_ready(self):
        # SubscriptionsConfig.ready() ran during test-process app loading and
        # must have attached the seat-quantity push to the platform seam
        # (self._saved is the registry exactly as app loading left it).
        from apps.subscriptions.orchestration.seats import sync_seat_quantity_on_commit

        assert sync_seat_quantity_on_commit in self._saved
