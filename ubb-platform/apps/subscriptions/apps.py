from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
    label = "subscriptions"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions

        handler_registry.register(
            "usage.recorded",
            "subscriptions.cost_accumulator",
            handle_usage_recorded_subscriptions,
            requires_product="subscriptions",
        )
