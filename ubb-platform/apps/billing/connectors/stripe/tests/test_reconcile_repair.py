import pytest
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt
from apps.billing.connectors.stripe.tasks import reconcile_topups_with_stripe


@pytest.mark.django_db
def test_reconcile_repairs_uncredited_succeeded_pi():
    t = Tenant.objects.create(name="T", stripe_connected_account_id="acct_x")
    c = Customer.objects.create(tenant=t, external_id="c1")
    Wallet.objects.create(customer=c, balance_micros=0)
    # attempt was charged at Stripe but never credited locally (left pending, no WalletTransaction)
    a = TopUpAttempt.objects.create(customer=c, amount_micros=20_000_000,
                                    trigger="auto_topup", status="pending")
    pi = MagicMock(id="pi_1", status="succeeded", latest_charge=MagicMock(id="ch_1"),
                   metadata={"topup_attempt_id": str(a.id)})
    listing = MagicMock()
    listing.auto_paging_iter.return_value = [pi]
    with patch("apps.billing.connectors.stripe.tasks.stripe.PaymentIntent.list", return_value=listing):
        reconcile_topups_with_stripe()
    assert Wallet.objects.get(customer=c).balance_micros == 20_000_000
    assert WalletTransaction.objects.filter(idempotency_key="auto_topup:pi_1").count() == 1
    a.refresh_from_db()
    assert a.status == "succeeded"
