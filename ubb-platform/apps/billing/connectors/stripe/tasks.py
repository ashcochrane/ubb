import logging
import time

import stripe
from celery import shared_task
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from core.exceptions import StripeTransientError, StripePaymentError, StripeFatalError
from apps.billing.locking import lock_for_billing, lock_top_up_attempt
from apps.billing.connectors.stripe.stripe_api import charge_saved_payment_method
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import AutoTopupRequiresAction

logger = logging.getLogger(__name__)


@shared_task(
    queue="ubb_topups",
    autoretry_for=(StripeTransientError,),
    max_retries=3,
    retry_backoff=True,
    acks_late=True,
)
def charge_auto_topup_task(attempt_id):
    """
    Charge Stripe for an auto-topup attempt.

    Dispatched via transaction.on_commit after usage recording.
    Idempotent: checks attempt status before and after charging.
    """
    from apps.billing.topups.models import TopUpAttempt

    # Pre-charge check (outside transaction — no lock needed)
    try:
        attempt = TopUpAttempt.objects.get(id=attempt_id)
    except TopUpAttempt.DoesNotExist:
        logger.warning(
            "TopUpAttempt not found, skipping",
            extra={"data": {"attempt_id": str(attempt_id)}},
        )
        return

    from apps.billing.topups.models import AutoTopUpConfig
    from apps.billing.topups.services import AutoTopUpService

    # Pre-charge guard (under lock): skip if already processed OR already funded past the trigger.
    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)
        attempt = lock_top_up_attempt(attempt.id)
        if attempt.status != "pending":
            return
        cfg = AutoTopUpConfig.objects.filter(customer_id=attempt.customer_id, is_enabled=True).first()
        threshold = cfg.trigger_threshold_micros if cfg else 0
        if wallet.balance_micros >= threshold:
            attempt.status = "superseded"
            attempt.save(update_fields=["status", "updated_at"])
            logger.info("Auto top-up superseded (already funded)",
                        extra={"data": {"attempt_id": str(attempt.id)}})
            return

    # Charge Stripe (no DB lock held)
    charge_result = charge_error = None
    try:
        charge_result = charge_saved_payment_method(attempt.customer, attempt.amount_micros, attempt)
    except (StripePaymentError, StripeFatalError) as e:
        charge_error = e

    if charge_error is not None:
        if getattr(charge_error, "code", None) == "authentication_required":
            pi = getattr(charge_error, "payment_intent", None)
            with transaction.atomic():
                attempt = lock_top_up_attempt(attempt.id)
                if attempt.status != "pending":
                    return
                attempt.status = "requires_action"
                if pi is not None:
                    attempt.stripe_payment_intent_id = pi.id if hasattr(pi, "id") else pi
                attempt.failure_reason = {"error_type": "AuthenticationRequired", "code": "authentication_required"}
                attempt.save(update_fields=["status", "stripe_payment_intent_id", "failure_reason", "updated_at"])
                write_event(AutoTopupRequiresAction(
                    tenant_id=str(attempt.customer.tenant_id), customer_id=str(attempt.customer_id),
                    attempt_id=str(attempt.id), amount_micros=attempt.amount_micros, code="authentication_required"))
            return
        with transaction.atomic():
            attempt = lock_top_up_attempt(attempt.id)
            if attempt.status != "pending":
                return
            attempt.status = "failed"
            attempt.failure_reason = {
                "error_type": type(charge_error).__name__,
                "code": getattr(charge_error, "code", None),
                "decline_code": getattr(charge_error, "decline_code", None),
                "message": str(charge_error)}
            attempt.save(update_fields=["status", "failure_reason", "updated_at"])
        return

    status = getattr(charge_result, "status", "") if charge_result else ""
    if status == "succeeded":
        AutoTopUpService.apply_topup_credit(attempt, charge_result)
        return
    if status in ("requires_action", "processing"):
        logger.info("Auto top-up deferred", extra={"data": {"attempt_id": str(attempt.id), "pi_status": status}})
        return
    with transaction.atomic():
        attempt = lock_top_up_attempt(attempt.id)
        if attempt.status != "pending":
            return
        attempt.status = "failed"
        attempt.failure_reason = {"error_type": "NoPaymentMethod",
                                  "message": "No saved payment method or charge did not succeed"}
        attempt.save(update_fields=["status", "failure_reason", "updated_at"])


