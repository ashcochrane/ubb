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

THE SAME CORE SERVES THE OPERATOR (R10 Stage C4, PLAN §7 item 36). Once an
event is authenticated, ``process_stripe_event`` does steps 2-4 on its
receiver-scoped ``StripeWebhookEvent`` row and answers an outcome; the HTTP
view turns the outcome into the response Stripe reads. The
``reprocess_webhook`` command runs the SAME function on the SAME row with
the Event it retrieved from Stripe, so a delivery and an operator re-run are
arbitrated by one CAS and dispatched by one handler map. That map lives with
each endpoint, and the billing one in the composition layer, which no
product module may import (ADR-001). So each endpoint module REGISTERS its
receiver here as it loads (``register_receiver``), and the command reads the
registry rather than importing the endpoint.
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

#: What processing one authenticated event came to. The HTTP view answers
#: each as Stripe expects (``_ANSWERS``); the operator command reports it.
OUTCOME_ALREADY_RECEIVED = "already_received"
OUTCOME_ALREADY_PROCESSING = "already_processing"
OUTCOME_ALREADY_PROCESSED = "already_processed"
OUTCOME_SKIPPED = "skipped"
OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED_RETRYABLE = "failed_retryable"
OUTCOME_FAILED = "failed"

#: The registered receivers: name -> (a zero-argument callable answering the
#: handler map, whether a wallet-subject refusal is a named outcome there).
_RECEIVERS = {}


def register_receiver(receiver, *, handlers, refuses_without_a_wallet_subject):
    """Declare how ``receiver`` dispatches, for callers that hold an Event
    but not the endpoint (the ``reprocess_webhook`` command).

    Called by each endpoint module as it loads. ``handlers`` is a callable
    returning that module's handler map, read at call time as the view reads
    it. Re-registering replaces the entry (a module may be reloaded).
    """
    if receiver not in WEBHOOK_RECEIVERS:
        raise ValueError(f"unknown Stripe webhook receiver {receiver!r}")
    _RECEIVERS[receiver] = (handlers, refuses_without_a_wallet_subject)


def registered_receiver(receiver):
    """``(handler map, refuses_without_a_wallet_subject)`` for ``receiver``,
    or None when no endpoint module in this process registered it."""
    entry = _RECEIVERS.get(receiver)
    if entry is None:
        return None
    handlers, refuses = entry
    return handlers(), refuses


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

    return _ANSWERS[process_stripe_event(
        event, receiver=receiver, handlers=handlers,
        refuses_without_a_wallet_subject=refuses_without_a_wallet_subject)]()


def process_stripe_event(event, *, receiver, handlers, refuses_without_a_wallet_subject):
    """Steps 2-4 for one AUTHENTICATED event: claim its receiver-scoped row
    (dedup + CAS), dispatch it to ``handlers``, record the result on that row,
    and answer the ``OUTCOME_*`` it came to.

    The webhook view calls this after verifying the signature; the
    ``reprocess_webhook`` command calls it with the Event it retrieved from
    Stripe. Both meet the same row and the same CAS, so a redelivery racing
    an operator re-run applies the business effect once: whichever claims
    the row first runs the handler, and the other is answered
    ``already_processing`` or ``already_processed``.
    """
    if receiver not in WEBHOOK_RECEIVERS:
        raise ValueError(f"unknown Stripe webhook receiver {receiver!r}")

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
        return OUTCOME_ALREADY_RECEIVED

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
                return OUTCOME_ALREADY_PROCESSING
            # Won CAS — fall through to handler
        else:
            scoped.update(
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            return OUTCOME_ALREADY_PROCESSED

    # 3. Dispatch — this receiver's map only. A type it does not own is
    # recorded `skipped` HERE and only here; the owning receiver's row is a
    # different row.
    handler = handlers.get(event.type)
    if not handler:
        webhook_event.status = "skipped"
        webhook_event.save(update_fields=["status", "updated_at"])
        return OUTCOME_SKIPPED

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
        return OUTCOME_FAILED_RETRYABLE  # Stripe retries
    except StripeFatalError as e:
        logger.error(
            "Webhook handler fatal error",
            extra={"data": {**log, "error": str(e)}},
        )
        _record_failure(webhook_event, e, retryable=False)
        return OUTCOME_FAILED  # 200 — no Stripe retry
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
        return OUTCOME_FAILED  # 200 — no Stripe retry
    except Exception as e:
        logger.exception(
            "Webhook handler transient error",
            extra={"data": log},
        )
        _record_failure(webhook_event, e, retryable=True)
        return OUTCOME_FAILED_RETRYABLE  # Stripe retries

    return OUTCOME_SUCCEEDED


#: The HTTP answer for each outcome — what Stripe reads: a 500 is retried,
#: every 200 is final for that delivery.
_ANSWERS = {
    OUTCOME_ALREADY_RECEIVED: lambda: JsonResponse({"status": "already_received"}),
    OUTCOME_ALREADY_PROCESSING: lambda: JsonResponse({"status": "already_processing"}),
    OUTCOME_ALREADY_PROCESSED: lambda: JsonResponse({"status": "already_processed"}),
    OUTCOME_SKIPPED: lambda: JsonResponse({"status": "ok"}),
    OUTCOME_SUCCEEDED: lambda: JsonResponse({"status": "ok"}),
    OUTCOME_FAILED_RETRYABLE: lambda: HttpResponse(status=500),
    OUTCOME_FAILED: lambda: JsonResponse({"status": "failed"}),
}


def _record_failure(webhook_event, exc, *, retryable):
    webhook_event.status = "failed"
    webhook_event.failure_reason = {
        "error": str(exc), "type": type(exc).__name__, "retryable": retryable,
    }
    webhook_event.processed_at = timezone.now()
    webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
