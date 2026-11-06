"""Shared top-up start machinery (#78) — one replay story for the twins.

The tenant route (trigger ``manual``) and the widget route (``widget``) run
the identical flow: the required ``idempotency_key`` is unique per customer
on ``TopUpAttempt`` (``uq_top_up_attempt_idempotency``), so a retried call
re-uses the original attempt — the checkout branch re-renders its session
(Stripe's own idempotency on ``checkout-{attempt.id}`` returns the same
session) and the event branch never re-emits (attempt + outbox event land in
one transaction).

A top-up REFUSES BEFORE IT WRITES (R10 Stage C1b, F-11 + O-6, RULED Q2):
every knowable precondition of the checkout — the wallet subject, the rail,
the connected account and its charge-readiness, the amount, the currency,
the server key — is evaluated before the ``TopUpAttempt`` and its audit row
land, and each refusal answers its truthful registered problem
(``api/v1/problems.py``). Only a refusal Stripe itself makes at
``Session.create`` can arrive after the attempt exists; that one marks the
attempt ``failed`` with the reason and is answered as
``payment_not_available`` (a transient upstream inability leaves the
attempt ``pending`` for the same key to retry and answers
``service_unavailable``). Never a bare ``internal_error``, never a pending
attempt nothing will ever settle.

``checkout`` is passed in by each endpoint module so tests keep patching
``<module>.create_checkout_session`` where the route lives.
"""
import logging

from django.db import IntegrityError, transaction

from apps.platform.audit.ledger import record as audit_record
from core.exceptions import StripeFatalError, StripeNotConfigured, StripeTransientError
from core.problems import Problem
from core.responses import json_response
from core.vocabulary import (
    AUDIT_ACTION_TOP_UP_REQUESTED,
    AUDIT_RESOURCE_TYPE_WALLET,
    TOP_UP_REQUEST_STATUS_TOPUP_REQUESTED,
)

logger = logging.getLogger(__name__)


def _audit_top_up(customer, owner, tenant, attempt, payload, trigger):
    """Audit a newly-started top-up (ADR-004). Fires once per fresh attempt —
    a replay re-uses the existing attempt and never reaches here. Actor is the
    auth-seam principal: ``end_customer`` for the widget twin, the tenant
    principal for the manual one. resource_id/customer_id keep the SEAT as
    the named subject of the action (who initiated); owner_id records whose
    wallet the eventual credit will land on (Task 7)."""
    audit_record(
        action=AUDIT_ACTION_TOP_UP_REQUESTED, tenant_id=tenant.id,
        resource_type=AUDIT_RESOURCE_TYPE_WALLET, resource_id=customer.id,
        metadata={"customer_id": str(customer.id),
                  "external_id": customer.external_id,
                  "owner_id": str(owner.id),
                  "amount_micros": payload.amount_micros,
                  "trigger": trigger, "attempt_id": str(attempt.id)})


def _mark_failed(attempt_id, exc):
    """A refusal Stripe made at Session.create, after the attempt existed:
    the attempt is ``failed`` with the reason, so nothing pending is left for
    a sweep to expire or an operator to wonder about."""
    from apps.billing.locking import lock_top_up_attempt

    with transaction.atomic():
        attempt = lock_top_up_attempt(attempt_id)
        if attempt.status != "pending":
            return
        attempt.status = "failed"
        attempt.failure_reason = {
            "error": str(exc), "type": type(exc).__name__,
            "code": getattr(exc, "code", None) or "payment_not_available",
            "stage": "checkout_session_create"}
        attempt.save(update_fields=["status", "failure_reason", "updated_at"])


