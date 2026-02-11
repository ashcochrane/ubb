import logging

from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService

logger = logging.getLogger("ubb.events")


def handle_usage_recorded_billing(event_id, payload):
    """Outbox handler: deduct wallet + accumulate billing period + auto-topup.

    Registered as outbox handler with requires_product="billing".
    Called by the outbox dispatcher with (event_id, payload) signature.

    Responsibilities:
    1. Deduct wallet balance (with proper locking)
    2. Create a WalletTransaction record
    3. Check arrears threshold and suspend customer if needed
    4. Check auto-topup eligibility and dispatch charge if needed
    5. Accumulate billing period totals
    """
    tenant = Tenant.objects.get(id=payload["tenant_id"])
    billed_cost_micros = payload.get("cost_micros", 0)

    if billed_cost_micros > 0:
        from apps.billing.wallets.models import WalletTransaction
        from apps.billing.locking import lock_for_billing
        from apps.billing.topups.services import AutoTopUpService

        with transaction.atomic():
            # lock_for_billing acquires locks in canonical order: Wallet -> Customer
            wallet, customer = lock_for_billing(payload["customer_id"])

            wallet.balance_micros -= billed_cost_micros
            wallet.save(update_fields=["balance_micros", "updated_at"])

            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type="USAGE_DEDUCTION",
                amount_micros=-billed_cost_micros,
                balance_after_micros=wallet.balance_micros,
                description=f"Usage: {payload.get('event_id', '')}",
                reference_id=payload.get("event_id", ""),
            )

            # Check arrears threshold and suspend if needed
            threshold = customer.get_arrears_threshold()
            if wallet.balance_micros < -threshold and customer.status == "active":
                customer.status = "suspended"
                customer.save(update_fields=["status", "updated_at"])

            # Check auto-topup eligibility (wallet is already locked)
            attempt = AutoTopUpService.create_pending_attempt(customer, wallet)

        # Accumulate billing period (outside the wallet lock)
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)

        # Dispatch auto-topup charge task if attempt was created
        if attempt:
            from apps.billing.stripe.tasks import charge_auto_topup_task
            transaction.on_commit(
                lambda aid=str(attempt.id): charge_auto_topup_task.delay(aid)
            )


def handle_customer_deleted_billing(event_id, payload):
    """Outbox handler: clean up billing resources when customer is deleted.

    Registered as outbox handler with requires_product="billing".
    Soft-deletes Wallet and AutoTopUpConfig for the customer.
    """
    customer_id = payload["customer_id"]

    from apps.billing.wallets.models import Wallet
    from apps.billing.topups.models import AutoTopUpConfig

    try:
        Wallet.objects.get(customer_id=customer_id).soft_delete()
    except Wallet.DoesNotExist:
        pass
    try:
        AutoTopUpConfig.objects.get(customer_id=customer_id).soft_delete()
    except AutoTopUpConfig.DoesNotExist:
        pass
