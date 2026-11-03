"""The one Stripe webhook receiver core, shared by both endpoints (R10 Stage
C1b, F-17; part of the "Stripe connector kit", ADR-001 decision 5).

Two Stripe endpoints exist — the billing receiver (``api/v1/webhooks.py``)
and the subscriptions receiver (``apps/subscriptions/api/endpoints.py``) —
each registered with Stripe for the event types it owns and each verified
with its own signing secret. Until C1b their bodies were two copies of the
same ~130 lines over one dedup table keyed on the Stripe event id alone, so
a type registered on both endpoints was processed by whichever copy won the
row and silently ``skipped`` by the other, and a retryable failure on the
owning receiver was buried under the other's row. This module is that body
once, parameterised by what genuinely differs between the two receivers:

- ``receiver`` — the closed registry value (``WEBHOOK_RECEIVERS``) that
  scopes deduplication: ``StripeWebhookEvent`` is unique per
  ``(receiver, stripe_event_id)``, so the same event id reaching both
  endpoints is processed by its owner and recorded by the other,
  independently, and a redelivery to one receiver stays exactly-once there;
- ``handlers`` — that receiver's handler map, read at call time so a test
  may patch the endpoint module's map;
- ``secret`` — that receiver's own signing secret, chosen by the endpoint
  view (live or test mode). The view fails closed on a blank one BEFORE
  calling here; this core verifies with exactly what it is handed and never
  falls back to another receiver's secret;
- ``refuses_without_a_wallet_subject`` — whether ``NoWalletSubjectError``
  is a named, non-retryable outcome (the billing receiver moves wallet
  money; the subscriptions receiver never does, so there it would be an
  ordinary failure).

Everything else — signature verification, the F4.4 mode gate, the
get-or-create dedup with the IntegrityError race fallback, the CAS retry
of retryable failures and stale ``processing`` rows, dispatch, and the
error classification that decides whether Stripe retries — is identical by
construction, because it is one function.
"""
import logging
from datetime import timedelta

import stripe
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.billing.connectors.stripe.invoice_routing import reject_for_mode
from apps.billing.stripe.models import WEBHOOK_RECEIVERS, StripeWebhookEvent
from core.exceptions import NoWalletSubjectError, StripeFatalError

logger = logging.getLogger(__name__)

#: A ``processing`` row older than this is presumed abandoned (a crashed
#: worker) and may be re-claimed by the next delivery through the CAS below.
PROCESSING_TTL_MINUTES = 30


def receive_stripe_event(request, *, receiver, handlers, secret, is_test_endpoint,
                         refuses_without_a_wallet_subject):
    """Verify, deduplicate (per receiver), dispatch and classify one delivery.

    ``secret`` must already be known non-blank: the endpoint views refuse a
    blank one with 400 before calling, so an empty key can never verify.
    """
    if receiver not in WEBHOOK_RECEIVERS:
        raise ValueError(f"unknown Stripe webhook receiver {receiver!r}")
    if not (secret or "").strip():
        # Belt and braces for the views' own fail-closed check: this core
        # never hands the verifier an empty key.
        return HttpResponse(status=400)

    # 1. Verify signature — with THIS receiver's secret only.
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    # 1b. Mode gate (F4.4): test endpoint = test events only; live endpoint
    # rejects test events once the test secret (= sandbox infra) exists.
    if reject_for_mode(event, is_test_endpoint=is_test_endpoint):
        return HttpResponse(status=400)

    # 2. Event-level dedup, scoped to the receiver, with IntegrityError handling
    scoped = StripeWebhookEvent.objects.filter(
        receiver=receiver, stripe_event_id=event.id)
    try:
        with transaction.atomic():
            webhook_event, created = StripeWebhookEvent.objects.get_or_create(
                receiver=receiver, stripe_event_id=event.id,
                defaults={"event_type": event.type, "status": "processing"},
            )
    except IntegrityError:
        scoped.update(
            duplicate_count=F("duplicate_count") + 1,
            last_seen_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return JsonResponse({"status": "already_received"})

    if not created:
        processing_ttl = timezone.now() - timedelta(minutes=PROCESSING_TTL_MINUTES)

        # CAS: allow retry of retryable failures or stale processing
        if (
            (webhook_event.status == "failed"
             and webhook_event.failure_reason
             and webhook_event.failure_reason.get("retryable") is True)
            or (webhook_event.status == "processing"
                and webhook_event.updated_at < processing_ttl)
        ):
            rows_updated = StripeWebhookEvent.objects.filter(
                id=webhook_event.id,
                status=webhook_event.status,
                updated_at=webhook_event.updated_at,
            ).update(
                status="processing",
                failure_reason=None,
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            if rows_updated == 0:
                return JsonResponse({"status": "already_processing"})
            # Won CAS — fall through to handler
        else:
            scoped.update(
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            return JsonResponse({"status": "already_processed"})

    # 3. Dispatch — this receiver's map only. A type it does not own is
    # recorded `skipped` HERE and only here; the owning receiver's row is a
    # different row.
    handler = handlers.get(event.type)
    if not handler:
        webhook_event.status = "skipped"
        webhook_event.save(update_fields=["status", "updated_at"])
        return JsonResponse({"status": "ok"})

    log = {"receiver": receiver, "event_id": event.id, "event_type": event.type}

    # 4. Execute with error classification
    try:
        handler(event)
        webhook_event.status = "succeeded"
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "processed_at", "updated_at"])
    except ObjectDoesNotExist as e:
        logger.warning(
            "Webhook handler ObjectDoesNotExist (likely out-of-order)",
            extra={"data": {**log, "error": str(e)}},
        )
        _record_failure(webhook_event, e, retryable=True)
        return HttpResponse(status=500)  # Stripe retries
    except StripeFatalError as e:
        logger.error(
            "Webhook handler fatal error",
            extra={"data": {**log, "error": str(e)}},
        )
        _record_failure(webhook_event, e, retryable=False)
        return JsonResponse({"status": "failed"})  # 200 — no Stripe retry
    except NoWalletSubjectError as e:
        if not refuses_without_a_wallet_subject:
            raise  # not an outcome this receiver names; see the generic arm
        # The wallet boundary refused: the matched tenant's billing mode holds
        # no wallet (`external`, `postpaid`), so there is no wallet for this
        # money to land on or leave — an out-of-band Checkout Session, or a
        # dispute/refund/payment on an attempt whose tenant has since left
        # `prepaid`. Nothing a retry could change: recorded on the event row
        # by name as a NON-retryable failure and acknowledged, so Stripe never
        # loops on it. The money stays where Stripe holds it, for the tenant.
        logger.error(
            "Webhook handler refused: no wallet subject",
            extra={"data": {**log, "error": str(e), "billing_mode": e.billing_mode}},
        )
        _record_failure(webhook_event, e, retryable=False)
        return JsonResponse({"status": "failed"})  # 200 — no Stripe retry
    except Exception as e:
        logger.exception(
            "Webhook handler transient error",
            extra={"data": log},
        )
        _record_failure(webhook_event, e, retryable=True)
        return HttpResponse(status=500)  # Stripe retries

    return JsonResponse({"status": "ok"})


def _record_failure(webhook_event, exc, *, retryable):
    webhook_event.status = "failed"
    webhook_event.failure_reason = {
        "error": str(exc), "type": type(exc).__name__, "retryable": retryable,
    }
    webhook_event.processed_at = timezone.now()
    webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
