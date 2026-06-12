import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_invoicing")
def reconcile_wallet_balances():
    """Reconcile wallet balances against WalletTransaction ledger.

    F4.3 extensions (grant txns are ordinary WalletTransactions, so the
    ledger-sum check still holds unchanged):
    - per-grant conservation: granted == remaining + sum(allocations)
      + expired_micros + voided_micros
    - per-wallet G1: sum(remaining of active grants) <= max(balance, 0)
    """
    from apps.billing.wallets.models import CreditGrant, Wallet, WalletTransaction
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

        active_grant_sum = CreditGrant.objects.filter(
            wallet=wallet, status="active",
        ).aggregate(total=Sum("remaining_micros"))["total"] or 0
        if active_grant_sum > max(wallet.balance_micros, 0):
            drift_count += 1
            logger.error(
                "Grant remaining drift detected: active grants exceed spendable balance",
                extra={"data": {
                    "wallet_id": str(wallet.id),
                    "customer_id": str(wallet.customer_id),
                    "active_grant_remaining": active_grant_sum,
                    "cached_balance": wallet.balance_micros,
                    "excess": active_grant_sum - max(wallet.balance_micros, 0),
                }},
            )

    grant_drift_count = 0
    grants_checked = 0
    for grant in CreditGrant.objects.all().iterator():
        allocated = grant.allocations.aggregate(total=Sum("amount_micros"))["total"] or 0
        grants_checked += 1
        expected = grant.remaining_micros + allocated + grant.expired_micros + grant.voided_micros
        if grant.granted_micros != expected:
            grant_drift_count += 1
            logger.error(
                "Credit grant ledger drift detected",
                extra={"data": {
                    "grant_id": str(grant.id),
                    "wallet_id": str(grant.wallet_id),
                    "granted_micros": grant.granted_micros,
                    "remaining_micros": grant.remaining_micros,
                    "allocated_micros": allocated,
                    "expired_micros": grant.expired_micros,
                    "voided_micros": grant.voided_micros,
                    "drift": grant.granted_micros - expected,
                }},
            )

    logger.info(
        "Wallet reconciliation complete",
        extra={"data": {"wallets_checked": wallets_checked, "drift_count": drift_count,
                        "grants_checked": grants_checked,
                        "grant_drift_count": grant_drift_count}},
    )


GRACE = timedelta(hours=6)       # > the live outbox retry/DLQ horizon (~2h43m: backoff 30s,2m,10m,30m,2h x5) + headroom
LOOKBACK = timedelta(days=7)
REPAIR_SPIKE_THRESHOLD = 25


