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


def _mark_invoice_payment_failed(event):
    """Stamp payment_failed_at + refresh hosted url on the matched customer invoice.

    Status-only (no money movement); account-checked; idempotent; never changes a
    terminal status. Routes by subscription presence the same way the api/v1 AR
    reconcile does. Imported lazily to avoid a circular import with api.v1.webhooks
    (which imports this module at load time).
    """
    from api.v1.webhooks import _invoice_subscription_id, _refresh_urls
    from apps.billing.invoicing.models import CustomerUsageInvoice
    from apps.subscriptions.models import SubscriptionInvoice, StripeSubscription

    inv = event.data.object
    acct = event.account
    invoice_id = getattr(inv, "id", None)
    if not acct or not invoice_id:
        return
    sub_id = _invoice_subscription_id(inv)
    if sub_id:
        sub = StripeSubscription.objects.filter(
            stripe_subscription_id=sub_id,
            tenant__stripe_connected_account_id=acct,
        ).first()
        if not sub:
            return
        with transaction.atomic():
            row = SubscriptionInvoice.objects.select_for_update().filter(
                stripe_invoice_id=invoice_id,
            ).first()
            if not row:
                return
            row.payment_failed_at = timezone.now()
            _refresh_urls(row, inv)
            row.save(update_fields=[
                "payment_failed_at", "hosted_invoice_url", "invoice_pdf", "updated_at",
            ])
    else:
        existing = CustomerUsageInvoice.objects.filter(
            stripe_invoice_id=invoice_id,
            tenant__stripe_connected_account_id=acct,
        ).first()
        if not existing:
            return
        with transaction.atomic():
            row = CustomerUsageInvoice.objects.select_for_update().get(id=existing.id)
            row.payment_failed_at = timezone.now()
            _refresh_urls(row, inv)
            row.save(update_fields=[
                "payment_failed_at", "hosted_invoice_url", "invoice_pdf", "updated_at",
            ])


def handle_invoice_payment_failed(event):
    """Handle invoice.payment_failed — stamp the invoice + suspend customer."""
    inv = event.data.object
    connected_account = event.account

    # AR: stamp payment_failed_at + refresh hosted url on the customer invoice
    # (status-only). Runs first and independently of the suspend below.
    _mark_invoice_payment_failed(event)

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
        # A suspended seat leaves the active roster: push the decremented seat
        # count to the business's subscription on commit.
        if customer.account_type == "seat" and customer.parent_id:
            from apps.subscriptions.orchestration.seats import sync_seat_quantity_on_commit
            sync_seat_quantity_on_commit(customer.parent)


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
    dispute_id = getattr(dispute, "id", None) or charge_id
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

        # Idempotency: key on dispute id (not charge id) so each distinct dispute is tracked
        from apps.billing.wallets.models import WalletTransaction
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=f"dispute:{dispute_id}",
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
            idempotency_key=f"dispute:{dispute_id}",
        )

        # Suspend customer if balance dropped below min_balance threshold
        from apps.billing.queries import get_customer_min_balance
        threshold = get_customer_min_balance(customer.id, customer.tenant_id)
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
            # A suspended seat leaves the active roster: decrement the business sub.
            if customer.account_type == "seat" and customer.parent_id:
                from apps.subscriptions.orchestration.seats import sync_seat_quantity_on_commit
                sync_seat_quantity_on_commit(customer.parent)


def handle_charge_refunded(event):
    """Handle charge.refunded — deduct wallet for Stripe-initiated refund.

    Each individual refund on the charge is processed as a separate WalletTransaction
    keyed on `stripe_refund:{refund.id}`, enabling correct handling of partial refunds
    (Stripe fires one charge.refunded event per refund, so charge-keyed idempotency
    would silently drop refund #2+).
    """
    charge = event.data.object
    charge_id = charge.id
    connected_account = event.account

    attempt = TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not attempt:
        return

    refunds_obj = getattr(charge, "refunds", None)
    refund_list = list(getattr(refunds_obj, "data", None) or [])
    if not refund_list:
        if not charge.amount_refunded:
            logger.warning(
                "Charge refunded with null/zero amount and no refund list",
                extra={"data": {"charge_id": charge_id}},
            )
            return
        # Fallback: synthesise a single entry from the top-level amount_refunded
        refund_list = [type("R", (), {"id": charge_id, "amount": charge.amount_refunded})()]

    from apps.billing.wallets.models import WalletTransaction
    from django.db import IntegrityError

    with transaction.atomic():
        wallet, customer = lock_for_billing(attempt.customer_id)

        for refund in refund_list:
            refund_id = getattr(refund, "id", None)
            refund_amount = getattr(refund, "amount", None)
            if not refund_id or not refund_amount:
                continue
            key = f"stripe_refund:{refund_id}"
            if WalletTransaction.objects.filter(wallet=wallet, idempotency_key=key).exists():
                continue
            refunded_micros = refund_amount * 10_000
            try:
                with transaction.atomic():  # savepoint for race-safe exactly-once (I2 pattern)
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type="STRIPE_REFUND",
                        amount_micros=-refunded_micros,
                        balance_after_micros=wallet.balance_micros - refunded_micros,
                        description=f"Stripe refund: {refund_id}",
                        reference_id=str(attempt.id),
                        idempotency_key=key,
                    )
            except IntegrityError:
                continue  # raced redelivery — already applied
            wallet.balance_micros -= refunded_micros
            wallet.save(update_fields=["balance_micros", "updated_at"])


def handle_payment_intent_succeeded(event):
    """Backstop: credit the wallet for a succeeded auto-topup PaymentIntent (idempotent)."""
    pi = event.data.object
    attempt_id = (getattr(pi, "metadata", None) or {}).get("topup_attempt_id")
    if not attempt_id:
        return
    from apps.billing.topups.services import AutoTopUpService
    try:
        attempt = TopUpAttempt.objects.get(id=attempt_id)
    except (TopUpAttempt.DoesNotExist, ValueError):
        return
    acct = getattr(event, "account", None)
    if acct and acct != attempt.customer.tenant.stripe_connected_account_id:
        return  # cross-account guard
    AutoTopUpService.apply_topup_credit(attempt, pi)


def handle_payment_intent_payment_failed(event):
    """Mark an auto-topup attempt failed when its PaymentIntent fails (idempotent)."""
    pi = event.data.object
    attempt_id = (getattr(pi, "metadata", None) or {}).get("topup_attempt_id")
    if not attempt_id:
        return
    try:
        attempt = TopUpAttempt.objects.get(id=attempt_id)
    except (TopUpAttempt.DoesNotExist, ValueError):
        return
    acct = getattr(event, "account", None)
    if acct and acct != attempt.customer.tenant.stripe_connected_account_id:
        return  # cross-account guard
    with transaction.atomic():
        attempt = lock_top_up_attempt(attempt.id)
        if attempt.status in ("succeeded", "failed", "superseded"):
            return
        attempt.status = "failed"
        lpe = getattr(pi, "last_payment_error", None)
        attempt.failure_reason = {"error_type": "PaymentIntentFailed",
                                  "message": getattr(lpe, "message", "") if lpe else ""}
        attempt.save(update_fields=["status", "failure_reason", "updated_at"])
