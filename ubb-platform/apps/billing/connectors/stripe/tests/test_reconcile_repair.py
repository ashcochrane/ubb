"""The hourly top-up reconcile, driven with the REAL stripe-python object
model (Stage C1a, F-3a / F-2).

``PaymentIntent.list`` answers a genuine ``stripe.ListObject`` of
``stripe.PaymentIntent``s (metadata a ``StripeObject``, no ``.get``), paged
the way the SDK pages — ``auto_paging_iter()`` asks for page two lazily.
Before C1a the sweep read ``metadata.get(...)`` (every real PaymentIntent
crashed it, uncaught), fetched page two OUTSIDE its try, and called the SDK
raw with whatever key it had — an empty live key reached transport.
"""
import logging

import pytest
import stripe
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt
from apps.billing.connectors.stripe.tasks import reconcile_topups_with_stripe

SK = "sk_test_sentinel"
TASKS = "apps.billing.connectors.stripe.tasks"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _pi_dict(id, attempt_id, *, status="succeeded", charge="ch_1"):
    return {"id": id, "object": "payment_intent", "status": status,
            "latest_charge": {"id": charge, "object": "charge"},
            "metadata": {"topup_attempt_id": str(attempt_id)}}


def _page(pi_dicts, *, has_more=False):
    """A genuine stripe.ListObject page of real PaymentIntents."""
    return stripe.ListObject.construct_from(
        {"object": "list", "data": pi_dicts, "has_more": has_more,
         "url": "/v1/payment_intents"}, SK)


def _real_charge(amount=2000, currency="usd"):
    return stripe.Charge.construct_from(
        {"id": "ch_1", "object": "charge", "status": "succeeded", "amount": amount,
         "currency": currency, "refunded": False}, SK)


def _tenant(name, account):
    t = Tenant.objects.create(name=name, stripe_connected_account_id=account,
                              products=["metering", "billing"], billing_mode="prepaid")
    c = Customer.objects.create(tenant=t, external_id="c1")
    Wallet.objects.create(customer=c, balance_micros=0)
    # Charged at Stripe but never credited locally (pending, no WalletTransaction).
    a = TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                    amount_micros=20_000_000,
                                    trigger="auto_top_up", status="pending")
    return t, c, a


def _capturing(logger_name):
    capture = _Capture()
    logging.getLogger(logger_name).addHandler(capture)
    return capture


@pytest.mark.django_db
def test_reconcile_repairs_uncredited_succeeded_pi(rail_activated):
    t, c, a = _tenant("T", "acct_x")
    page = _page([_pi_dict("pi_1", a.id)])
    assert not hasattr(page.data[0].metadata, "get")  # the real shape
    with patch(f"{TASKS}.stripe.PaymentIntent.list", return_value=page), \
         patch(f"{TASKS}.stripe.Charge.retrieve", return_value=_real_charge()):
        reconcile_topups_with_stripe()
    assert Wallet.objects.get(customer=c).balance_micros == 20_000_000
    assert WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_1").count() == 1
    a.refresh_from_db()
    assert a.status == "succeeded"


@pytest.mark.django_db
def test_a_succeeded_pi_on_the_second_page_is_repaired_too(rail_activated):
    """auto_paging_iter() fetches page two lazily through ListObject.next_page;
    the attempt listed there is credited like one on page one."""
    t, c, a1 = _tenant("T", "acct_x")
    c2 = Customer.objects.create(tenant=t, external_id="c2")
    Wallet.objects.create(customer=c2, balance_micros=0)
    a2 = TopUpAttempt.objects.create(customer=c2, billing_owner_id=c2.id,
                                     amount_micros=20_000_000,
                                     trigger="auto_top_up", status="pending")
    page1 = _page([_pi_dict("pi_p1", a1.id)], has_more=True)
    page2 = _page([_pi_dict("pi_p2", a2.id, charge="ch_2")])
    with patch(f"{TASKS}.stripe.PaymentIntent.list", return_value=page1), \
         patch.object(stripe.ListObject, "next_page", side_effect=[page2, _page([])]) as nxt, \
         patch(f"{TASKS}.stripe.Charge.retrieve", return_value=_real_charge()):
        reconcile_topups_with_stripe()
    assert nxt.call_count == 2  # page two, then the empty page that ends the walk
    for attempt, customer, key in ((a1, c, "auto_top_up:pi_p1"), (a2, c2, "auto_top_up:pi_p2")):
        attempt.refresh_from_db()
        assert attempt.status == "succeeded"
        assert Wallet.objects.get(customer=customer).balance_micros == 20_000_000
        assert WalletTransaction.objects.filter(idempotency_key=key).count() == 1


