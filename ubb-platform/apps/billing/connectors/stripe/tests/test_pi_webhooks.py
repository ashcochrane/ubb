"""The auto-top-up PaymentIntent webhooks, driven with the REAL stripe-python
object model (Stage C1a, F-3a).

Every PaymentIntent here is a ``stripe.PaymentIntent`` built by
``construct_from`` — whose ``metadata`` is a ``StripeObject`` with no
``.get`` — and every event is a ``stripe.Event``, exactly what
``Webhook.construct_event`` delivers. The signed-delivery class goes one step
further and posts a genuinely signed payload through the billing receiver.
Before C1a the handlers read ``metadata.get(...)`` and every real event
answered a retryable 500 (``R10-BILLING-READINESS/findings.md`` F-3a).
"""
import hashlib
import hmac
import json
import time

import pytest
import stripe
from django.test import RequestFactory, override_settings
from unittest.mock import patch

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.stripe.models import StripeWebhookEvent
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt
from apps.billing.connectors.stripe.webhooks import (
    handle_payment_intent_succeeded,
    handle_payment_intent_payment_failed,
)

SK = "sk_test_sentinel"


def _pi_dict(id, attempt_id=None, *, status="succeeded", latest_charge="ch_1",
             last_payment_error=None):
    data = {"id": id, "object": "payment_intent", "status": status,
            "metadata": {} if attempt_id is None else {"topup_attempt_id": str(attempt_id)}}
    if latest_charge is not None:
        data["latest_charge"] = {"id": latest_charge, "object": "charge"}
    if last_payment_error is not None:
        data["last_payment_error"] = {"message": last_payment_error, "code": "card_declined"}
    return data


def _event_dict(pi_dict, *, type="payment_intent.succeeded", account=None, livemode=True):
    data = {"id": f"evt_{pi_dict['id']}", "object": "event", "type": type,
            "livemode": livemode, "created": int(time.time()),
            "data": {"object": pi_dict}}
    if account is not None:
        data["account"] = account
    return data


