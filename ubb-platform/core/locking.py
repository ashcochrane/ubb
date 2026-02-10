"""
Canonical lock ordering helpers for billing operations.

Lock order: Wallet -> Customer -> TopUpAttempt -> Invoice -> UsageEvent

INVARIANT: No code path may acquire locks in a different order.
All code that needs multiple locks MUST use these helpers.
Do not call select_for_update() directly on these models.
"""


def lock_row(model_class, **lookup):
    """Acquire a row lock. Must be inside @transaction.atomic."""
    return model_class.objects.select_for_update().get(**lookup)


from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet


def lock_for_billing(customer_id):
    """
    Acquire Wallet -> Customer locks in canonical order.

    Use for: usage recording, wallet credits/debits, suspension checks.
    MUST be called within @transaction.atomic.
    """
    wallet = Wallet.objects.select_for_update().get(customer_id=customer_id)
    customer = Customer.objects.select_for_update().get(id=customer_id)
    return wallet, customer


def lock_customer(customer_id):
    """
    Acquire Customer lock only.

    Use for: status changes without wallet mutation (e.g., webhook suspension).
    MUST be called within @transaction.atomic.
    """
    return Customer.objects.select_for_update().get(id=customer_id)


def lock_top_up_attempt(attempt_id):
    """
    Acquire TopUpAttempt lock.

    Use for: status transitions after Stripe calls.
    MUST be called within @transaction.atomic.
    """
    from apps.billing.topups.models import TopUpAttempt
    return TopUpAttempt.objects.select_for_update().get(id=attempt_id)


def lock_invoice(invoice_id):
    """
    Acquire Invoice lock.

    Use for: status transitions from webhooks.
    MUST be called within @transaction.atomic.
    """
    from apps.metering.usage.models import Invoice
    return Invoice.objects.select_for_update().get(id=invoice_id)


def lock_usage_event(event_id):
    """
    Acquire UsageEvent row lock.

    Use for: refund race protection — ensures event isn't invoiced between check and refund.
    MUST be called within @transaction.atomic.
    Raises UsageEvent.DoesNotExist if not found.
    """
    from apps.metering.usage.models import UsageEvent
    return UsageEvent.objects.select_for_update().get(id=event_id)