@shared_task(queue="ubb_invoicing")
def reconcile_usage_drawdowns():
    """Source-of-truth repair: apply missing usage debits exactly-once.
    Anti-joins on WalletTransaction.usage_event_id (cutover-safe). Owner pinned on the event.

    Scans on ARRIVAL basis (created_at, F4.2): the DLQ horizon is an
    arrival-time concept — a backfilled event with effective_at 30 days ago is
    INSERTED now, so it must be repair-eligible now, not invisible because its
    effective age predates the lookback. basis="created" keeps the window
    unchanged (GRACE..LOOKBACK after insertion) for every event regardless of
    its effective timestamp; the (tenant, created_at) index supports the scan."""
    from django.db import transaction, IntegrityError
    from apps.platform.tenants.models import Tenant
    from apps.platform.customers.models import Customer
    from apps.metering.queries import iter_billable_usage_events
    from apps.billing.wallets.models import Wallet, WalletTransaction
    from apps.billing.locking import lock_for_billing

    now = timezone.now()
    settled_before = now - GRACE
    since = now - LOOKBACK
    repaired = 0
    for tenant in Tenant.objects.filter(billing_mode="prepaid", is_active=True):
        for ev in iter_billable_usage_events(tenant.id, since, settled_before, basis="created"):
            owner_id = ev["billing_owner_id"]
            if owner_id is None:  # defensive: pre-backfill row -> re-resolve via the shared resolver (parity with the live path)
                cust = Customer.objects.filter(id=ev["customer_id"]).first()
                owner_id = cust.resolve_billing_owner().id if cust else ev["customer_id"]
            ow = Wallet.objects.filter(customer_id=owner_id).first()
            if ow and WalletTransaction.objects.filter(
                    wallet=ow, usage_event_id=ev["id"], transaction_type="USAGE_DEDUCTION").exists():
                continue  # already debited (column anti-join, cutover-safe)
            key = f"usage_deduction:{ev['id']}"
            with transaction.atomic():
                wallet, owner = lock_for_billing(owner_id)
                # F4.3 lazy expiry: same as the live drawdown twin — due lots
                # expire BEFORE the balance read so repair never consumes them.
                from apps.billing.wallets.grants import GrantLedger
                GrantLedger.expire_due(wallet)
                existing = WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).first()
                if existing is not None:
                    if existing.amount_micros != -ev["billed_cost_micros"]:
                        logger.error("ledger.usage_deduction_amount_mismatch", extra={"data": {
                            "usage_event_id": str(ev["id"]), "existing": existing.amount_micros,
                            "expected": -ev["billed_cost_micros"]}})
                    continue
                new_balance = wallet.balance_micros - ev["billed_cost_micros"]
                try:
                    with transaction.atomic():
                        txn = WalletTransaction.objects.create(
                            wallet=wallet, transaction_type="USAGE_DEDUCTION",
                            amount_micros=-ev["billed_cost_micros"], balance_after_micros=new_balance,
                            description=f"Usage (reconciled): {ev['id']}", reference_id=str(ev["id"]),
                            idempotency_key=key, usage_event_id=ev["id"])
                except IntegrityError:
                    continue  # raced with the live drawdown -> already debited
                wallet.balance_micros = new_balance
                wallet.save(update_fields=["balance_micros", "updated_at"])
                GrantLedger.allocate(wallet, txn, ev["billed_cost_micros"])  # winning branch only
                repaired += 1
                logger.warning("wallet.drawdown_repaired", extra={"data": {
                    "usage_event_id": str(ev["id"]), "owner_id": str(owner_id),
                    "amount_micros": -ev["billed_cost_micros"]}})
                # I12: do NOT re-fire CustomerSuspended / balance_overage on a back-correction
    if repaired:
        logger.warning("wallet.drawdown_repair_summary", extra={"data": {"repaired": repaired}})
        if repaired >= REPAIR_SPIKE_THRESHOLD:
            logger.error("wallet.drawdown_repair_spike", extra={"data": {"repaired": repaired}})


GRANT_WARNING_WINDOW = timedelta(days=7)


@shared_task(queue="ubb_invoicing")
def expire_credit_grants():
    """Beat (hourly :10): expire due credit grants + warn on soon-to-expire.

    Pass 1 — for each wallet holding active grants with expires_at <= now:
    lock_for_billing + GrantLedger.expire_due. Exactly-once per grant via the
    expiry:{grant_id} WalletTransaction key; lazy expiry in the drawdown paths
    makes this beat a sweeper, not a correctness requirement.

    Pass 2 — warning: active grants expiring within GRANT_WARNING_WINDOW that
    were never warned. Winning-update one-shot: filter(...).update(
    warning_sent_at=now) rowcount==1 emits CreditGrantExpiring in the same
    atomic — concurrent beats can't double-fire.
    """
    from django.db import transaction
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.grants import GrantLedger
    from apps.billing.wallets.models import CreditGrant
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import CreditGrantExpiring

    now = timezone.now()

    # Pass 1 — expiry.
    customer_ids = list(CreditGrant.objects.filter(
        status="active", expires_at__isnull=False, expires_at__lte=now,
    ).values_list("wallet__customer_id", flat=True).distinct())
    expired_wallets = 0
    for customer_id in customer_ids:
        with transaction.atomic():
            wallet, _customer = lock_for_billing(customer_id)
            GrantLedger.expire_due(wallet, now=now)
        expired_wallets += 1

    # Pass 2 — expiring-soon warnings.
    warned = 0
    pending = CreditGrant.objects.filter(
        status="active", warning_sent_at__isnull=True,
        expires_at__isnull=False, expires_at__lte=now + GRANT_WARNING_WINDOW,
    ).select_related("wallet")
    for grant in pending.iterator():
        with transaction.atomic():
            updated = CreditGrant.objects.filter(
                id=grant.id, warning_sent_at__isnull=True,
            ).update(warning_sent_at=now)
            if updated == 1:
                write_event(CreditGrantExpiring(
                    tenant_id=str(grant.tenant_id),
                    customer_id=str(grant.wallet.customer_id),
                    grant_id=str(grant.id),
                    kind=grant.kind,
                    remaining_micros=grant.remaining_micros,
                    expires_at=grant.expires_at.isoformat(),
                ))
                warned += 1
    if expired_wallets or warned:
        logger.info("credit_grants.beat_complete", extra={"data": {
            "wallets_swept": expired_wallets, "warnings_sent": warned}})
