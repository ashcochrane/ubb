"""Shared top-up start machinery (#78) — one replay story for the twins.

The tenant route (trigger ``manual``) and the widget route (``widget``) run
the identical flow: the required ``idempotency_key`` is unique per customer
on ``TopUpAttempt`` (``uq_topup_attempt_idempotency``), so a retried call
re-uses the original attempt — the checkout branch re-renders its session
(Stripe's own idempotency on ``checkout-{attempt.id}`` returns the same
session) and the event branch never re-emits (attempt + outbox event land in
one transaction).

``checkout`` is passed in by each endpoint module so tests keep patching
``<module>.create_checkout_session`` where the route lives.
"""
from django.db import IntegrityError, transaction

from core.problems import Problem
from core.responses import json_response


def start_top_up(request, customer, tenant, payload, *, trigger, checkout):
    from apps.billing.topups.models import TopUpAttempt
    from apps.platform.queries import get_tenant_stripe_account, get_customer_stripe_id

    if get_tenant_stripe_account(tenant.id):
        # Stripe connector is active — create checkout session
        if not get_customer_stripe_id(customer.id):
            raise Problem("conflict", "customer has no stripe_customer_id")

        attempt = TopUpAttempt.objects.filter(
            customer=customer, idempotency_key=payload.idempotency_key,
        ).first()
        if attempt is None:
            try:
                attempt = TopUpAttempt.objects.create(
                    customer=customer,
                    amount_micros=payload.amount_micros,
                    trigger=trigger,
                    status="pending",
                    idempotency_key=payload.idempotency_key,
                )
            except IntegrityError:  # concurrent replay lost the race
                attempt = TopUpAttempt.objects.get(
                    customer=customer, idempotency_key=payload.idempotency_key)

        checkout_url = checkout(
            customer, attempt.amount_micros, attempt,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
        return {"checkout_url": checkout_url}

    # No connector — emit an event for the tenant to handle; the attempt row
    # is the replay anchor (a replayed key answers 202 without a second event).
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import TopUpRequested

    existing = TopUpAttempt.objects.filter(
        customer=customer, idempotency_key=payload.idempotency_key,
    ).first()
    if existing is None:
        try:
            with transaction.atomic():  # attempt + event land together
                TopUpAttempt.objects.create(
                    customer=customer,
                    amount_micros=payload.amount_micros,
                    trigger=trigger,
                    status="pending",
                    idempotency_key=payload.idempotency_key,
                )
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
        {"status": "topup_requested", "message": "Top-up request sent to tenant"},
        status=202,
    )
