import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
def test_columns_and_backfill_defaults():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    from apps.metering.usage.models import UsageEvent
    from apps.billing.wallets.models import Wallet, WalletTransaction
    e = UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i",
                                  billing_owner_id=c.id)
    assert e.billing_owner_id == c.id
    w = Wallet.objects.create(customer=c, balance_micros=0)
    tx = WalletTransaction.objects.create(wallet=w, transaction_type="TOP_UP",
                                          amount_micros=1, balance_after_micros=1, usage_event_id=e.id)
    assert tx.usage_event_id == e.id
