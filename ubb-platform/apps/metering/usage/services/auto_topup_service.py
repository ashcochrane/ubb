import logging

from django.db import IntegrityError, transaction

from apps.platform.customers.models import AutoTopUpConfig, TopUpAttempt

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
