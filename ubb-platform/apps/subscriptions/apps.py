from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
    label = "subscriptions"

    def ready(self):
        from core.event_bus import event_bus
        from apps.subscriptions.handlers import handle_usage_recorded

        event_bus.subscribe(
            "usage.recorded",
            handle_usage_recorded,
            requires_product="subscriptions",
        )