def _event(pi_dict, *, type="payment_intent.succeeded", account=None):
    """A genuine stripe.Event whose data.object is a real stripe.PaymentIntent
    (its metadata a StripeObject, not a dict) — the shape
    Webhook.construct_event delivers. `account` is absent when None, as on a
    platform-account event (the cross-account guard then stays quiet)."""
    return stripe.Event.construct_from(_event_dict(pi_dict, type=type, account=account), SK)


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestPIWebhook:
    def _setup(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                        amount_micros=20_000_000,
                                        trigger="auto_top_up", status="pending")
        return c, a

    def test_webhook_credits_once_idempotent(self):
        c, a = self._setup()
        event = _event(_pi_dict("pi_1", a.id))
        pi = event.data.object
        assert isinstance(pi, stripe.PaymentIntent) and not hasattr(pi.metadata, "get")
        handle_payment_intent_succeeded(event)
        a.refresh_from_db()
        assert a.status == "succeeded"
        assert a.stripe_charge_id == "ch_1"
        assert Wallet.objects.get(customer=c).balance_micros == 20_000_000
        handle_payment_intent_succeeded(event)  # again — idempotent
        assert WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_1").count() == 1

    def test_webhook_ignores_non_topup_pi(self):
        # Empty metadata: a StripeObject that is TRUTHY yet holds nothing.
        handle_payment_intent_succeeded(_event(_pi_dict("pi_x")))  # no-op, no error
        assert WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_x").count() == 0

    def test_webhook_ignores_a_pi_with_no_metadata_at_all(self):
        handle_payment_intent_succeeded(_event(
            {"id": "pi_bare", "object": "payment_intent", "status": "succeeded"}))
        assert WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_bare").count() == 0

    def test_payment_failed_marks_the_attempt_failed_with_stripes_message(self):
        c, a = self._setup()
        pi = _pi_dict("pi_f", a.id, status="requires_payment_method", latest_charge=None,
                      last_payment_error="Your card was declined.")
        handle_payment_intent_payment_failed(_event(pi, type="payment_intent.payment_failed"))
        a.refresh_from_db()
        assert a.status == "failed"
        assert a.failure_reason == {"error_type": "PaymentIntentFailed",
                                    "message": "Your card was declined."}
        assert Wallet.objects.get(customer=c).balance_micros == 0


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestPIWebhookCrossAccountGuard:
    """B4: the payment_intent handlers must verify event.account against the
    attempt's tenant.stripe_connected_account_id before acting on the credit."""

    def _setup(self, acct="acct_tenant_1"):
        t = Tenant.objects.create(name="T", stripe_connected_account_id=acct,
                                  products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                        amount_micros=20_000_000,
                                        trigger="auto_top_up", status="pending")
        return t, c, a

    def test_succeeded_mismatched_account_is_skipped(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        with patch("apps.billing.topups.services.AutoTopUpService.apply_topup_credit") as m:
            handle_payment_intent_succeeded(_event(_pi_dict("pi_cross", a.id), account="acct_DIFFERENT"))
        m.assert_not_called()

    def test_succeeded_matching_account_applies_credit(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        with patch("apps.billing.topups.services.AutoTopUpService.apply_topup_credit") as m:
            handle_payment_intent_succeeded(_event(_pi_dict("pi_match", a.id), account="acct_tenant_1"))
        m.assert_called_once()

    def test_succeeded_no_account_applies_credit(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        with patch("apps.billing.topups.services.AutoTopUpService.apply_topup_credit") as m:
            handle_payment_intent_succeeded(_event(_pi_dict("pi_noacct", a.id), account=None))
        m.assert_called_once()

    def test_failed_mismatched_account_is_skipped(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        pi = _pi_dict("pi_cross_f", a.id, status="requires_payment_method", latest_charge=None,
                      last_payment_error="card declined")
        handle_payment_intent_payment_failed(
            _event(pi, type="payment_intent.payment_failed", account="acct_DIFFERENT"))
        a.refresh_from_db()
        assert a.status == "pending"  # untouched — cross-account guard fired

    def test_failed_matching_account_marks_failed(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        pi = _pi_dict("pi_match_f", a.id, status="requires_payment_method", latest_charge=None,
                      last_payment_error="card declined")
        handle_payment_intent_payment_failed(
            _event(pi, type="payment_intent.payment_failed", account="acct_tenant_1"))
        a.refresh_from_db()
        assert a.status == "failed"


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestARealSignedPaymentIntentEventOverTheBillingReceiver:
    """Stage C1a: a genuinely signed ``payment_intent.succeeded`` /
    ``payment_intent.payment_failed`` posted to the billing receiver, verified
    by Stripe's own ``Webhook.construct_event`` — nothing mocked between the
    wire and the wallet. On the anchor both answered 500
    (``{"type": "AttributeError", "error": "get"}``) and Stripe would have
    retried for three days."""

    SECRET = "whsec_c1a_pi_receiver"

    def _setup(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid",
                                  stripe_connected_account_id="acct_signed")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                        amount_micros=20_000_000,
                                        trigger="auto_top_up", status="pending")
        return c, a

    def _deliver(self, event_dict):
        from api.v1.webhooks import stripe_webhook
        payload = json.dumps(event_dict).encode()
        ts = int(time.time())
        digest = hmac.new(self.SECRET.encode(), f"{ts}.".encode() + payload,
                          hashlib.sha256).hexdigest()
        request = RequestFactory().post(
            "/api/v1/webhooks/stripe", data=payload, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=f"t={ts},v1={digest}")
        with override_settings(STRIPE_WEBHOOK_SECRET=self.SECRET):
            return stripe_webhook(request)

    def test_a_signed_succeeded_event_credits_the_wallet_and_answers_200(self):
        c, a = self._setup()
        response = self._deliver(_event_dict(_pi_dict("pi_signed", a.id), account="acct_signed"))
        assert response.status_code == 200, response.content
        a.refresh_from_db()
        assert a.status == "succeeded"
        assert Wallet.objects.get(customer=c).balance_micros == 20_000_000
        row = StripeWebhookEvent.objects.get(stripe_event_id="evt_pi_signed")
        assert row.status == "succeeded"

    def test_a_signed_payment_failed_event_fails_the_attempt_and_answers_200(self):
        c, a = self._setup()
        response = self._deliver(_event_dict(
            _pi_dict("pi_signed_f", a.id, status="requires_payment_method", latest_charge=None,
                     last_payment_error="Your card was declined."),
            type="payment_intent.payment_failed", account="acct_signed"))
        assert response.status_code == 200, response.content
        a.refresh_from_db()
        assert a.status == "failed"
        assert a.failure_reason["message"] == "Your card was declined."
        assert Wallet.objects.get(customer=c).balance_micros == 0
        assert StripeWebhookEvent.objects.get(stripe_event_id="evt_pi_signed_f").status == "succeeded"
