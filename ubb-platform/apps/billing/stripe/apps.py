from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class StripeIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing.stripe"
    label = "stripe_integration"

    def ready(self):
        # Skip validation in test environments
        import sys
        if 'test' in sys.argv:
            return
        if not getattr(settings, "STRIPE_SECRET_KEY", ""):
            raise ImproperlyConfigured("STRIPE_SECRET_KEY must be set")
        if not getattr(settings, "STRIPE_WEBHOOK_SECRET", ""):
            raise ImproperlyConfigured("STRIPE_WEBHOOK_SECRET must be set")
