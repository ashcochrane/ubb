from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.events"
    label = "events"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.platform.events.webhooks import handle_webhook_delivery
        from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES

        # WEBHOOK_EVENT_TYPES is the single source of truth (see catalog.py):
        # the same list the config API validates against.
        for event_type in WEBHOOK_EVENT_TYPES:
            handler_registry.register(
                event_type,
                f"platform.webhook_delivery.{event_type}",
                handle_webhook_delivery,
                requires_product=None,
            )
