import logging

import pytest
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt
from apps.billing.connectors.stripe.tasks import reconcile_topups_with_stripe


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.mark.django_db
def test_reconcile_repairs_uncredited_succeeded_pi(rail_activated):
    t = Tenant.objects.create(name="T", stripe_connected_account_id="acct_x",
                              products=["metering", "billing"], billing_mode="prepaid")
    c = Customer.objects.create(tenant=t, external_id="c1")
    Wallet.objects.create(customer=c, balance_micros=0)
    # attempt was charged at Stripe but never credited locally (left pending, no WalletTransaction)
    a = TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                    amount_micros=20_000_000,
                                    trigger="auto_top_up", status="pending")
    pi = MagicMock(id="pi_1", status="succeeded", latest_charge=MagicMock(id="ch_1"),
                   metadata={"topup_attempt_id": str(a.id)})
    listing = MagicMock()
    listing.auto_paging_iter.return_value = [pi]
    mock_charge = MagicMock(status="succeeded", amount=2000, currency="usd", refunded=False)
    with patch("apps.billing.connectors.stripe.tasks.stripe.PaymentIntent.list", return_value=listing), \
         patch("apps.billing.connectors.stripe.tasks.stripe.Charge.retrieve", return_value=mock_charge):
        reconcile_topups_with_stripe()
    assert Wallet.objects.get(customer=c).balance_micros == 20_000_000
    assert WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_1").count() == 1
    a.refresh_from_db()
    assert a.status == "succeeded"


@pytest.mark.django_db
def test_an_attempt_whose_tenant_left_prepaid_is_recorded_by_name_and_the_sweep_goes_on(
        rail_activated):
    """Stage A (2026-11-02): a settled PaymentIntent whose attempt belongs to
    a tenant that no longer holds a wallet cannot be credited — the wallet
    boundary refuses by name. The sweep records that loudly (money was taken
    and cannot land) and goes on to the next tenant rather than dying on
    the same attempt every hour: the second tenant below is still repaired."""
    def a_tenant(name, account):
        t = Tenant.objects.create(name=name, stripe_connected_account_id=account,
                                  products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                        amount_micros=20_000_000,
                                        trigger="auto_top_up", status="pending")
        return t, c, a

    left, left_c, left_a = a_tenant("Left", "acct_left")
    still, still_c, still_a = a_tenant("Still", "acct_still")
    left.billing_mode = "external"
    left.save()

    def listing_for(**kwargs):
        attempt = left_a if kwargs["stripe_account"] == "acct_left" else still_a
        pi = MagicMock(id=f"pi_{kwargs['stripe_account']}", status="succeeded",
                       latest_charge=MagicMock(id="ch_1"),
                       metadata={"topup_attempt_id": str(attempt.id)})
        listing = MagicMock()
        listing.auto_paging_iter.return_value = [pi]
        return listing

    mock_charge = MagicMock(status="succeeded", amount=2000, currency="usd", refunded=False)
    # The `apps` loggers do not propagate (config/settings.py), so the record
    # is read off the module's own logger.
    capture = _Capture()
    task_logger = logging.getLogger("apps.billing.connectors.stripe.tasks")
    task_logger.addHandler(capture)
    try:
        with patch("apps.billing.connectors.stripe.tasks.stripe.PaymentIntent.list",
                   side_effect=listing_for), \
                patch("apps.billing.connectors.stripe.tasks.stripe.Charge.retrieve",
                      return_value=mock_charge):
            reconcile_topups_with_stripe()  # no raise
    finally:
        task_logger.removeHandler(capture)

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
