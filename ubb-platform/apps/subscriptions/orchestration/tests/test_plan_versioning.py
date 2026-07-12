"""F5.4: plan-price versioning — fee edits create NEW versioned Stripe Prices.

The fee-edit fix: ensure_plan_provisioned skips an axis once its price id is
set, so plan fee edits were silently ignored. update_plan_prices bumps
pricing_version, creates a new Price (same Product) keyed
plan-price-{axis}-{plan.id}-v{version}, and repoints the plan. Old
subscriptions keep their old price (CustomerSubscriptionItem.stripe_price_id is
the history) unless migrate_existing=True.
"""
import pytest
from unittest.mock import patch, MagicMock

from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import (
    CustomerSubscriptionItem,
    StripeSubscription,
    TenantBillingPlan,
)
from apps.subscriptions.orchestration.service import (
    SubscriptionOrchestrator,
    OrchestrationError,
)

SVC = "apps.subscriptions.orchestration.service.stripe"


def _charge_ready_tenant():
    return Tenant.objects.create(name="T", products=["metering", "billing"],
        stripe_connected_account_id="acct_T", charges_enabled=True)


def _provisioned_plan(t, **overrides):
    defaults = dict(
        tenant=t, key="pro", name="Pro",
        access_fee_micros=50_000_000, per_seat_micros=8_000_000, interval="month",
        stripe_access_product_id="prod_a", stripe_access_price_id="price_a_v1",
        stripe_seat_product_id="prod_s", stripe_seat_price_id="price_s_v1",
        provisioned_at=timezone.now(),
    )
    defaults.update(overrides)
    return TenantBillingPlan.objects.create(**defaults)


def _subscribed(t, plan, *, external_id="biz", sub_id="sub_1", seat_qty=10):
    biz = Customer.objects.create(tenant=t, external_id=external_id,
                                  stripe_customer_id=f"cus_{external_id}")
    now = timezone.now()
    mirror = StripeSubscription.objects.create(
        tenant=t, customer=biz, stripe_subscription_id=sub_id,
        stripe_product_name="Pro", status="active",
        amount_micros=50_000_000 + 8_000_000 * seat_qty, currency="usd",
        interval="month", quantity=seat_qty,
        current_period_start=now, current_period_end=now, last_synced_at=now)
    access = CustomerSubscriptionItem.objects.create(
        tenant=t, customer=biz, stripe_subscription=mirror,
        stripe_subscription_item_id=f"si_a_{sub_id}", axis="access",
        stripe_price_id="price_a_v1", unit_amount_micros=50_000_000, quantity=1, plan=plan)
    seat = CustomerSubscriptionItem.objects.create(
        tenant=t, customer=biz, stripe_subscription=mirror,
        stripe_subscription_item_id=f"si_s_{sub_id}", axis="seat",
        stripe_price_id="price_s_v1", unit_amount_micros=8_000_000, quantity=seat_qty, plan=plan)
    return biz, mirror, access, seat


# ---- provisioned fee edit: new versioned Price, old subs grandfathered ----

@pytest.mark.django_db
def test_fee_edit_on_provisioned_plan_creates_v2_price_on_same_product():
    t = _charge_ready_tenant()
    plan = _provisioned_plan(t)
    _, _, access_item, seat_item = _subscribed(t, plan)

    with patch(f"{SVC}.Price.create", return_value=MagicMock(id="price_s_v2")) as pc:
        SubscriptionOrchestrator.update_plan_prices(t, "pro", per_seat_micros=6_000_000)
        pc.assert_called_once()
        _, kw = pc.call_args
        assert kw["product"] == "prod_s"                      # SAME existing Product
        assert kw["unit_amount"] == 600                       # 6M micros -> 600 cents
        assert kw["idempotency_key"] == f"plan-price-seat-{plan.id}-v2"

    plan.refresh_from_db()
    assert plan.pricing_version == 2
    assert plan.stripe_seat_price_id == "price_s_v2"
    assert plan.per_seat_micros == 6_000_000
    assert plan.stripe_access_price_id == "price_a_v1"        # untouched axis
    assert plan.access_fee_micros == 50_000_000

    # Existing subscription items are GRANDFATHERED — untouched.
    access_item.refresh_from_db(); seat_item.refresh_from_db()
    assert seat_item.stripe_price_id == "price_s_v1"
    assert seat_item.unit_amount_micros == 8_000_000
    assert access_item.stripe_price_id == "price_a_v1"


@pytest.mark.django_db
def test_fee_edit_both_axes_bumps_version_once():
    t = _charge_ready_tenant()
    plan = _provisioned_plan(t)
    with patch(f"{SVC}.Price.create",
               side_effect=[MagicMock(id="price_a_v2"), MagicMock(id="price_s_v2")]) as pc:
        SubscriptionOrchestrator.update_plan_prices(
            t, "pro", access_fee_micros=60_000_000, per_seat_micros=6_000_000)
        assert pc.call_count == 2
        keys = [c.kwargs["idempotency_key"] for c in pc.call_args_list]
        assert keys == [f"plan-price-access-{plan.id}-v2", f"plan-price-seat-{plan.id}-v2"]
    plan.refresh_from_db()
    assert plan.pricing_version == 2  # ONE bump per call, not per axis


