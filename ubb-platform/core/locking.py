"""
Canonical lock ordering for the UBB platform.

Lock order: Wallet -> Customer -> TopUpAttempt -> Invoice -> UsageEvent

Product-specific lock helpers live in their respective apps:
- apps/billing/locking.py: lock_for_billing, lock_top_up_attempt, lock_invoice
- apps/metering/locking.py: lock_usage_event

INVARIANT: No code path may acquire locks in a different order.
All code that needs multiple locks MUST use these helpers (or their
product-specific equivalents).
"""


def lock_row(model_class, **lookup):
    """Acquire a row lock. Must be inside @transaction.atomic."""
    return model_class.objects.select_for_update().get(**lookup)


def lock_customer(customer_id):
    """
    Acquire Customer lock only.

    Use for: status changes without wallet mutation (e.g., webhook suspension).
    MUST be called within @transaction.atomic.
    """
    from apps.platform.customers.models import Customer
    return Customer.objects.select_for_update().get(id=customer_id)
