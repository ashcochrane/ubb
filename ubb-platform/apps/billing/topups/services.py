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
                    # `customer` here is already the billing owner (the
                    # caller locked it via lock_for_billing(owner_id) off a
                    # BalanceLow event keyed to the owner) — resolving again
                    # is a no-op for that case and keeps this creation site
                    # correct even if a future caller ever passed a seat.
                    billing_owner_id=customer.resolve_billing_owner().id,
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
        Exactly-once via WalletTransaction idempotency_key=auto_topup:{pi_id}. Returns True if it credited.

        #109 co-commit pattern: the outer atomic nests the wallet op, then
        locks + saves the TopUpAttempt keyed on ``outcome == "applied"`` — one
        commit, wallet→attempt lock order preserved. The TOP_UP row, the PAID
        CreditGrant lot (expiry from the owner's
        CustomerBillingProfile.topup_grant_expiry_days) and the Tier-2 live
        mirror all live behind the wallet seam."""
        from apps.billing.locking import lock_top_up_attempt
        from apps.billing.wallets import operations as wallet_ops

        pi_id = payment_intent.id if hasattr(payment_intent, "id") else payment_intent["id"]
        key = f"auto_topup:{pi_id}"
        lc = getattr(payment_intent, "latest_charge", None)
        charge_id = (lc.id if hasattr(lc, "id") else lc) if lc else None
        amount_micros = attempt.amount_micros

        # Task 7: credit the PINNED owner, never the seat. Every creation
        # path in this codebase sets billing_owner_id — a NULL here is a
        # data-integrity gap, not a normal state, and must be refused loudly
        # rather than silently defaulting to attempt.customer_id (the seat),
        # which would reproduce the exact phantom-wallet bug this pin exists
        # to prevent.
        if attempt.billing_owner_id is None:
            raise RuntimeError(
                f"TopUpAttempt {attempt.id} has no billing_owner_id — "
                "refusing to credit rather than risk crediting the seat")

        with transaction.atomic():
            result = wallet_ops.credit_top_up(
                customer_id=attempt.billing_owner_id, tenant=attempt.customer.tenant,
                amount_micros=amount_micros, idempotency_key=key,
                source="auto_topup", source_reference=str(attempt.id),
                description="Auto top-up", reference_id=str(attempt.id))
            if result.outcome != "applied":
                return False
            attempt = lock_top_up_attempt(attempt.id)
            attempt.status = "succeeded"
            attempt.stripe_payment_intent_id = pi_id
            fields = ["status", "stripe_payment_intent_id", "updated_at"]
            if charge_id:
                attempt.stripe_charge_id = charge_id
                fields.append("stripe_charge_id")
            attempt.save(update_fields=fields)
            return True
