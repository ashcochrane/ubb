from django.apps import AppConfig


class UsageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.metering.usage"
    label = "usage"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.metering.handlers import handle_refund_requested

        handler_registry.register(
            "refund.requested",
            "metering.create_refund_record",
            handle_refund_requested,
            requires_product="metering",
        )
