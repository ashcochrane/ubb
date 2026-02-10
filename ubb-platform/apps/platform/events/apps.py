from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.events"
    label = "events"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.platform.events.webhooks import handle_webhook_delivery

        event_types = [
            "usage.recorded",
            "usage.refunded",
            "referral.reward_earned",
            "referral.created",
            "referral.expired",
        ]
        for event_type in event_types:
            handler_registry.register(
                event_type,
                f"platform.webhook_delivery.{event_type}",
                handle_webhook_delivery,
                requires_product=None,
            )
