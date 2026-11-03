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
    """Non-retryable payment errors (card declined, insufficient funds).

    ``payment_intent_id`` is the PaymentIntent Stripe attached to the card
    error (``e.error.payment_intent`` on the real ``CardError`` shape), so a
    declined or SCA-blocked attempt can record the intent it concerns (O-1).
    """
    def __init__(self, message, code=None, decline_code=None, payment_intent_id=None):
        super().__init__(message)
        self.code = code
        self.decline_code = decline_code
        self.payment_intent_id = payment_intent_id


class StripeFatalError(UBBError):
    """Non-retryable fatal errors (auth, config, idempotency mismatch).

    The composition layer answers one of these, raised by a payment
    operation a tenant asked for, as the registered ``payment_not_available``
    problem (409): a valid request the payment subject cannot currently
    perform — never a bare ``internal_error`` (R10 Stage C1b, F-11, RULED Q2
    and Q21). Subclasses that name a narrower registered problem
    (``PaymentRailClosed``, ``CurrencyDisagreement``) keep their own.
    """
    pass


class StripeNotConfigured(StripeFatalError):
    """UBB itself holds no usable Stripe key for the tenant's mode — the live
    ``STRIPE_SECRET_KEY`` is unset, or a sandbox tenant has no (or a live)
    ``STRIPE_TEST_SECRET_KEY``. Raised by the wrapper before any request is
    built (F-2) and by the top-up preconditions before anything is written
    (F-11). The composition layer answers it as ``service_unavailable`` (503,
    RULED Q21): the service is not configured to perform the payment, which
    is neither the tenant's state (``payment_not_available``) nor the
    caller's request. Still a ``StripeFatalError`` to every caller of the
    rail that degrades on one."""
    pass


class PaymentNotAvailable(StripeFatalError):
    """The tenant's payment account cannot presently perform a customer
    payment operation: no connected Stripe account, or the connected account
    is not charge-ready (``charges_enabled=False``) — R10 Stage C1b, F-11
    + O-6, RULED Q2. Evaluated BEFORE a top-up attempt or its audit row is
    written, so nothing pending is left behind; answered as the registered
    ``payment_not_available`` problem (409, RULED Q21: a state conflict, not
    a malformed request). A ``StripeFatalError`` because that is what it is
    to every caller of the rail: not retryable, and raised before anything
    is sent."""

    code = "payment_not_available"

    def __init__(self, *, tenant_id, reason):
        self.tenant_id = tenant_id
        self.reason = reason
        self.explanation = (
            f"the tenant's payment account cannot perform this payment right "
            f"now: {reason}")
        super().__init__(self.explanation)


class UnknownCurrency(UBBError):
    """A currency whose minor unit ``core.money`` does not know.

    Raised rather than defaulting: a caller with no currency in hand must say
    which one it means, or the assumption stays invisible until a second
    currency is admitted — which is the coupling ``core.money`` exists to
    delete."""
    pass


class MisalignedAmount(UBBError):
    """An amount still carrying a sub-minor-unit remainder at a money boundary.

    Means some upstream step skipped ``core.money.to_minor``, and the remainder
    now has nowhere to be carried to. Rounding it away at the boundary is
    exactly the bug the carry rule exists to prevent."""
    pass


class NegativeKnownPriceRefused(UBBError):
    """A known customer price below zero reached a rail that moves money.

    UBB never writes one (#603 A2: a negative calculated price is recorded
    ``unknown`` with ``pricing_status_reason`` ``negative_price_unsupported``),
    and no rail carries negative money in v1 (ADR-0020 §5). The rule that
    stood before it — "an amount at or below zero is no money" — dropped such
    a price silently (ruling 9 retires it), and taking it would credit a
    wallet or reverse a reward. So a rail that meets one names it and moves
    nothing; an outbox handler that raises keeps its payload and retries it,
    so the state stays visible. Beside ``MisalignedAmount`` because it is the
    same kind of fact: an amount a money boundary must not carry."""

    def __init__(self, event_id, rail):
        super().__init__(
            f"usage event {event_id} reached {rail} with a known customer "
            "price below zero. UBB records a negative calculated price as "
            "unknown (negative_price_unsupported) and moves no negative money "
            "in v1, so nothing was moved.")
        self.event_id = event_id
        self.rail = rail


class NotBillingOwnerError(UBBError):
    """Task 8c ratchet: raised by ``apps.billing.locking.lock_for_billing``
    when handed a customer id that is not itself a billing owner (i.e.
    ``resolve_billing_owner(customer).id != customer.id``). Every one of the
    seven seat/owner defects found across Tasks 3/7/8 was the same shape: a
    caller reached the wallet layer with a seat id, and the lazy
    wallet-creation in ``lock_for_billing`` turned that into a silent phantom
    wallet instead of a loud failure. Callers must resolve the owner
    (``customer.resolve_billing_owner()``) before calling in."""
    pass


class NoWalletSubjectError(UBBError):
    """A wallet operation reached the wallet boundary for a tenant whose
    billing mode holds no wallet — ``apps.platform.tenants.flags.
    holds_a_wallet`` is false (``external`` and ``postpaid`` in v1).

    The same ratchet shape as ``NotBillingOwnerError`` above, one rung out:
    raised by ``apps.billing.locking.lock_for_billing`` BEFORE any ``Wallet``
    row is read or created, which is the one place every wallet mutation
    passes through — so the lazy ``Wallet.objects.create`` there can no
    longer mint a wallet for a tenant nothing in that mode reads. A wallet
    exists only where ``holds_a_wallet`` is true; an absent wallet is never a
    zero-balance wallet and is never invented by a wallet operation. The two
    entry points that write wallet-adjacent state before reaching the
    boundary (a top-up attempt, an auto-top-up configuration) raise it at
    their own door through the same rule.

    The composition layer answers it as the registered ``feature_not_enabled``
    problem (403) carrying ``detail`` below. It means "wallet capability is
    not enabled in this billing mode" — NOT that the tenant lacks the
    ``billing`` product, which an ``external + billing`` tenant has."""

    def __init__(self, billing_mode):
        self.billing_mode = billing_mode
        self.detail = (
            "wallet operations are not available in this tenant's billing "
            f"mode ({billing_mode})")
        super().__init__(self.detail)