@shared_task(queue="ubb_billing")
def reconcile_topups_with_stripe():
    """Stripe-driven repair sweep: credit any succeeded auto-topup PaymentIntent that has no
    local wallet credit. Lookback exceeds Stripe's 3-day webhook-retry horizon so it only
    repairs genuinely-lost events. Idempotent via apply_topup_credit (auto_topup:{pi_id})."""
    from apps.billing.topups.models import TopUpAttempt
    from apps.billing.topups.services import AutoTopUpService
    from apps.billing.wallets.models import WalletTransaction
    from apps.platform.tenants.models import Tenant

    cutoff = int((timezone.now() - timedelta(days=4)).timestamp())
    repaired = 0
    accounts = (Tenant.objects.exclude(stripe_connected_account_id="")
                .exclude(stripe_connected_account_id__isnull=True)
                .values_list("stripe_connected_account_id", flat=True).distinct())
    for account in accounts:
        try:
            pis = stripe.PaymentIntent.list(created={"gte": cutoff}, limit=100, stripe_account=account)
        except stripe.error.StripeError:
            logger.warning("Reconcile: PI list failed", extra={"data": {"account": account}})
            continue
        for pi in pis.auto_paging_iter():
            attempt_id = (getattr(pi, "metadata", None) or {}).get("topup_attempt_id")
            if not attempt_id or getattr(pi, "status", "") != "succeeded":
                continue
            if WalletTransaction.objects.filter(idempotency_key=f"auto_topup:{pi.id}").exists():
                continue
            try:
                attempt = TopUpAttempt.objects.get(id=attempt_id)
            except (TopUpAttempt.DoesNotExist, ValueError):
                continue
            if AutoTopUpService.apply_topup_credit(attempt, pi):
                repaired += 1
                logger.warning("Reconcile repaired uncredited auto-topup",
                               extra={"data": {"attempt_id": str(attempt.id), "pi": pi.id}})
            time.sleep(0.1)
    if repaired:
        logger.warning("Auto-topup reconcile repaired credits", extra={"data": {"repaired": repaired}})

    # Secondary: amount/refund audit of locally-succeeded attempts (drift detection).
    from apps.platform.queries import get_tenant_stripe_account
    audit_cutoff = timezone.now() - timedelta(hours=48)
    audit_attempts = TopUpAttempt.objects.filter(
        status="succeeded", stripe_charge_id__isnull=False, updated_at__gte=audit_cutoff,
    ).select_related("customer__tenant")
    mismatches = 0
    for attempt in audit_attempts.iterator():
        try:
            charge = stripe.Charge.retrieve(
                attempt.stripe_charge_id,
                stripe_account=get_tenant_stripe_account(attempt.customer.tenant_id),
            )
        except stripe.error.StripeError:
            logger.warning("Stripe charge fetch failed", extra={"data": {
                "attempt_id": str(attempt.id), "charge_id": attempt.stripe_charge_id}})
            continue
        expected_micros = attempt.amount_micros
        actual_micros = charge.amount * 10_000
        if charge.status != "succeeded" or actual_micros != expected_micros or charge.refunded:
            mismatches += 1
            logger.error("Stripe reconciliation mismatch", extra={"data": {
                "attempt_id": str(attempt.id), "charge_id": attempt.stripe_charge_id,
                "expected_micros": expected_micros, "actual_micros": actual_micros,
                "charge_status": charge.status, "refunded": charge.refunded}})
        time.sleep(0.1)
    if mismatches > 0:
        logger.error("Stripe reconciliation completed with mismatches",
                     extra={"data": {"mismatch_count": mismatches}})
