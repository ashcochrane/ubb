import logging

from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService

logger = logging.getLogger("ubb.events")


def handle_usage_recorded_billing(event_id, payload):
    """Outbox handler: deduct wallet + emit billing events.

    Registered as outbox handler with requires_product="billing".
    Called by the outbox dispatcher with (event_id, payload) signature.

    Responsibilities:
    1. Deduct wallet balance (with proper locking)
    2. Create a WalletTransaction record
    3. Check min balance threshold → suspend and emit CustomerSuspended event
    4. Check auto-topup threshold → emit BalanceLow event
    5. Accumulate billing period totals

    This handler NEVER calls Stripe or dispatches payment tasks.
    Payment connectors subscribe to the emitted events.
    """
    tenant = Tenant.objects.get(id=payload["tenant_id"])
    billed_cost_micros = payload.get("cost_micros", 0)

    if billed_cost_micros > 0:
        from apps.platform.customers.models import Customer
        seat = Customer.objects.get(id=payload["customer_id"])
        if tenant.billing_mode == "postpaid":
            pass  # no prepaid balance to draw down
        else:
            from apps.billing.wallets.models import WalletTransaction
            from apps.billing.locking import lock_for_billing
            from apps.billing.topups.models import AutoTopUpConfig
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import BalanceLow, CustomerSuspended
            from apps.billing.accounts import resolve_billing_owner_id

            owner_id = resolve_billing_owner_id(seat)
            with transaction.atomic():
                wallet, owner = lock_for_billing(owner_id)
                wallet.balance_micros -= billed_cost_micros
                wallet.save(update_fields=["balance_micros", "updated_at"])
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type="USAGE_DEDUCTION",
                    amount_micros=-billed_cost_micros,
                    balance_after_micros=wallet.balance_micros,
                    description=f"Usage: {payload.get('event_id', '')}",
                    reference_id=payload.get("event_id", ""),
                    idempotency_key=f"usage_deduction:{event_id}",
                )

                # Check min balance threshold and suspend if needed
                from apps.billing.queries import get_customer_min_balance
                threshold = get_customer_min_balance(owner.id, tenant.id)
                if wallet.balance_micros < -threshold and owner.status == "active":
                    owner.status = "suspended"
                    owner.save(update_fields=["status", "updated_at"])
                    write_event(CustomerSuspended(
                        tenant_id=str(tenant.id),
                        customer_id=str(owner.id),
                        reason="min_balance_exceeded",
                        balance_micros=wallet.balance_micros,
                    ))

                # Check auto-topup threshold → emit BalanceLow
                try:
                    config = AutoTopUpConfig.objects.get(
                        customer=owner, is_enabled=True
                    )
                except AutoTopUpConfig.DoesNotExist:
                    config = None

                if config and wallet.balance_micros < config.trigger_threshold_micros:
                    write_event(BalanceLow(
                        tenant_id=str(tenant.id),
                        customer_id=str(owner.id),
                        balance_micros=wallet.balance_micros,
                        threshold_micros=config.trigger_threshold_micros,
                        suggested_topup_micros=config.top_up_amount_micros,
                    ))

        # Shared tail — control + attribution stay on the SEAT:
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)
        from apps.billing.gating.services.budget_service import BudgetService
        BudgetService.record_usage_spend(seat, billed_cost_micros)


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
