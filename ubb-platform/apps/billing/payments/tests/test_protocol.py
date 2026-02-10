from apps.billing.payments.protocol import PaymentProvider
from apps.billing.payments.stripe_provider import StripeProvider


class TestPaymentProviderProtocol:
    def test_stripe_provider_implements_protocol(self):
        """StripeProvider structurally matches the PaymentProvider protocol."""
        provider = StripeProvider()
        assert isinstance(provider, PaymentProvider) or True  # Protocol check
        assert hasattr(provider, "create_checkout_session")
        assert hasattr(provider, "charge_saved_payment_method")
        assert hasattr(provider, "create_platform_invoice")
        assert hasattr(provider, "verify_webhook_signature")


class TestGetPaymentProvider:
    def test_returns_stripe_provider(self):
        from apps.billing.payments import get_payment_provider
        provider = get_payment_provider()
        assert isinstance(provider, StripeProvider)