def start_top_up(request, customer, tenant, payload, *, trigger, checkout):
    from apps.billing.connectors.stripe.stripe_api import (
        refuse_a_checkout_that_cannot_proceed)
    from apps.billing.locking import refuse_a_wallet_operation_without_a_wallet
    from apps.billing.topups.models import TopUpAttempt
    from apps.platform.queries import get_tenant_stripe_account, get_customer_stripe_id

    # A top-up is a wallet operation that writes its attempt row (and, with
    # no connector, its outbox event) BEFORE the wallet boundary is reached,
    # so the wallet-subject rule is asked here, at the door, before any of
    # that lands: a tenant whose billing mode holds no wallet (`external`,
    # `postpaid`) registers no attempt and emits nothing. Both twins — the
    # tenant route and `/me/top-up` — pass through here.
    refuse_a_wallet_operation_without_a_wallet(tenant)

    # Task 7: pin the billing owner at creation, exactly like
    # Task.billing_owner_id / Posting.billing_owner_id — `customer` stays
    # the SEAT that initiated (both the tenant-admin and widget callers), but
    # the credit this attempt eventually produces (apply_topup_credit / the
    # checkout webhook) must land on the owner's wallet, not the seat's.
    owner = customer.resolve_billing_owner()

    if get_tenant_stripe_account(tenant.id):
        # Stripe connector is active — create checkout session
        if not get_customer_stripe_id(customer.id):
            raise Problem("conflict", "customer has no stripe_customer_id")

        # Every knowable precondition, BEFORE the attempt and its audit row
        # exist (F-11 + O-6): the rail, the connected account's
        # charge-readiness, the amount, the currency, the server key. A
        # refusal here writes nothing.
        refuse_a_checkout_that_cannot_proceed(
            customer, payload.amount_micros, owner_id=owner.id)

        attempt = TopUpAttempt.objects.filter(
            customer=customer, idempotency_key=payload.idempotency_key,
        ).first()
        if attempt is None:
            try:
                with transaction.atomic():  # attempt + audit land together
                    attempt = TopUpAttempt.objects.create(
                        customer=customer,
                        billing_owner_id=owner.id,
                        amount_micros=payload.amount_micros,
                        trigger=trigger,
                        status="pending",
                        idempotency_key=payload.idempotency_key,
                    )
                    _audit_top_up(customer, owner, tenant, attempt, payload, trigger)
            except IntegrityError:  # concurrent replay lost the race
                attempt = TopUpAttempt.objects.get(
                    customer=customer, idempotency_key=payload.idempotency_key)

        try:
            checkout_url = checkout(
                customer, attempt.amount_micros, attempt,
                success_url=payload.success_url,
                cancel_url=payload.cancel_url,
            )
        except (StripeTransientError, StripeNotConfigured) as exc:
            # Upstream could not answer right now, or the service lost its
            # key between the precondition and the call: the attempt stays
            # pending for the same idempotency_key to retry; the sweep
            # expires it if nothing ever does. Answered service_unavailable
            # (503) — the subject's state has not changed, so not `failed`.
            logger.warning("top-up checkout: payment service unavailable",
                           extra={"data": {"attempt_id": str(attempt.id),
                                           "trigger": trigger,
                                           "type": type(exc).__name__}})
            raise
        except StripeFatalError as exc:
            # Stripe's own permanent refusal of the Session (or a precondition
            # that changed between the check above and the call): the attempt
            # is failed with the reason, and the refusal is answered by name
            # (payment_not_available, or the narrower problem the subclass
            # carries) — never a bare 500 over a pending row.
            _mark_failed(attempt.id, exc)
            logger.warning("top-up checkout refused by Stripe",
                           extra={"data": {"attempt_id": str(attempt.id),
                                           "trigger": trigger, "error": str(exc),
                                           "type": type(exc).__name__}})
            raise
        return {"checkout_url": checkout_url}

    # No connector — emit an event for the tenant to handle; the attempt row
    # is the replay anchor (a replayed key answers 202 without a second event).
    # The 202 is a DECLARED answer of both routes (R10 Stage C5, F-5):
    # `TopUpAcceptedResponse`, whose `status` is the registry's closed
    # `top_up_request_status`, beside each route's own 200 checkout shape.
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import TopUpRequested

    existing = TopUpAttempt.objects.filter(
        customer=customer, idempotency_key=payload.idempotency_key,
    ).first()
    if existing is None:
        try:
            with transaction.atomic():  # attempt + event + audit land together
                attempt = TopUpAttempt.objects.create(
                    customer=customer,
                    billing_owner_id=owner.id,
                    amount_micros=payload.amount_micros,
                    trigger=trigger,
                    status="pending",
                    idempotency_key=payload.idempotency_key,
                )
                _audit_top_up(customer, owner, tenant, attempt, payload, trigger)
                write_event(TopUpRequested(
                    tenant_id=str(tenant.id),
                    customer_id=str(customer.id),
                    amount_micros=payload.amount_micros,
                    trigger=trigger,
                    success_url=getattr(payload, "success_url", "") or "",
                    cancel_url=getattr(payload, "cancel_url", "") or "",
                ))
        except IntegrityError:
            pass  # concurrent replay already wrote the attempt + event
    return json_response(
        request,
        {"status": TOP_UP_REQUEST_STATUS_TOPUP_REQUESTED,
         "message": "Top-up request sent to tenant"},
        status=202,
    )
