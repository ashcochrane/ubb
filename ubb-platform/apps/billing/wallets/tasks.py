import logging

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
