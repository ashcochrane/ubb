from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
    label = "subscriptions"

    def ready(self):
        from apps.platform.customers.hooks import register_seat_roster_listener
        from apps.platform.events.registry import handler_registry
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.orchestration.seats import sync_seat_quantity_on_commit

        handler_registry.register(
            "usage.recorded",
            "subscriptions.cost_accumulator",
            handle_usage_recorded_subscriptions,
            requires_product="metering",
        )
        # Platform owns the seat-roster seam (platform never imports products):
        # any roster change notifies this listener, which pushes the new live
        # seat quantity to Stripe (deferred internally via on_commit, so timing
        # is identical to the old direct call).
        register_seat_roster_listener(sync_seat_quantity_on_commit)
