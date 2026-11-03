import logging

import stripe
from django.db import transaction
from django.utils import timezone

from apps.platform.customers.hooks import notify_seat_roster_changed
from apps.platform.customers.models import Customer
from apps.billing.topups.models import TopUpAttempt
from apps.billing.invoicing.models import Invoice
from apps.billing.locking import lock_for_billing, lock_top_up_attempt
from apps.billing.connectors.stripe.invoice_routing import (
    _invoice_subscription_id,
    _refresh_urls,
    event_livemode,
    livemode_filter,
)
from apps.billing.stripe.services.stripe_service import (
    api_key_for_tenant, metadata_value, stripe_call)
from core.exceptions import StripeFatalError, StripeTransientError
from core.locking import lock_customer
from core.currency_policy import the_rails_currency
from core.money import from_minor
from core.vocabulary import GRANT_SOURCE_CHECKOUT

logger = logging.getLogger(__name__)

#: The two top-up triggers that run a Stripe Checkout Session (the tenant
#: route and the widget twin). Both expire after 24h (`topups/tasks.py`), and
#: both are recovered by `handle_checkout_completed` when the session
#: completes late.
CHECKOUT_TRIGGERS = ("manual", "widget")


def handle_checkout_completed(event):
    """Handle checkout.session.completed — credit wallet for top-up."""
    session = event.data.object
    if session.payment_status != "paid":
        return

    connected_account = event.account
    customer = Customer.objects.select_related("tenant").filter(
        stripe_customer_id=session.customer,
        tenant__stripe_connected_account_id=connected_account,
        **livemode_filter(event),
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

    # Handler-level idempotency: check attempt status if present. An EXPIRED
    # Checkout attempt (the tenant route's `manual` or the widget's `widget`
    # — both expire after 24h since C1b) that completes late is recovered:
    # the money was taken, so it is credited.
    if attempt and attempt.status != "pending":
        if not (attempt.status == "expired" and attempt.trigger in CHECKOUT_TRIGGERS):
            return

    # Guard null/zero amount (Stripe can send None for incomplete sessions)
    if not session.amount_total:
        logger.warning(
            "Checkout completed with null/zero amount_total",
            extra={"data": {"session_id": getattr(session, "id", None)}},
        )
        return
    # Scaled by the currency the SESSION states, never the tenant's setting
    # (§0.4 B): UBB opened it in the wallet's currency, so any other is
    # refused rather than credited at a guessed scale.
    amount_micros = from_minor(
        session.amount_total,
        the_rails_currency(f"Stripe checkout session {getattr(session, 'id', None)}",
                           getattr(session, "currency", None)))

    # Task 7: the credit must land on the billing OWNER, never the
    # Stripe-matched `customer` above (which can be a pooled seat). When a
    # TopUpAttempt correlates (the normal path — every checkout session UBB
    # creates carries client_reference_id=attempt.id), its PINNED
    # billing_owner_id is authoritative: a NULL there is a data-integrity
    # gap this webhook must refuse rather than silently credit the seat.
    # When there is NO correlating attempt (an out-of-band Checkout Session
    # this codebase didn't create), there is nothing pinned to trust or
    # distrust, so this resolves the CURRENT owner fresh — the same
    # resolver every other read/write in this bug's fix uses, and not a
    # "fall back to the seat".
    if attempt is not None:
        if attempt.billing_owner_id is None:
            logger.error(
                "TopUpAttempt missing billing_owner_id — refusing to credit",
                extra={"data": {"attempt_id": str(attempt.id), "session_id": session.id}},
            )
            raise RuntimeError(
                f"TopUpAttempt {attempt.id} has no billing_owner_id — "
                "refusing to credit rather than risk crediting the seat")
        credit_customer_id = attempt.billing_owner_id
    else:
        credit_customer_id = customer.resolve_billing_owner().id

    # Pre-fetch PaymentIntent and charge ID outside transaction (no network inside DB locks)
    pi_id = getattr(session, "payment_intent", None)
    charge_id_from_pi = None
    if isinstance(pi_id, str) and pi_id:
        # Through the wrapper (F-2): a tenant whose mode has no key configured
        # is refused BEFORE transport, and the credit below still lands — the
        # Checkout Session already took the money; only the charge id is lost.
        try:
            pi = stripe_call(
                stripe.PaymentIntent.retrieve,
                api_key=api_key_for_tenant(customer.tenant),
                id=pi_id,
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
        except (StripeTransientError, StripeFatalError, stripe.error.StripeError):
            logger.warning(
                "Failed to retrieve charge ID for reconciliation",
                extra={"data": {"payment_intent": pi_id}},
            )

    from apps.billing.wallets import operations as wallet_ops

    with transaction.atomic():
        # The wallet lock is taken FIRST (canonical Wallet -> TopUpAttempt
        # order); the read-only replay probe keeps a redelivery from touching
        # the attempt at all (parity with the pre-#109 shape). The wallet op
        # below re-enters the same lock and re-probes under it. Locks the
        # OWNER (Task 7) — `customer` is deliberately left unshadowed: the
        # receipt dispatch below still needs the SEAT (whoever's Stripe
        # customer/card was actually charged).
        from apps.billing.wallets.models import WalletTransaction
        wallet, owner = lock_for_billing(credit_customer_id)
        if WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=f"topup:{session.id}").exists():
            return

        # Re-check attempt status under lock
        if attempt:
            attempt = lock_top_up_attempt(attempt.id)
            if attempt.status != "pending":
                if not (attempt.status == "expired" and attempt.trigger in CHECKOUT_TRIGGERS):
                    return
            if attempt.status == "expired":
                logger.info(
                    "Recovering expired Checkout top-up from webhook",
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

        # The credit, its PAID lot, and the Tier-2 live mirror land behind the
        # wallet seam (#109), co-committed with the attempt walk above.
        wallet_ops.credit_top_up(
            customer_id=owner.id, tenant=customer.tenant,
            amount_micros=amount_micros,
            idempotency_key=f"topup:{session.id}",
            source=GRANT_SOURCE_CHECKOUT,
            source_reference=str(attempt.id) if attempt else session.id,
            description="Stripe top-up",
            reference_id=str(attempt.id) if attempt else "")

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


def _suspend_with_cause(owner, reason, *, measured=None):
    """Suspend a LOCKED, active billing owner for a cause no stop line opens
    (R10 Stage C2, F-6): write the status and the registry reason together,
    announce `customer.suspended` with it, and — a suspended seat leaving the
    active roster — push the decremented seat count on commit. The caller
    holds the owner's row lock and has decided the cause applies. Lifted only
    at the one reactivation site (`LiveCounter._maybe_unsuspend`)."""
    from apps.billing.gating.services.stop_signal_service import announced_balance
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import CustomerSuspended

    owner.status = "suspended"
    owner.suspension_reason = reason
    owner.save(update_fields=["status", "suspension_reason", "updated_at"])
    write_event(CustomerSuspended(
        tenant_id=str(owner.tenant_id), customer_id=str(owner.id), reason=reason,
        balance_micros=announced_balance(owner.id, owner.tenant, measured=measured)))
    if owner.account_type == "seat" and owner.parent_id:
        notify_seat_roster_changed(owner.parent)


def _mark_invoice_payment_failed(event):
    """Stamp payment_failed_at + refresh hosted url on the matched customer invoice.

    Status-only (no money movement); account-checked; idempotent; never changes a
    terminal status. Routes by subscription presence the same way the billing AR
    reconcile does; the subscription side is stamped by the subscriptions port
    (billing never touches subscriptions internals).

    Returns the id of the HISTORICAL BILLING OWNER the matched local invoice
    represents when that invoice is a STANDING failure — the customer the
    suspension below targets (R10 Stage C2, RULED Q4 a, PLAN §7 item 27): a
    usage invoice's own `customer`, a subscription invoice's `billing_owner`,
    both fixed when the invoice entered UBB and never re-derived from today's
    topology. None when no local usage/subscription invoice matches the
    Stripe invoice (Q4 c: nobody is suspended), and None for a matched invoice
    already paid or void: a late failure event on a settled invoice is stamped
    as before but suspends nobody.
    """
    from apps.billing.connectors.stripe.invoice_routing import SETTLED_PAYMENT_STATUSES
    from apps.billing.invoicing.models import CustomerUsageInvoice
    from apps.subscriptions.ports import mark_invoice_payment_failed_for_subscription

    inv = event.data.object
    acct = event.account
    invoice_id = getattr(inv, "id", None)
    if not acct or not invoice_id:
        return None
    sub_id = _invoice_subscription_id(inv)
    if sub_id:
        return mark_invoice_payment_failed_for_subscription(
            acct, sub_id, invoice_id, inv, livemode=event_livemode(event))
    existing = CustomerUsageInvoice.objects.filter(
        stripe_invoice_id=invoice_id,
        tenant__stripe_connected_account_id=acct,
        **livemode_filter(event),
    ).first()
    if not existing:
        return None
    with transaction.atomic():
        row = CustomerUsageInvoice.objects.select_for_update().get(id=existing.id)
        row.payment_failed_at = timezone.now()
        _refresh_urls(row, inv)
        row.save(update_fields=[
            "payment_failed_at", "hosted_invoice_url", "invoice_pdf", "updated_at",
        ])
        if row.payment_status in SETTLED_PAYMENT_STATUSES:
            return None
        # THE HISTORICAL OWNER (PLAN §7 item 27): a usage invoice's own
        # `customer` IS the billing owner it was issued to (the claim keys the
        # row on it, I5) — never re-derived from today's topology.
        return row.customer_id


def handle_invoice_payment_failed(event):
    """Handle invoice.payment_failed — stamp the local invoice + suspend the
    billing owner it represents (R10 Stage C2, F-6, RULED Q4).

    The suspension targets the canonical billing owner of the MATCHED LOCAL
    usage/subscription invoice — never whichever local customer happens to
    carry the Stripe customer id — writes `suspension_reason = payment_failed`
    and emits `customer.suspended`, so the suspension says why and the AR
    clear (`LiveCounter.clear_payment_failed_suspension`) can tell it apart
    from a money suspension. A Stripe payment-failure event with no matching
    local invoice suspends nobody. Applies in every mode: a payment failure
    is not a spend control.

    The stamp commits first, and the owner's standing is read only under its
    row lock: an owner suspended for another cause keeps that cause (the
    reactivation site will not lift it while this failure stands, and hands
    it over to `payment_failed`), and an owner a concurrent clear just made
    active is suspended here.
    """
    from apps.platform.work import reasons

    owner_id = _mark_invoice_payment_failed(event)
    if owner_id is None:
        return
    with transaction.atomic():
        owner = lock_customer(owner_id)
        if owner.status != "active":
            return
        _suspend_with_cause(owner, reasons.PAYMENT_FAILED)


def handle_charge_dispute_created(event):
    """Handle charge.dispute.created — flag affected top-up for manual review."""
    dispute = event.data.object
    charge_id = dispute.charge
    connected_account = event.account

    attempt = TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=connected_account,
        **livemode_filter(event, tenant_path="customer__tenant"),
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
        **livemode_filter(event, tenant_path="customer__tenant"),
    ).first()
    if not attempt:
        return

    if not dispute.amount:
        logger.warning(
            "Dispute closed with null/zero amount",
            extra={"data": {"charge_id": charge_id}},
        )
        return
    from apps.billing.wallets import operations as wallet_ops

    tenant = attempt.customer.tenant
    # Stripe's minor units -> micros, in the currency the DISPUTE states
    # (§0.4 B) — never the tenant's setting; any other is refused.
    amount_micros = from_minor(
        dispute.amount,
        the_rails_currency(f"Stripe dispute on charge {charge_id}",
                           getattr(dispute, "currency", None)))

    # Task 8a: this clawback moves money OUT. The original top-up's credit
    # landed on the billing OWNER (Task 7); clawing it back from the seat
    # instead would mint a phantom seat wallet, drive it negative, and leave
    # the business holding a credit that was never actually reversed. Same
    # NULL-refusal failure mode as the credit path — never silently fall
    # back to attempt.customer_id (the seat).
    if attempt.billing_owner_id is None:
        logger.error(
            "TopUpAttempt missing billing_owner_id — refusing to claw back",
            extra={"data": {"attempt_id": str(attempt.id), "dispute_id": dispute_id}},
        )
        raise RuntimeError(
            f"TopUpAttempt {attempt.id} has no billing_owner_id — "
            "refusing to claw back rather than risk debiting the seat")
    owner_id = attempt.billing_owner_id

    with transaction.atomic():
        # Deduct + clawback cascade behind the wallet seam (#109), keyed on
        # the dispute id (not charge id) so each distinct dispute is tracked.
        result = wallet_ops.claw_back_dispute(
            customer_id=owner_id, tenant=tenant,
            amount_micros=amount_micros, dispute_id=dispute_id,
            charge_id=charge_id, attempt_id=attempt.id)
        if result.outcome != "applied":
            return

        # Suspend the OWNER if balance dropped below min_balance threshold —
        # a Customer-status policy, so it stays with the webhook (the op's
        # customer-row lock is held until this outer transaction commits).
        # Suspending the owner (not the seat) is what RiskService.check
        # actually reads for every seat funded by this wallet.
        from apps.billing.queries import get_customer_min_balance
        from core.crossing import past_floor
        from apps.platform.work import reasons
        owner = Customer.objects.select_for_update().get(id=owner_id)
        threshold = get_customer_min_balance(owner.id, owner.tenant_id)
        if past_floor(result.balance_micros, threshold) and owner.status == "active":
            # R10 Stage C2 (F-6): the suspension says why — `dispute_lost`,
            # a registry reason — and announces itself. It clears ONLY by the
            # durable balance-recovery rule (the balance back at or above this
            # same floor — `LiveCounter.BALANCE_SUSPEND_REASONS`), never
            # because an invoice became paid or void.
            _suspend_with_cause(owner, reasons.DISPUTE_LOST,
                                measured=result.balance_micros)
            logger.warning(
                "Customer suspended after dispute deduction",
                extra={"data": {
                    "customer_id": str(owner.id),
                    "balance_micros": result.balance_micros,
                    "threshold": threshold,
                }},
            )


def _attempt_for_charge(event, charge_id):
    """The top-up attempt a Stripe charge paid for, bound to the connected
    account and mode the event came from (one attempt <-> one charge)."""
    return TopUpAttempt.objects.filter(
        stripe_charge_id=charge_id,
        customer__tenant__stripe_connected_account_id=event.account,
        **livemode_filter(event, tenant_path="customer__tenant"),
    ).first()


def _owner_of(attempt, charge_id):
    """Task 8a: the claw-back must debit whichever wallet the original top-up
    credit landed on (the billing OWNER, pinned at attempt creation), never
    the seat — the same shape and failure mode as the dispute handler."""
    if attempt.billing_owner_id is None:
        logger.error(
            "TopUpAttempt missing billing_owner_id — refusing to claw back",
            extra={"data": {"attempt_id": str(attempt.id), "charge_id": charge_id}},
        )
        raise RuntimeError(
            f"TopUpAttempt {attempt.id} has no billing_owner_id — "
            "refusing to claw back rather than risk debiting the seat")
    return attempt.billing_owner_id


def handle_charge_refunded(event):
    """charge.refunded — claw back exactly the increment Stripe has refunded
    (R10 Stage C1b, RULED Q15; design in the Stage C plan §5.1b).

    The authoritative facts are on the event's Charge: ``id``, ``currency``
    and the CUMULATIVE ``amount_refunded`` (present on every Charge). The
    ledger holds the durable applied sum per charge (the ``stripe_refund``
    rows referencing the attempt), and the wallet op applies the positive
    difference exactly once, keyed on the cumulative level
    (``stripe_refund:{charge_id}:{amount_refunded}``). When the Charge
    carries an expanded ``refunds.data`` (older API versions or an
    expansion), the per-refund facts are applied instead, each keyed
    ``stripe_refund:{refund_id}`` and reconciled against the SAME applied
    sum, with any remainder (a truncated list) applied on the cumulative
    key — so the two families can never double-apply. Processing never
    depends on ``refunds`` being expanded and makes no outbound call.

    A zero increment (duplicate delivery, an already-applied level) moves
    nothing; a NEGATIVE one (Stripe's cumulative below the applied sum: an
    out-of-order older event, or a refund that later failed — Q19) is a
    structured ERROR and moves nothing. The claw-back applies when the
    cumulative increases, including while the refund is still ``pending``
    (RULED Q20) — never deferred to a later ``succeeded`` update. Currency
    is the Charge's (or the refund's own), through ``the_rails_currency``:
    USD only (ADR-0023), a foreign currency refuses by name and moves
    nothing. The F4.3 grant cascade and the owner-wallet targeting are the
    wallet op's and unchanged.
    """
    charge = event.data.object
    charge_id = charge.id
    attempt = _attempt_for_charge(event, charge_id)
    if not attempt:
        return

    amount_refunded = getattr(charge, "amount_refunded", None)
    refunds_obj = getattr(charge, "refunds", None)
    refund_list = list(getattr(refunds_obj, "data", None) or [])
    if not amount_refunded and not refund_list:
        logger.warning(
            "Charge refunded with null/zero amount_refunded and no refund list",
            extra={"data": {"charge_id": charge_id}},
        )
        return

    from apps.billing.wallets import operations as wallet_ops

    tenant = attempt.customer.tenant
    owner_id = _owner_of(attempt, charge_id)
    charge_currency = the_rails_currency(
        f"Stripe charge {charge_id}", getattr(charge, "currency", None))
    # Where the Charge states its cumulative, that is the level to converge
    # to; a Charge shape without it (only an expanded list) converges to the
    # list's own sum.
    if amount_refunded:
        cumulative_micros = from_minor(amount_refunded, charge_currency)
    else:
        cumulative_micros = sum(
            from_minor(getattr(r, "amount", 0) or 0, the_rails_currency(
                f"Stripe refund {getattr(r, 'id', None)}", getattr(r, "currency", None)))
            for r in refund_list)

    with transaction.atomic():
        # One commit for the whole event; each movement is its own
        # exactly-once wallet op, every one reconciled under the wallet lock
        # against the applied sum the previous one left. A refused op (the
        # cumulative below the applied sum) has already logged the one
        # structured ERROR with every identifier; nothing moves.
        for refund in refund_list:
            refund_id = getattr(refund, "id", None)
            refund_amount = getattr(refund, "amount", None)
            if not refund_id or not refund_amount:
                continue
            wallet_ops.claw_back_stripe_refund(
                customer_id=owner_id, tenant=tenant,
                cumulative_micros=cumulative_micros,
                # In the currency each REFUND states (§0.4 B).
                refund_micros=from_minor(refund_amount, the_rails_currency(
                    f"Stripe refund {refund_id}", getattr(refund, "currency", None))),
                key=f"stripe_refund:{refund_id}", charge_id=charge_id,
                attempt_id=attempt.id)
        # The cumulative level: the only movement when no refund ids are
        # present; the remainder (a truncated list) otherwise; a no-op when
        # the per-refund keys already brought the applied sum to the level.
        if amount_refunded:
            wallet_ops.claw_back_stripe_refund(
                customer_id=owner_id, tenant=tenant,
                cumulative_micros=cumulative_micros,
                key=f"stripe_refund:{charge_id}:{amount_refunded}",
                charge_id=charge_id, attempt_id=attempt.id)


REFUND_REVERSAL_STATUSES = ("failed", "canceled")


def handle_charge_refund_updated(event):
    """charge.refund.updated — ALERT-ONLY (R10 Stage C1b, RULED Q19).

    A refund that later becomes ``failed`` or ``canceled`` means money UBB
    clawed back on the cumulative increase (Q20) is staying with the
    customer after all. UBB never re-credits automatically: an automatic
    re-credit is a new compensating money movement needing its own durable
    identity, replay semantics and audit contract, and C1b does not invent
    one. This handler detects the condition, emits ONE structured ERROR
    carrying the tenant/customer/charge/refund identifiers, the status and
    the amounts (no secrets), and leaves the wallet unchanged — the
    cumulative decrease that accompanies it is refused by the claw-back op
    (``REFUND_TOTAL_BELOW_APPLIED``), never applied.

    THE KNOWN v1 OPERATIONAL RECOVERY PATH, not automatic refund reversal:
    an accountable operator verifies the Stripe fact (the Refund's status in
    the Dashboard or ``Refund.retrieve``) and, where a re-credit is
    warranted, uses the existing supported credit path
    (``POST /api/v1/billing/customers/{id}/credit`` with a movement reason
    and an idempotency key). No new wallet transaction type and no reversal
    workflow exist for it. Any other refund status (``pending``,
    ``succeeded``, ``requires_action``) is nothing to act on here.
    """
    refund = event.data.object
    status = getattr(refund, "status", None)
    if status not in REFUND_REVERSAL_STATUSES:
        return
    charge_ref = getattr(refund, "charge", None)
    charge_id = charge_ref if isinstance(charge_ref, str) else getattr(charge_ref, "id", None)
    attempt = _attempt_for_charge(event, charge_id) if charge_id else None
    if not attempt:
        return

    from apps.billing.wallets import operations as wallet_ops

    tenant = attempt.customer.tenant
    owner_id = attempt.billing_owner_id
    logger.error(
        "Stripe refund reversed after claw-back — operator recovery required "
        "(no automatic re-credit; verify the refund in Stripe, then use the "
        "supported credit path if a re-credit is warranted)",
        extra={"data": {
            "alert": "stripe_refund_reversed",
            "tenant_id": str(tenant.id),
            "customer_id": str(attempt.customer_id),
            "owner_id": str(owner_id) if owner_id else None,
            "attempt_id": str(attempt.id),
            "charge_id": charge_id,
            "refund_id": getattr(refund, "id", None),
            "refund_status": status,
            "failure_reason": getattr(refund, "failure_reason", None),
            "refund_amount_minor": getattr(refund, "amount", None),
            "refund_currency": getattr(refund, "currency", None),
            "applied_micros": (wallet_ops.stripe_refund_applied_micros_for(owner_id, attempt.id)
                               if owner_id else None),
            "event_id": getattr(event, "id", None),
        }},
    )


def handle_payment_intent_succeeded(event):
    """Backstop: credit the wallet for a succeeded auto top-up PaymentIntent (idempotent)."""
    pi = event.data.object
    # A real PaymentIntent's metadata is a StripeObject, not a dict (F-3a).
    attempt_id = metadata_value(pi, "topup_attempt_id")
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
    if attempt.customer.tenant.is_sandbox == event_livemode(event):
        return  # cross-MODE guard (F4.4): acct_ ids are identical in test+live
    AutoTopUpService.apply_topup_credit(attempt, pi)


def handle_payment_intent_payment_failed(event):
    """Mark an auto top-up attempt failed when its PaymentIntent fails (idempotent)."""
    pi = event.data.object
    attempt_id = metadata_value(pi, "topup_attempt_id")
    if not attempt_id:
        return
    try:
        attempt = TopUpAttempt.objects.get(id=attempt_id)
    except (TopUpAttempt.DoesNotExist, ValueError):
        return
    acct = getattr(event, "account", None)
    if acct and acct != attempt.customer.tenant.stripe_connected_account_id:
        return  # cross-account guard
    if attempt.customer.tenant.is_sandbox == event_livemode(event):
        return  # cross-MODE guard (F4.4): acct_ ids are identical in test+live
    with transaction.atomic():
        attempt = lock_top_up_attempt(attempt.id)
        if attempt.status in ("succeeded", "failed", "superseded"):
            return
        attempt.status = "failed"
        lpe = getattr(pi, "last_payment_error", None)
        attempt.failure_reason = {"error_type": "PaymentIntentFailed",
                                  "message": getattr(lpe, "message", "") if lpe else ""}
        attempt.save(update_fields=["status", "failure_reason", "updated_at"])
