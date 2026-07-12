import logging

from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import BalanceLow, CustomerSuspended, BalanceOverage

logger = logging.getLogger("ubb.events")


def handle_usage_recorded_billing(event_id, payload):
    """Outbox handler: deduct wallet + emit billing events.

    Registered as outbox handler with requires_product="billing".
    Called by the outbox dispatcher with (event_id, payload) signature.

    Responsibilities:
    1. Deduct wallet balance (with proper locking)
    2. Create a WalletTransaction record (idempotent via usage_event_id key)
    3. Emit BalanceOverage when balance crosses zero (winning insert only)
    4. Check min balance threshold → suspend and emit CustomerSuspended event
    5. Check auto-topup threshold → emit BalanceLow event
    6. Accumulate billing period totals

    This handler NEVER calls Stripe or dispatches payment tasks.
    Payment connectors subscribe to the emitted events.
    """
    tenant = Tenant.objects.get(id=payload["tenant_id"])
    billed_cost_micros = payload.get("cost_micros", 0)

    if billed_cost_micros > 0:
        from apps.platform.customers.models import Customer
        seat = Customer.objects.get(id=payload["customer_id"])
        if tenant.billing_mode == "postpaid":
            # Tier-2 P6b (D13): no prepaid balance to draw down, but a postpaid
            # owner that crossed its budget cap must be durably SUSPENDED so the
            # start-gate blocks new runs. Driven by the synchronous customer-wide
            # stop flag (set by record_usage_debit at the crossing) — the single
            # source of truth — so this handler is the SOLE emitter of
            # customer.suspended for postpaid too, on the winning active->
            # suspended transition (serialized on the owner Customer row).
            from apps.platform.tenants.flags import enforcing
            if enforcing(tenant):
                from apps.platform.customers.models import Customer as _Customer
                from apps.billing.gating.services.live_ledger_service import LiveLedgerService
                # Record-time-pinned owner (matches the prepaid branch) so a
                # re-parent between record_usage and this async handler can't
                # read the flag on the wrong owner.
                owner_id = payload.get("billing_owner_id") or str(seat.resolve_billing_owner().id)
                if LiveLedgerService.read_stop(owner_id, tenant)["stop"]:
                    with transaction.atomic():
                        locked = _Customer.objects.select_for_update().get(id=owner_id)
                        if locked.status == "active":
                            locked.status = "suspended"
                            locked.suspension_reason = "budget_exceeded"
                            locked.save(update_fields=["status", "suspension_reason", "updated_at"])
                            write_event(CustomerSuspended(
                                tenant_id=str(tenant.id), customer_id=str(owner_id),
                                reason="budget_exceeded", balance_micros=0))
        else:
            from apps.billing.wallets.models import WalletTransaction
            from apps.billing.wallets.grants import GrantLedger
            from apps.billing.locking import lock_for_billing
            from apps.billing.topups.models import AutoTopUpConfig
            from apps.billing.queries import get_customer_min_balance
            from django.db import IntegrityError

            owner_id = payload.get("billing_owner_id") or str(seat.resolve_billing_owner().id)
            usage_event_id = payload.get("event_id", "")
            key = f"usage_deduction:{usage_event_id}"
            with transaction.atomic():
                wallet, owner = lock_for_billing(owner_id)
                # F4.3 lazy expiry: due lots expire BEFORE the old_balance read
                # so an expired lot is never consumed by this drawdown.
                GrantLedger.expire_due(wallet)
                existing = WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).first()
                if existing is not None:
                    if existing.amount_micros != -billed_cost_micros:
                        logger.error("ledger.usage_deduction_amount_mismatch", extra={"data": {
                            "usage_event_id": usage_event_id, "existing": existing.amount_micros,
                            "expected": -billed_cost_micros}})
                    # I2: already debited -> no decrement, no events
                else:
                    old_balance = wallet.balance_micros
                    new_balance = old_balance - billed_cost_micros
                    try:
                        with transaction.atomic():  # savepoint
                            txn = WalletTransaction.objects.create(
                                wallet=wallet, transaction_type="USAGE_DEDUCTION",
                                amount_micros=-billed_cost_micros, balance_after_micros=new_balance,
                                description=f"Usage: {usage_event_id}", reference_id=usage_event_id,
                                idempotency_key=key, usage_event_id=usage_event_id or None)
                    except IntegrityError:
                        pass  # I2: raced -> already debited, no decrement, no events
                    else:
                        wallet.balance_micros = new_balance
                        wallet.save(update_fields=["balance_micros", "updated_at"])
                        # F4.3: winning branch only — lot consumption rides the
                        # usage_deduction:{event_id} exactly-once key.
                        GrantLedger.allocate(wallet, txn, billed_cost_micros)
                        limit = get_customer_min_balance(owner.id, tenant.id)
                        if old_balance >= 0 and new_balance < 0:   # I6
                            write_event(BalanceOverage(
                                tenant_id=str(tenant.id), customer_id=str(owner.id),
                                balance_micros=new_balance, overage_limit_micros=limit,
                                overage_micros=-new_balance))
                        if new_balance < -limit and owner.status == "active":
                            owner.status = "suspended"
                            owner.suspension_reason = "min_balance_exceeded"  # P6b/D15
                            owner.save(update_fields=["status", "suspension_reason", "updated_at"])
                            write_event(CustomerSuspended(
                                tenant_id=str(tenant.id), customer_id=str(owner.id),
                                reason="min_balance_exceeded", balance_micros=new_balance))
                        try:
                            config = AutoTopUpConfig.objects.get(customer=owner, is_enabled=True)
                        except AutoTopUpConfig.DoesNotExist:
                            config = None
                        if config and new_balance < config.trigger_threshold_micros:
                            write_event(BalanceLow(
                                tenant_id=str(tenant.id), customer_id=str(owner.id),
                                balance_micros=new_balance,
                                threshold_micros=config.trigger_threshold_micros,
                                suggested_topup_micros=config.top_up_amount_micros))

        # Shared tail — control + attribution stay on the SEAT:
        TenantBillingService.accumulate_usage(tenant, billed_cost_micros)
        # Budget policy: budgets are EFFECTIVE-month basis; the live Redis
        # counter tracks the CURRENT wall-clock month only. A backdated event
        # whose effective month is a PRIOR month must NOT inflate this month's
        # counter (the hourly reconcile_budget_counters rebuild — already
        # effective_at-filtered via get_customer_cost_totals — is the source
        # of truth). Absent/unparseable effective_at = legacy payload =
        # current behavior (increment).
        # Documented enforcement bypass: an enforcing-capped seat can backdate
        # usage into the prior month to evade the live cap. The exposure is
        # bounded by Tenant.backfill_window_days (0..60); tenants needing
        # airtight caps set it low — 0 disables backfill entirely.
        import datetime as _dt
        from django.utils import timezone as _tz
        from django.utils.dateparse import parse_datetime
        count_in_live = True
        raw_eff = payload.get("effective_at")
        if raw_eff:
            eff = parse_datetime(raw_eff)
            if eff is not None:
                if eff.tzinfo is not None:
                    eff = eff.astimezone(_dt.timezone.utc)
                now = _tz.now()
                count_in_live = (eff.year, eff.month) == (now.year, now.month)
        if count_in_live:
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
