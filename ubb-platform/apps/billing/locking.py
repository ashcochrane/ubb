"""
Billing-specific lock helpers.

See core/locking.py for canonical lock ordering:
    Wallet -> Customer -> TopUpAttempt -> Invoice -> UsageEvent

These helpers enforce the ordering for billing operations.
"""
from core.locking import lock_row


def lock_for_billing(customer_id):
    """
    Acquire Wallet -> Customer locks in canonical order.
    Creates the Wallet lazily if it doesn't exist yet.

    Use for: usage recording, wallet credits/debits, suspension checks.
    MUST be called within @transaction.atomic.
    """
    from apps.billing.wallets.models import Wallet
    from apps.platform.customers.models import Customer

    wallet = Wallet.all_objects.select_for_update().filter(customer_id=customer_id).first()
    if wallet is None:
        wallet = Wallet.objects.create(customer_id=customer_id, balance_micros=0, currency="USD")
    elif wallet.deleted_at is not None:
        wallet.restore()
    customer = Customer.objects.select_for_update().get(id=customer_id)
    return wallet, customer


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
    from apps.billing.invoicing.models import Invoice
    return Invoice.objects.select_for_update().get(id=invoice_id)
