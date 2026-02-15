import logging

import stripe
from django.db import transaction
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.billing.topups.models import TopUpAttempt
from apps.billing.invoicing.models import Invoice
from apps.billing.locking import lock_for_billing, lock_top_up_attempt
from core.locking import lock_customer

logger = logging.getLogger(__name__)


def handle_checkout_completed(event):
    """Handle checkout.session.completed — credit wallet for top-up."""
    session = event.data.object
    if session.payment_status != "paid":
        return

    connected_account = event.account
    customer = Customer.objects.filter(
        stripe_customer_id=session.customer,
        tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not customer:
        return

    # Correlate with TopUpAttempt via client_reference_id
    attempt = None
    if session.client_reference_id:
        try:
            attempt = TopUpAttempt.objects.get(id=session.client_reference_id)
        except TopUpAttempt.DoesNotExist:
            logger.warning(
                "TopUpAttempt not found for checkout session",
                extra={"data": {"client_reference_id": session.client_reference_id}},
            )

    # Handler-level idempotency: check attempt status if present
    if attempt and attempt.status != "pending":
        if not (attempt.status == "expired" and attempt.trigger == "manual"):
            return

    # Guard null/zero amount (Stripe can send None for incomplete sessions)
    if not session.amount_total:
        logger.warning(
            "Checkout completed with null/zero amount_total",
            extra={"data": {"session_id": getattr(session, "id", None)}},
        )
        return
    amount_micros = session.amount_total * 10_000

    # Pre-fetch PaymentIntent and charge ID outside transaction (no network inside DB locks)
    pi_id = getattr(session, "payment_intent", None)
    charge_id_from_pi = None
    if isinstance(pi_id, str) and pi_id:
        try:
            pi = stripe.PaymentIntent.retrieve(
                pi_id,
                stripe_account=connected_account,
                expand=["latest_charge"],
            )
            if pi.latest_charge:
                cid = (
                    pi.latest_charge.id
                    if hasattr(pi.latest_charge, "id")
                    else pi.latest_charge
                )
                if isinstance(cid, str) and cid:
                    charge_id_from_pi = cid
        except stripe.error.StripeError:
            logger.warning(
                "Failed to retrieve charge ID for reconciliation",
                extra={"data": {"payment_intent": pi_id}},
            )

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Idempotency: check for existing top-up transaction
        from apps.billing.wallets.models import WalletTransaction
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=f"topup:{session.id}",
        ).first()
        if existing:
            return

        # Re-check attempt status under lock
        if attempt:
            attempt = lock_top_up_attempt(attempt.id)
            if attempt.status != "pending":
                if not (attempt.status == "expired" and attempt.trigger == "manual"):
                    return
            if attempt.status == "expired":
                logger.info(
                    "Recovering expired manual top-up from webhook",
                    extra={"data": {"attempt_id": str(attempt.id), "session_id": session.id}},
                )
            attempt.status = "succeeded"
            attempt.stripe_checkout_session_id = session.id
            save_fields = ["status", "stripe_checkout_session_id", "updated_at"]
            if isinstance(pi_id, str) and pi_id:
                attempt.stripe_payment_intent_id = pi_id
                save_fields.append("stripe_payment_intent_id")
                if charge_id_from_pi:
                    attempt.stripe_charge_id = charge_id_from_pi
                    save_fields.append("stripe_charge_id")
            attempt.save(update_fields=save_fields)

        wallet.balance_micros += amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="TOP_UP",
            amount_micros=amount_micros,
            balance_after_micros=wallet.balance_micros,
            description="Stripe top-up",
            reference_id=str(attempt.id) if attempt else "",
            idempotency_key=f"topup:{session.id}",
        )

    # Generate receipt invoice (after commit)
    if attempt:
        transaction.on_commit(lambda: _dispatch_receipt(customer.id, attempt.id))


