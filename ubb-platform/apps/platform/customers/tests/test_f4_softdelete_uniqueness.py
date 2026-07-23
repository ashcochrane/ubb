from dataclasses import asdict

import pytest
from django.db import transaction
from django.test import Client
from apps.platform.customers.models import Customer
from apps.platform.events.schemas import CustomerDeleted
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.billing.wallets.models import Wallet
from apps.billing.handlers import handle_customer_deleted_billing
from apps.billing.locking import lock_for_billing


@pytest.mark.django_db
class TestF4SoftDeleteUniqueness:
    def test_reonboard_churned_external_id_returns_201(self):
        tenant = Tenant.objects.create(name="T", products=["metering", "billing"], stripe_connected_account_id="acct_test")
        _, raw_key = TenantApiKey.create_key(tenant)
        c = Customer.objects.create(tenant=tenant, external_id="churn1")
        c.soft_delete()
        resp = Client().post("/api/v1/platform/customers", data={"external_id": "churn1"},
                             content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        assert resp.status_code == 201            # today: 409
        assert Customer.objects.filter(tenant=tenant, external_id="churn1").count() == 1
        assert Customer.all_objects.filter(tenant=tenant, external_id="churn1").count() == 2

    def test_lock_for_billing_reuses_soft_deleted_wallet(self):
        tenant = Tenant.objects.create(name="T2", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="c2")
        w = Wallet.objects.create(customer=customer, balance_micros=7_000_000)
        handle_customer_deleted_billing(
            "e1", asdict(CustomerDeleted(tenant_id=tenant.id, customer_id=customer.id)))
        customer.restore()
        with transaction.atomic():
            wallet, _cust = lock_for_billing(customer.id)
        assert wallet.id == w.id
        assert wallet.deleted_at is None
        assert wallet.balance_micros == 7_000_000   # balance preserved
