import pytest
from unittest.mock import patch, MagicMock
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import CustomerSubscriptionItem, StripeSubscription
from apps.subscriptions.orchestration.service import SubscriptionOrchestrator, OrchestrationError


def _charge_ready_tenant():
    return Tenant.objects.create(name="T", products=["metering", "billing"],
        stripe_connected_account_id="acct_T", charges_enabled=True)

@pytest.mark.django_db
def test_ensure_plan_provisioned_creates_products_prices_once():
    t = _charge_ready_tenant()
    plan = a_plan(tenant=t, key="pro", name="Pro",
        access_fee_micros=50_000_000, per_seat_micros=8_000_000, interval="month")
    with patch("apps.subscriptions.orchestration.service.stripe.Product.create",
               side_effect=[MagicMock(id="prod_a"), MagicMock(id="prod_s")]) as mp, \
         patch("apps.subscriptions.orchestration.service.stripe.Price.create",
               side_effect=[MagicMock(id="price_a"), MagicMock(id="price_s")]) as mpr:
        SubscriptionOrchestrator.ensure_plan_provisioned(plan)
    plan.refresh_from_db()
    assert plan.stripe_access_price_id == "price_a" and plan.stripe_seat_price_id == "price_s"
    assert plan.provisioned_at is not None
    # second call: no new Stripe calls
    with patch("apps.subscriptions.orchestration.service.stripe.Product.create") as mp2:
        SubscriptionOrchestrator.ensure_plan_provisioned(plan)
        mp2.assert_not_called()

