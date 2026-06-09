import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_invoicing")
def reconcile_wallet_balances():
    """Reconcile wallet balances against WalletTransaction ledger."""
    from apps.billing.wallets.models import Wallet, WalletTransaction
    from django.db.models import Sum

    wallets = Wallet.objects.all()
    drift_count = 0
    wallets_checked = 0
    for wallet in wallets.iterator():
        ledger_sum = WalletTransaction.objects.filter(
            wallet=wallet,
        ).aggregate(total=Sum("amount_micros"))["total"] or 0

        wallets_checked += 1
        if wallet.balance_micros != ledger_sum:
            drift_count += 1
            logger.error(
                "Wallet balance drift detected",
                extra={"data": {
                    "wallet_id": str(wallet.id),
                    "customer_id": str(wallet.customer_id),
                    "cached_balance": wallet.balance_micros,
                    "ledger_balance": ledger_sum,
                    "drift": wallet.balance_micros - ledger_sum,
                }},
            )

    logger.info(
        "Wallet reconciliation complete",
        extra={"data": {"wallets_checked": wallets_checked, "drift_count": drift_count}},
    )


GRACE = timedelta(hours=6)       # > the live outbox retry/DLQ horizon (~2h43m: backoff 30s,2m,10m,30m,2h x5) + headroom
LOOKBACK = timedelta(days=7)
REPAIR_SPIKE_THRESHOLD = 25


@shared_task(queue="ubb_invoicing")
def reconcile_usage_drawdowns():
    """Source-of-truth repair: apply missing usage debits exactly-once.
    Anti-joins on WalletTransaction.usage_event_id (cutover-safe). Owner pinned on the event."""
    from django.db import transaction, IntegrityError
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from apps.metering.usage.models import UsageEvent
    from apps.billing.wallets.models import Wallet, WalletTransaction
    from apps.billing.locking import lock_for_billing

    now = timezone.now()
    settled_before = now - GRACE
    since = now - LOOKBACK
    repaired = 0
    for tenant in Tenant.objects.filter(billing_mode="prepaid", is_active=True):
        events = UsageEvent.objects.filter(
            tenant=tenant, billed_cost_micros__gt=0,
            effective_at__gte=since, effective_at__lt=settled_before)
        for ev in events.iterator():
            owner_id = ev.billing_owner_id
            if owner_id is None:  # defensive: pre-backfill row -> re-resolve via the shared resolver (parity with the live path)
                cust = Customer.objects.filter(id=ev.customer_id).first()
                owner_id = cust.resolve_billing_owner().id if cust else ev.customer_id
            ow = Wallet.objects.filter(customer_id=owner_id).first()
            if ow and WalletTransaction.objects.filter(
                    wallet=ow, usage_event_id=ev.id, transaction_type="USAGE_DEDUCTION").exists():
                continue  # already debited (column anti-join, cutover-safe)
            key = f"usage_deduction:{ev.id}"
            with transaction.atomic():
                wallet, owner = lock_for_billing(owner_id)
                existing = WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).first()
                if existing is not None:
                    if existing.amount_micros != -ev.billed_cost_micros:
                        logger.error("ledger.usage_deduction_amount_mismatch", extra={"data": {
                            "usage_event_id": str(ev.id), "existing": existing.amount_micros,
                            "expected": -ev.billed_cost_micros}})
                    continue
                new_balance = wallet.balance_micros - ev.billed_cost_micros
                try:
                    with transaction.atomic():
                        WalletTransaction.objects.create(
                            wallet=wallet, transaction_type="USAGE_DEDUCTION",
                            amount_micros=-ev.billed_cost_micros, balance_after_micros=new_balance,
                            description=f"Usage (reconciled): {ev.id}", reference_id=str(ev.id),
                            idempotency_key=key, usage_event_id=ev.id)
                except IntegrityError:
                    continue  # raced with the live drawdown -> already debited
                wallet.balance_micros = new_balance
                wallet.save(update_fields=["balance_micros", "updated_at"])
                repaired += 1
                logger.warning("wallet.drawdown_repaired", extra={"data": {
                    "usage_event_id": str(ev.id), "owner_id": str(owner_id),
                    "amount_micros": -ev.billed_cost_micros}})
                # I12: do NOT re-fire CustomerSuspended / balance_overage on a back-correction
    if repaired:
        logger.warning("wallet.drawdown_repair_summary", extra={"data": {"repaired": repaired}})
        if repaired >= REPAIR_SPIKE_THRESHOLD:
            logger.error("wallet.drawdown_repair_spike", extra={"data": {"repaired": repaired}})
