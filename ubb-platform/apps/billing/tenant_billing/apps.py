from django.apps import AppConfig


class TenantBillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.tenant_billing"
    label = "tenant_billing"

    def ready(self):
        from core.event_bus import event_bus
        from apps.billing.handlers import handle_usage_recorded
        event_bus.subscribe("usage.recorded", handle_usage_recorded, requires_product="billing")
