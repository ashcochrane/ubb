from django.apps import AppConfig


class TenantBillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.tenant_billing"
    label = "tenant_billing"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.handlers import handle_customer_deleted_billing

        handler_registry.register(
            "usage.recorded",
            "billing.wallet_deduction",
            handle_usage_recorded_billing,
            requires_product="billing",
        )

        handler_registry.register(
            "customer.deleted",
            "billing.cleanup_customer",
            handle_customer_deleted_billing,
            requires_product="billing",
        )
