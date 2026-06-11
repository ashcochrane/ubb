"""
True multi-thread concurrency tests for the Stripe webhook endpoint (F1.2).

Uses TransactionTestCase (NOT @pytest.mark.django_db) so that setup data is
committed before worker threads start, and workers can see each other's
transactions through real Postgres row locking.  Each worker closes its
thread-local DB connection in a finally: block; a threading.Barrier(2) forces
both workers into the critical section simultaneously, maximising the race
window.  Harness cloned from apps/billing/tests/test_concurrency_races.py.

Invariants asserted:
    (a) Event-level dedup — two simultaneous deliveries of the SAME event id
        yield exactly one StripeWebhookEvent row and apply the handler effect
        exactly once; one response is "ok", the other is the dedup vocabulary
        ("already_received" via IntegrityError, "already_processed" /
        "already_processing" via the CAS path).
    (b) AR transition table under concurrency — invoice.finalized and
        invoice.paid for the SAME Stripe invoice (distinct event ids) end
        paid in EVERY interleaving: paid-then-finalized must not regress to
        open, and the money fields gate on the applied state.
"""

import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone

from apps.billing.stripe.models import StripeWebhookEvent
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from api.v1.webhooks import stripe_webhook

DEDUP_VOCAB = {"already_received", "already_processed", "already_processing"}


def _sub_inv_obj(stripe_invoice_id, subscription_id, *, amount_paid=4900,
                 hosted_url="", pdf=""):
    """Stripe invoice payload shaped like the builders in test_ar_reconcile.py."""
    return SimpleNamespace(
        id=stripe_invoice_id,
        subscription=subscription_id,
        parent=None,
        amount_paid=amount_paid,
        currency="usd",
        hosted_invoice_url=hosted_url,
        invoice_pdf=pdf,
        period_start=1738368000,
        period_end=1740960000,
        status_transitions=SimpleNamespace(paid_at=1738400000),
    )


def _event(event_id, event_type, account, obj):
    return SimpleNamespace(
        id=event_id, type=event_type, account=account,
        data=SimpleNamespace(object=obj),
    )


def _fixtures(name, acct, sub_id):
    tenant = Tenant.objects.create(
        name=name, products=["metering", "subscriptions"],
        stripe_connected_account_id=acct,
    )
    customer = Customer.objects.create(tenant=tenant, external_id=f"{name}_c1")
    now = timezone.now()
    StripeSubscription.objects.create(
        tenant=tenant, customer=customer,
        stripe_subscription_id=sub_id,
        stripe_product_name="Pro", status="active",
        amount_micros=49_000_000, currency="usd", interval="month",
        current_period_start=now, current_period_end=now, last_synced_at=now,
    )
    return tenant, customer


class ConcurrentWebhookDedup(TransactionTestCase):
    """Race (a): two threads deliver the SAME Stripe event id simultaneously —
    exactly one StripeWebhookEvent row, the handler effect applied once."""

    def test_same_event_delivered_twice_processes_once(self):
        _fixtures("RACE_WH_DEDUP", "acct_race_dedup", "sub_race_dedup")
        event = _event(
            "evt_race_dedup", "invoice.paid", "acct_race_dedup",
            _sub_inv_obj("in_race_dedup", "sub_race_dedup"),
        )

        factory = RequestFactory()
        barrier = threading.Barrier(2)
        responses = []
        errors = []

        def worker():
            try:
                request = factory.post(
                    "/api/v1/webhooks/stripe/", data="{}",
                    content_type="application/json",
                )
                barrier.wait()
                response = stripe_webhook(request)
                responses.append(
                    (response.status_code, json.loads(response.content)))
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        with patch("api.v1.webhooks.stripe.Webhook.construct_event",
                   return_value=event):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [], f"workers raised unexpected exceptions: {errors}")
        self.assertEqual(len(responses), 2)

        # Both HTTP responses valid: exactly one "ok", the other dedup vocabulary.
        statuses = [body["status"] for code, body in responses]
        for code, _body in responses:
            self.assertEqual(code, 200)
        self.assertEqual(
            statuses.count("ok"), 1,
            f"expected exactly one 'ok' response, got {statuses}",
        )
        other = next(s for s in statuses if s != "ok")
        self.assertIn(other, DEDUP_VOCAB, f"unexpected dedup response {other!r}")

        # Exactly one dedup row, with the duplicate counted.
        self.assertEqual(
            StripeWebhookEvent.objects.filter(
                stripe_event_id="evt_race_dedup").count(),
            1,
        )

        # Handler effect applied once: one row, paid once.
        rows = SubscriptionInvoice.objects.filter(stripe_invoice_id="in_race_dedup")
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.status, "paid")
        self.assertIsNotNone(row.paid_at)
        self.assertEqual(row.amount_paid_micros, 49_000_000)


class ConcurrentARDelivery(TransactionTestCase):
    """Race (b): invoice.finalized (event A) races invoice.paid (event B) for
    the SAME Stripe invoice — in EVERY interleaving the row ends paid with
    paid_at set and the correct amount (paid-then-finalized must not regress
    to open per the AR transition table)."""

    def test_finalized_races_paid_row_ends_paid(self):
        _fixtures("RACE_WH_AR", "acct_race_ar", "sub_race_ar")
        events = {
            b"FIN": _event(
                "evt_race_fin", "invoice.finalized", "acct_race_ar",
                _sub_inv_obj("in_race_ar", "sub_race_ar", amount_paid=0,
                             hosted_url="https://pay/fin", pdf="https://pdf/fin"),
            ),
            b"PAID": _event(
                "evt_race_paid", "invoice.paid", "acct_race_ar",
                _sub_inv_obj("in_race_ar", "sub_race_ar", amount_paid=4900),
            ),
        }

        def fake_construct(payload, sig_header, secret):
            return events[payload]

        factory = RequestFactory()
        barrier = threading.Barrier(2)
        responses = []
        errors = []

        def worker(body):
            try:
                request = factory.post(
                    "/api/v1/webhooks/stripe/", data=body,
                    content_type="application/json",
                )
                barrier.wait()
                response = stripe_webhook(request)
                responses.append(
                    (response.status_code, json.loads(response.content)))
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        with patch("api.v1.webhooks.stripe.Webhook.construct_event",
                   side_effect=fake_construct):
            threads = [
                threading.Thread(target=worker, args=(b"FIN",)),
                threading.Thread(target=worker, args=(b"PAID",)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [], f"workers raised unexpected exceptions: {errors}")
        self.assertEqual(len(responses), 2)

        # Distinct event ids: both deliveries must process successfully.
        for code, body in responses:
            self.assertEqual(code, 200)
            self.assertEqual(body["status"], "ok")
        self.assertEqual(
            StripeWebhookEvent.objects.filter(
                stripe_event_id__in=["evt_race_fin", "evt_race_paid"],
                status="succeeded",
            ).count(),
            2,
        )

        # EVERY interleaving ends paid: open->paid applies; paid<-open refused.
        rows = SubscriptionInvoice.objects.filter(stripe_invoice_id="in_race_ar")
        self.assertEqual(rows.count(), 1, "the race must not create a second row")
        row = rows.first()
        self.assertEqual(row.status, "paid")
        self.assertIsNotNone(row.paid_at)
        self.assertEqual(row.amount_paid_micros, 49_000_000)
