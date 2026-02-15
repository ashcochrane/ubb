from django.apps import AppConfig


class StripeConnectorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.connectors.stripe"
    label = "stripe_connector"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.billing.connectors.stripe.handlers import (
            handle_balance_low_stripe,
        )

        handler_registry.register(
            "billing.balance_low",
            "stripe_connector.auto_topup",
            handle_balance_low_stripe,
            requires_product="billing",
        )