@pytest.mark.django_db
def test_subscribe_creates_two_items_and_mirror():
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    plan = a_plan(tenant=t, key="pro", name="Pro",
        access_fee_micros=50_000_000, per_seat_micros=8_000_000, interval="month",
        stripe_access_price_id="price_a", stripe_seat_price_id="price_s", provisioned_at="2026-01-01T00:00:00Z")
    fake_sub = {"id": "sub_1", "status": "active", "currency": "usd",
        "items": {"data": [
            {"id": "si_a", "price": {"id": "price_a", "unit_amount": 5000, "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 1},
            {"id": "si_s", "price": {"id": "price_s", "unit_amount": 800, "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 10}]}}
    with patch("apps.subscriptions.orchestration.service.stripe.Subscription.create", return_value=fake_sub):
        mirror = SubscriptionOrchestrator.subscribe(biz, plan, 10)
    assert mirror.amount_micros == 130_000_000
    assert CustomerSubscriptionItem.objects.filter(customer=biz).count() == 2
    assert CustomerSubscriptionItem.objects.get(axis="seat", customer=biz).quantity == 10

@pytest.mark.django_db
def test_set_seats_modifies_quantity_with_proration():
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    plan = a_plan(tenant=t, key="pro", name="Pro", per_seat_micros=8_000_000)
    sub = StripeSubscription.objects.create(tenant=t, customer=biz, stripe_subscription_id="sub_1",
        amount_micros=80_000_000, quantity=10, interval="month", status="active",
        current_period_start="2026-01-01T00:00:00Z", current_period_end="2026-02-01T00:00:00Z",
        last_synced_at="2026-01-01T00:00:00Z")
    CustomerSubscriptionItem.objects.create(tenant=t, customer=biz, stripe_subscription=sub,
        stripe_subscription_item_id="si_s", axis="seat", stripe_price_id="price_s", quantity=10, plan=plan)
    with patch("apps.subscriptions.orchestration.service.stripe.SubscriptionItem.modify") as mod:
        SubscriptionOrchestrator.set_seats(biz, plan, 12, change_event_id="evt_1")
        _, kw = mod.call_args
        assert kw["quantity"] == 12 and kw["proration_behavior"] == "create_prorations"
    assert CustomerSubscriptionItem.objects.get(stripe_subscription_item_id="si_s").quantity == 12

@pytest.mark.django_db
def test_set_seats_refreshes_mirror_without_webhook():
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    plan = a_plan(tenant=t, key="pro", name="Pro", per_seat_micros=2_000_000)
    mirror = StripeSubscription.objects.create(tenant=t, customer=biz, stripe_subscription_id="sub_1",
        amount_micros=5_000_000, quantity=2, interval="month", status="active",
        current_period_start="2026-01-01T00:00:00Z", current_period_end="2026-02-01T00:00:00Z",
        last_synced_at="2026-01-01T00:00:00Z")
    # access line (qty 1 @ 1_000_000) + seat line (qty 2 @ 2_000_000)
    CustomerSubscriptionItem.objects.create(tenant=t, customer=biz, stripe_subscription=mirror,
        stripe_subscription_item_id="si_a", axis="access", stripe_price_id="price_a",
        unit_amount_micros=1_000_000, quantity=1, plan=plan)
    CustomerSubscriptionItem.objects.create(tenant=t, customer=biz, stripe_subscription=mirror,
        stripe_subscription_item_id="si_s", axis="seat", stripe_price_id="price_s",
        unit_amount_micros=2_000_000, quantity=2, plan=plan)
    with patch("apps.subscriptions.orchestration.service.stripe.SubscriptionItem.modify"):
        SubscriptionOrchestrator.set_seats(biz, plan, 5, change_event_id="e1")
    mirror.refresh_from_db()
    assert mirror.amount_micros == 1_000_000 + 2_000_000 * 5 == 11_000_000
    assert mirror.quantity == 5
    assert mirror.last_synced_at is not None


@pytest.mark.django_db
def test_ensure_plan_provisioned_uses_tenant_currency():
    t = Tenant.objects.create(name="EUR", products=["metering", "billing"],
        stripe_connected_account_id="acct_T", charges_enabled=True, default_currency="eur")
    plan = a_plan(tenant=t, key="pro", name="Pro",
        access_fee_micros=50_000_000, per_seat_micros=8_000_000, interval="month")
    with patch("apps.subscriptions.orchestration.service.stripe.Product.create",
               side_effect=[MagicMock(id="prod_a"), MagicMock(id="prod_s")]), \
         patch("apps.subscriptions.orchestration.service.stripe.Price.create",
               side_effect=[MagicMock(id="price_a"), MagicMock(id="price_s")]) as mpr:
        SubscriptionOrchestrator.ensure_plan_provisioned(plan)
    assert mpr.call_count == 2
    for _, kw in mpr.call_args_list:
        assert kw["currency"] == "eur"


@pytest.mark.django_db
def test_not_charge_ready_raises():
    t = Tenant.objects.create(name="T", products=["metering"])  # no connected acct / charges_enabled
    plan = a_plan(tenant=t, key="pro", name="Pro", access_fee_micros=50_000_000)
    with pytest.raises(OrchestrationError):
        SubscriptionOrchestrator.ensure_plan_provisioned(plan)


@pytest.mark.django_db
class TestMarkupOnlyPlanSubscribe:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"],
            stripe_connected_account_id="acct_test", charges_enabled=True,
            default_currency="usd")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="sam-hobby")

    def test_markup_only_plan_creates_no_stripe_objects(self):
        """Personal Lite: $0 access, $0 seat, 50% markup. There is nothing for
        Stripe to bill, so no Product, Price, Subscription, or Customer is
        created — and crucially Stripe is never called with items=[]."""
        plan = a_plan(tenant=self.tenant, key="personal-lite",
                      name="Personal Lite",
                      markup_percentage_micros=50_000_000)
        with patch("apps.subscriptions.orchestration.service.stripe_call") as stripe_call:
            result = SubscriptionOrchestrator.subscribe(self.customer, plan, seats=0)
        assert result is None
        stripe_call.assert_not_called()
        assert not StripeSubscription.objects.filter(customer=self.customer).exists()

    def test_markup_only_plan_works_with_no_stripe_account_at_all(self):
        """The has_stripe_axes guard sits before _require_charge_ready on
        purpose: a markup-only plan needs nothing from Stripe, so a tenant
        with no connected account (and charges_enabled=False) must still be
        able to subscribe a customer to it, returning None without raising
        OrchestrationError. If the guard is ever moved below the charge-ready
        check, this is the test that catches it."""
        tenant = Tenant.objects.create(
            name="NoStripe", products=["metering", "billing"],
            stripe_connected_account_id="", charges_enabled=False,
            default_currency="usd")
        customer = Customer.objects.create(tenant=tenant, external_id="no-stripe-cust")
        plan = a_plan(tenant=tenant, key="markup-only",
                      name="Markup Only",
                      markup_percentage_micros=50_000_000)
        with patch("apps.subscriptions.orchestration.service.stripe_call") as stripe_call:
            result = SubscriptionOrchestrator.subscribe(customer, plan, seats=0)
        assert result is None
        stripe_call.assert_not_called()