@pytest.mark.django_db
def test_a_failure_fetching_page_two_is_caught_inside_the_sweeps_try(rail_activated):
    """A page-two fetch failure lands in the same except as a page-one one:
    the account is logged and skipped, the sweep goes on, nothing raises."""
    t, c, a = _tenant("T", "acct_x")
    page1 = _page([_pi_dict("pi_p1", a.id)], has_more=True)
    capture = _capturing(TASKS)
    try:
        with patch(f"{TASKS}.stripe.PaymentIntent.list", return_value=page1), \
             patch.object(stripe.ListObject, "next_page",
                          side_effect=stripe.error.APIConnectionError("page two lost")), \
             patch(f"{TASKS}.stripe.Charge.retrieve", return_value=_real_charge()):
            reconcile_topups_with_stripe()  # no raise
    finally:
        logging.getLogger(TASKS).removeHandler(capture)
    assert [r.getMessage() for r in capture.records if r.levelno == logging.WARNING] == [
        "Reconcile: PI list failed"]
    a.refresh_from_db()
    assert a.status == "pending"  # the partial page was not acted on
    assert Wallet.objects.get(customer=c).balance_micros == 0


@pytest.mark.django_db
def test_an_unset_live_key_never_reaches_transport(rail_activated, settings):
    """F-2: with STRIPE_SECRET_KEY unset the live tenant's list is refused by
    the wrapper BEFORE any request is built; the sweep logs and moves on.
    Before C1a the raw SDK call sent the request with an empty key."""
    t, c, a = _tenant("T", "acct_x")
    settings.STRIPE_SECRET_KEY = ""
    transport = MagicMock(name="request_raw")
    capture = _capturing(TASKS)
    try:
        with patch("stripe._api_requestor._APIRequestor.request_raw", transport):
            reconcile_topups_with_stripe()  # no raise
    finally:
        logging.getLogger(TASKS).removeHandler(capture)
    transport.assert_not_called()
    assert "Reconcile: PI list failed" in [r.getMessage() for r in capture.records]
    a.refresh_from_db()
    assert a.status == "pending"


@pytest.mark.django_db
def test_the_charge_audit_with_an_unset_live_key_never_reaches_transport(rail_activated, settings):
    """F-2, the sweep's second raw site (Charge.retrieve on every recently
    succeeded attempt): refused by the wrapper, the attempt skipped."""
    t, c, a = _tenant("T", "acct_x")
    a.status = "succeeded"
    a.stripe_charge_id = "ch_audit"
    a.save(update_fields=["status", "stripe_charge_id", "updated_at"])
    settings.STRIPE_SECRET_KEY = ""
    transport = MagicMock(name="request_raw")
    with patch("stripe._api_requestor._APIRequestor.request_raw", transport):
        reconcile_topups_with_stripe()  # no raise
    transport.assert_not_called()


@pytest.mark.django_db
def test_an_attempt_whose_tenant_left_prepaid_is_recorded_by_name_and_the_sweep_goes_on(
        rail_activated):
    """Stage A (2026-11-02): a settled PaymentIntent whose attempt belongs to
    a tenant that no longer holds a wallet cannot be credited — the wallet
    boundary refuses by name. The sweep records that loudly (money was taken
    and cannot land) and goes on to the next tenant rather than dying on
    the same attempt every hour: the second tenant below is still repaired."""
    left, left_c, left_a = _tenant("Left", "acct_left")
    still, still_c, still_a = _tenant("Still", "acct_still")
    left.billing_mode = "external"
    left.save()

    def listing_for(**kwargs):
        attempt = left_a if kwargs["stripe_account"] == "acct_left" else still_a
        return _page([_pi_dict(f"pi_{kwargs['stripe_account']}", attempt.id)])

    # The `apps` loggers do not propagate (config/settings.py), so the record
    # is read off the module's own logger.
    capture = _capturing(TASKS)
    try:
        with patch(f"{TASKS}.stripe.PaymentIntent.list", side_effect=listing_for), \
                patch(f"{TASKS}.stripe.Charge.retrieve", return_value=_real_charge()):
            reconcile_topups_with_stripe()  # no raise
    finally:
        logging.getLogger(TASKS).removeHandler(capture)

    left_a.refresh_from_db()
    assert left_a.status == "pending"
    assert Wallet.objects.get(customer=left_c).balance_micros == 0
    assert not WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_acct_left").exists()
    recorded = [r for r in capture.records
                if r.getMessage() == "auto_top_up.reconcile_refused_no_wallet_subject"]
    assert len(recorded) == 1
    assert recorded[0].levelno == logging.ERROR
    assert recorded[0].data["billing_mode"] == "external"
    # The sweep went on: the tenant that still holds a wallet was repaired.
    still_a.refresh_from_db()
    assert still_a.status == "succeeded"
    assert Wallet.objects.get(customer=still_c).balance_micros == 20_000_000
