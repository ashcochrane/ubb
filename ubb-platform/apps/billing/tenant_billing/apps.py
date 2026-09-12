from django.apps import AppConfig


class TenantBillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.tenant_billing"
    label = "tenant_billing"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.platform.events.schemas import CustomerDeleted, UsageRecorded
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.handlers import handle_customer_deleted_billing

        handler_registry.register(
            UsageRecorded.EVENT_TYPE,
            "billing.wallet_deduction",
            handle_usage_recorded_billing,
            requires_product="billing",
        )

        handler_registry.register(
            CustomerDeleted.EVENT_TYPE,
            "billing.cleanup_customer",
            handle_customer_deleted_billing,
            requires_product="billing",
        )