@pytest.mark.django_db
def test_new_subscribe_after_fee_edit_uses_new_price():
    t = _charge_ready_tenant()
    plan = _provisioned_plan(t)
    with patch(f"{SVC}.Price.create", return_value=MagicMock(id="price_s_v2")):
        SubscriptionOrchestrator.update_plan_prices(t, "pro", per_seat_micros=6_000_000)
    plan.refresh_from_db()

    biz = Customer.objects.create(tenant=t, external_id="newbiz", stripe_customer_id="cus_new")
    fake_sub = {"id": "sub_new", "status": "active", "currency": "usd",
        "items": {"data": [
            {"id": "si_a2", "price": {"id": "price_a_v1", "unit_amount": 5000,
             "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 1},
            {"id": "si_s2", "price": {"id": "price_s_v2", "unit_amount": 600,
             "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 3}]}}
    with patch(f"{SVC}.Subscription.create", return_value=fake_sub) as sc:
        SubscriptionOrchestrator.subscribe(biz, plan, 3)
        items = sc.call_args.kwargs["items"]
    assert {"price": "price_s_v2", "quantity": 3} in items    # new price picked up
    assert {"price": "price_a_v1", "quantity": 1} in items


@pytest.mark.django_db
def test_replay_with_same_fees_is_a_noop():
    t = _charge_ready_tenant()
    plan = _provisioned_plan(t)
    with patch(f"{SVC}.Price.create", return_value=MagicMock(id="price_s_v2")) as pc:
        SubscriptionOrchestrator.update_plan_prices(t, "pro", per_seat_micros=6_000_000)
        assert pc.call_count == 1
    with patch(f"{SVC}.Price.create") as pc2:
        SubscriptionOrchestrator.update_plan_prices(t, "pro", per_seat_micros=6_000_000)
        pc2.assert_not_called()                               # no second Price
    plan.refresh_from_db()
    assert plan.pricing_version == 2                          # no second bump


# ---- migrate_existing=True ----

@pytest.mark.django_db
def test_migrate_existing_repoints_active_items_without_proration():
    t = _charge_ready_tenant()
    plan = _provisioned_plan(t)
    _, mirror, access_item, seat_item = _subscribed(t, plan, seat_qty=10)
    # A canceled subscription on the same plan must NOT be migrated.
    _, dead_mirror, _, dead_seat = _subscribed(t, plan, external_id="dead", sub_id="sub_dead")
    dead_mirror.status = "canceled"
    dead_mirror.save(update_fields=["status"])

    with patch(f"{SVC}.Price.create", return_value=MagicMock(id="price_s_v2")), \
         patch(f"{SVC}.SubscriptionItem.modify") as sim:
        SubscriptionOrchestrator.update_plan_prices(
            t, "pro", per_seat_micros=6_000_000, migrate_existing=True)
        sim.assert_called_once()                              # live seat item only
        _, kw = sim.call_args
        assert kw["id"] == seat_item.stripe_subscription_item_id
        assert kw["price"] == "price_s_v2"
        assert kw["proration_behavior"] == "none"
        assert kw["idempotency_key"] == f"item-migrate-{seat_item.stripe_subscription_item_id}-v2"

    seat_item.refresh_from_db()
    assert seat_item.stripe_price_id == "price_s_v2"
    assert seat_item.unit_amount_micros == 6_000_000
    access_item.refresh_from_db()
    assert access_item.stripe_price_id == "price_a_v1"        # other axis untouched
    dead_seat.refresh_from_db()
    assert dead_seat.stripe_price_id == "price_s_v1"          # canceled sub untouched

    mirror.refresh_from_db()
    # 50M access + 10 seats * 6M = 110M after migration.
    assert mirror.amount_micros == 110_000_000


# ---- _persist_mirror axis inference survives a version bump ----

@pytest.mark.django_db
def test_persist_mirror_classifies_old_price_axes_via_item_history():
    """THE regression: after a bump, an old-price seat item with qty 1 must stay
    'seat' (the qty fallback would flip it to 'access')."""
    t = _charge_ready_tenant()
    plan = _provisioned_plan(t)
    biz, mirror, _, seat_item = _subscribed(t, plan, seat_qty=1)  # qty 1 on purpose

    with patch(f"{SVC}.Price.create", return_value=MagicMock(id="price_s_v2")):
        SubscriptionOrchestrator.update_plan_prices(t, "pro", per_seat_micros=6_000_000)
    plan.refresh_from_db()
    assert plan.stripe_seat_price_id == "price_s_v2"          # old id no longer current

    # Re-persist the OLD subscription (e.g. an idempotent subscribe replay):
    # its items still hold price_s_v1 / price_a_v1.
    old_sub = {"id": "sub_1", "status": "active", "currency": "usd",
        "items": {"data": [
            {"id": "si_a_sub_1", "price": {"id": "price_a_v1", "unit_amount": 5000,
             "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 1},
            {"id": "si_s_sub_1", "price": {"id": "price_s_v1", "unit_amount": 800,
             "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 1}]}}
    SubscriptionOrchestrator._persist_mirror(t, biz, plan, old_sub)

    seat_item.refresh_from_db()
    assert seat_item.axis == "seat"  # history-based match, not the qty heuristic


@pytest.mark.django_db
def test_persist_mirror_quantity_fallback_preserved_for_unknown_prices():
    """No current-id match, no history -> the original qty>1 heuristic still applies."""
    t = _charge_ready_tenant()
    plan = _provisioned_plan(t)
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    sub = {"id": "sub_x", "status": "active", "currency": "usd",
        "items": {"data": [
            {"id": "si_u1", "price": {"id": "price_unknown_1", "unit_amount": 5000,
             "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 1},
            {"id": "si_u2", "price": {"id": "price_unknown_2", "unit_amount": 800,
             "recurring": {"interval": "month", "usage_type": "licensed"}}, "quantity": 7}]}}
    SubscriptionOrchestrator._persist_mirror(t, biz, plan, sub)
    assert CustomerSubscriptionItem.objects.get(stripe_subscription_item_id="si_u1").axis == "access"
    assert CustomerSubscriptionItem.objects.get(stripe_subscription_item_id="si_u2").axis == "seat"


# ---- unprovisioned axes: fee-only update, lazy provisioning picks it up ----

@pytest.mark.django_db
def test_unprovisioned_fee_edit_updates_fee_without_stripe_or_version_bump():
    t = _charge_ready_tenant()
    plan = TenantBillingPlan.objects.create(tenant=t, key="pro", name="Pro",
        access_fee_micros=50_000_000, per_seat_micros=8_000_000, interval="month")
    with patch(f"{SVC}.Price.create") as pc, patch(f"{SVC}.Product.create") as prc:
        SubscriptionOrchestrator.update_plan_prices(
            t, "pro", access_fee_micros=60_000_000, per_seat_micros=6_000_000)
        pc.assert_not_called()
        prc.assert_not_called()
    plan.refresh_from_db()
    assert plan.access_fee_micros == 60_000_000
    assert plan.per_seat_micros == 6_000_000
    assert plan.pricing_version == 1                          # no bump

    # Lazy provisioning later uses the CURRENT (edited) fees.
    with patch(f"{SVC}.Product.create",
               side_effect=[MagicMock(id="prod_a"), MagicMock(id="prod_s")]), \
         patch(f"{SVC}.Price.create",
               side_effect=[MagicMock(id="price_a"), MagicMock(id="price_s")]) as pc2:
        SubscriptionOrchestrator.ensure_plan_provisioned(plan)
    amounts = [c.kwargs["unit_amount"] for c in pc2.call_args_list]
    assert amounts == [6000, 600]                             # 60M and 6M micros in cents


@pytest.mark.django_db
def test_unprovisioned_fee_edit_does_not_require_charge_ready():
    """Plans can be re-priced before Stripe onboarding (no Stripe call needed)."""
    t = Tenant.objects.create(name="T", products=["metering"])  # NOT charge-ready
    TenantBillingPlan.objects.create(tenant=t, key="pro", name="Pro",
        access_fee_micros=50_000_000)
    plan = SubscriptionOrchestrator.update_plan_prices(t, "pro", access_fee_micros=70_000_000)
    assert plan.access_fee_micros == 70_000_000


@pytest.mark.django_db
def test_provisioned_fee_edit_requires_charge_ready():
    t = Tenant.objects.create(name="T", products=["metering"])  # NOT charge-ready
    TenantBillingPlan.objects.create(tenant=t, key="pro", name="Pro",
        access_fee_micros=50_000_000, stripe_access_product_id="prod_a",
        stripe_access_price_id="price_a_v1", provisioned_at=timezone.now())
    with pytest.raises(OrchestrationError):
        SubscriptionOrchestrator.update_plan_prices(t, "pro", access_fee_micros=70_000_000)


@pytest.mark.django_db
def test_unknown_plan_key_raises():
    t = _charge_ready_tenant()
    with pytest.raises(OrchestrationError):
        SubscriptionOrchestrator.update_plan_prices(t, "ghost", access_fee_micros=1_000_000)


@pytest.mark.django_db
def test_fee_dropped_to_zero_on_provisioned_axis_skips_price_create():
    """A zero fee makes the axis dormant for new subscribes — no $0 Price minted."""
    t = _charge_ready_tenant()
    plan = _provisioned_plan(t)
    with patch(f"{SVC}.Price.create") as pc:
        SubscriptionOrchestrator.update_plan_prices(t, "pro", per_seat_micros=0)
        pc.assert_not_called()
    plan.refresh_from_db()
    assert plan.per_seat_micros == 0
    assert plan.pricing_version == 1