def _dispatch_receipt(customer_id, attempt_id):
    from apps.platform.customers.models import Customer
    from apps.billing.topups.models import TopUpAttempt
    from apps.billing.connectors.stripe.receipts import ReceiptService
    try:
        customer = Customer.objects.select_related("tenant").get(id=customer_id)
        attempt = TopUpAttempt.objects.get(id=attempt_id)
        ReceiptService.create_topup_receipt(customer, attempt)
    except Exception:
        logger.exception(
            "Failed to generate top-up receipt",
            extra={"data": {"customer_id": str(customer_id), "attempt_id": str(attempt_id)}},
        )


def handle_invoice_payment_failed(event):
    """Handle invoice.payment_failed — suspend customer."""
    inv = event.data.object
    connected_account = event.account
    customer = Customer.objects.filter(
        stripe_customer_id=inv.customer,
        tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not customer:
        return

    # Handler-level idempotency: already suspended = skip
    if customer.status == "suspended":
        return

    with transaction.atomic():
        customer = lock_customer(customer.id)
        if customer.status == "suspended":
            return
        customer.status = "suspended"
        customer.save(update_fields=["status", "updated_at"])


def handle_charge_dispute_created(event):
    """Handle charge.dispute.created — flag affected top-up for manual review."""
    dispute = event.data.object
    charge_id = dispute.charge
    connected_account = event.account

    attempt = TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not attempt:
        logger.warning(
            "Dispute for unknown charge",
            extra={"data": {"charge_id": charge_id}},
        )
        return

    logger.error(
        "Stripe dispute opened on top-up",
        extra={"data": {
            "attempt_id": str(attempt.id),
            "charge_id": charge_id,
            "amount": dispute.amount,
            "reason": dispute.reason,
        }},
    )


def handle_charge_dispute_closed(event):
    """Handle charge.dispute.closed — auto-deduct wallet if dispute lost."""
    dispute = event.data.object
    charge_id = dispute.charge
    connected_account = event.account

    if dispute.status != "lost":
        return  # Won or withdrawn — no action

    attempt = TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not attempt:
        return

    if not dispute.amount:
        logger.warning(
            "Dispute closed with null/zero amount",
            extra={"data": {"charge_id": charge_id}},
        )
        return
    amount_micros = dispute.amount * 10_000  # Stripe cents -> micros

    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)

        # Idempotency: check for existing dispute deduction
        from apps.billing.wallets.models import WalletTransaction
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=f"dispute:{charge_id}",
        ).first()
        if existing:
            return

        wallet.balance_micros -= amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="DISPUTE_DEDUCTION",
            amount_micros=-amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Dispute lost: {charge_id}",
            reference_id=str(attempt.id),
            idempotency_key=f"dispute:{charge_id}",
        )

        # Suspend customer if balance dropped below min_balance threshold
        threshold = customer.get_min_balance()
        if wallet.balance_micros < -threshold and customer.status == "active":
            customer.status = "suspended"
            customer.save(update_fields=["status", "updated_at"])
            logger.warning(
                "Customer suspended after dispute deduction",
                extra={"data": {
                    "customer_id": str(customer.id),
                    "balance_micros": wallet.balance_micros,
                    "threshold": threshold,
                }},
            )


def handle_charge_refunded(event):
    """Handle charge.refunded — deduct wallet for Stripe-initiated refund."""
    charge = event.data.object
    charge_id = charge.id
    connected_account = event.account

    attempt = TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not attempt:
        return

    if not charge.amount_refunded:
        logger.warning(
            "Charge refunded with null/zero amount_refunded",
            extra={"data": {"charge_id": charge_id}},
        )
        return
    refunded_micros = charge.amount_refunded * 10_000

    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)

        from apps.billing.wallets.models import WalletTransaction
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=f"stripe_refund:{charge_id}",
        ).first()
        if existing:
            return

        wallet.balance_micros -= refunded_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="STRIPE_REFUND",
            amount_micros=-refunded_micros,
            balance_after_micros=wallet.balance_micros,
            description=f"Stripe refund: {charge_id}",
            reference_id=str(attempt.id),
            idempotency_key=f"stripe_refund:{charge_id}",
        )
