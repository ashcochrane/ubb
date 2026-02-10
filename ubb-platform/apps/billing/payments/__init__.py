from apps.billing.payments.stripe_provider import StripeProvider

_provider = None


def get_payment_provider():
    global _provider
    if _provider is None:
        _provider = StripeProvider()
    return _provider
