"""
Metering-specific lock helpers.

See core/locking.py for canonical lock ordering:
    Wallet -> Customer -> TopUpAttempt -> Invoice -> UsageEvent
"""


def lock_usage_event(event_id):
    """
    Acquire UsageEvent row lock.

    Use for: refund race protection -- ensures event isn't invoiced between check and refund.
    MUST be called within @transaction.atomic.
    Raises UsageEvent.DoesNotExist if not found.
    """
    from apps.metering.usage.models import UsageEvent
    return UsageEvent.objects.select_for_update().get(id=event_id)
