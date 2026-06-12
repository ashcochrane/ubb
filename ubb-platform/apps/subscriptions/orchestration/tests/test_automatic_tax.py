"""F5.3: Subscription.create carries automatic_tax IFF the tenant opted in."""
import pytest
from unittest.mock import patch

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import TenantBillingPlan
from apps.subscriptions.orchestration.service import SubscriptionOrchestrator

FAKE_SUB = {"id": "sub_1", "status": "active", "currency": "usd",
    "items": {"data": [
        {"id": "si_a", "price": {"id": "price_a", "unit_amount": 5000,
         "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 1}]}}


def _tenant(**extra):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
        stripe_connected_account_id="acct_T", charges_enabled=True, **extra)


def _subscribe(tenant):
    biz = Customer.objects.create(tenant=tenant, external_id="biz",
                                  stripe_customer_id="cus_biz")
    plan = TenantBillingPlan.objects.create(tenant=tenant, key="pro", name="Pro",
        access_fee_micros=50_000_000, interval="month",
        stripe_access_price_id="price_a", provisioned_at="2026-01-01T00:00:00Z")
    with patch("apps.subscriptions.orchestration.service.stripe.Subscription.create",
               return_value=FAKE_SUB) as create:
        SubscriptionOrchestrator.subscribe(biz, plan, 0)
    _, kw = create.call_args
    return kw


@pytest.mark.django_db
def test_subscription_create_carries_automatic_tax_when_enabled():
    kw = _subscribe(_tenant(automatic_tax_enabled=True))
    assert kw["automatic_tax"] == {"enabled": True}


@pytest.mark.django_db
def test_subscription_create_omits_automatic_tax_by_default():
    kw = _subscribe(_tenant())
    assert "automatic_tax" not in kw
