class UBBError(Exception):
    """Base UBB exception."""
    pass


class AuthenticationError(UBBError):
    pass


class InsufficientBalanceError(UBBError):
    pass


class CustomerSuspendedError(UBBError):
    pass


class IdempotencyError(UBBError):
    pass


class PricingError(UBBError):
    pass


class StripeError(UBBError):
    pass


class RateLimitError(UBBError):
    pass


class ArrearsThresholdError(UBBError):
    pass


class StripeTransientError(UBBError):
    """Retryable Stripe errors (network, rate limit, server 5xx)."""
    pass


class StripePaymentError(UBBError):
    """Non-retryable payment errors (card declined, insufficient funds)."""
    def __init__(self, message, code=None, decline_code=None):
        super().__init__(message)
        self.code = code
        self.decline_code = decline_code


class StripeFatalError(UBBError):
    """Non-retryable fatal errors (auth, config, idempotency mismatch)."""
    pass
