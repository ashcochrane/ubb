import logging

from django.db import IntegrityError, transaction

from apps.billing.topups.models import AutoTopUpConfig, TopUpAttempt

logger = logging.getLogger(__name__)


class AutoTopUpService:
    @staticmethod
    def create_pending_attempt(customer, wallet):
        """
        Check auto-topup eligibility and create a pending TopUpAttempt.

        MUST be called within @transaction.atomic with wallet already locked
        via lock_for_billing().

        Returns TopUpAttempt if created, None if skipped (not eligible or
        another pending attempt already exists).
        """
        try:
            config = customer.auto_top_up_config
        except AutoTopUpConfig.DoesNotExist:
            return None

        if not config.is_enabled:
            return None

        if wallet.balance_micros >= config.trigger_threshold_micros:
            return None

        logger.info(
            "Auto top-up triggered",
            extra={"data": {
                "customer_id": str(customer.id),
                "balance_micros": wallet.balance_micros,
                "threshold_micros": config.trigger_threshold_micros,
            }},
        )

        # Savepoint: IntegrityError must not abort the outer transaction
        try:
            with transaction.atomic():
                attempt = TopUpAttempt.objects.create(
                    customer=customer,
                    amount_micros=config.top_up_amount_micros,
                    trigger="auto_topup",
                    status="pending",
                )
            return attempt
        except IntegrityError:
            # Another pending auto-topup already exists
            logger.info(
                "Auto top-up skipped: pending attempt exists",
                extra={"data": {"customer_id": str(customer.id)}},
            )
            return None

    @staticmethod
    def apply_topup_credit(attempt, payment_intent) -> bool:
        """Idempotently credit the wallet for a succeeded auto-topup PaymentIntent.
        Convergent: called by the charge task, the payment_intent.succeeded webhook, and reconcile.
        Exactly-once via WalletTransaction idempotency_key=auto_topup:{pi_id}. Returns True if it credited."""
        from apps.billing.locking import lock_for_billing, lock_top_up_attempt
        from apps.billing.wallets.models import WalletTransaction

        pi_id = payment_intent.id if hasattr(payment_intent, "id") else payment_intent["id"]
        key = f"auto_topup:{pi_id}"
        lc = getattr(payment_intent, "latest_charge", None)
        charge_id = (lc.id if hasattr(lc, "id") else lc) if lc else None
        amount_micros = attempt.amount_micros

        with transaction.atomic():
            wallet, customer = lock_for_billing(attempt.customer_id)
            if WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).exists():
                return False
            attempt = lock_top_up_attempt(attempt.id)
            new_balance = wallet.balance_micros + amount_micros
            try:
                with transaction.atomic():  # savepoint: race backstop on the unique constraint
                    WalletTransaction.objects.create(
                        wallet=wallet, transaction_type="TOP_UP", amount_micros=amount_micros,
                        balance_after_micros=new_balance, description="Auto top-up",
                        reference_id=str(attempt.id), idempotency_key=key)
            except IntegrityError:
                return False
            wallet.balance_micros = new_balance
            wallet.save(update_fields=["balance_micros", "updated_at"])
            attempt.status = "succeeded"
            attempt.stripe_payment_intent_id = pi_id
            fields = ["status", "stripe_payment_intent_id", "updated_at"]
            if charge_id:
                attempt.stripe_charge_id = charge_id
                fields.append("stripe_charge_id")
            attempt.save(update_fields=fields)
            return True
