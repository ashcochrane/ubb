"""F5.4: subscription lifecycle verbs — cancel (at-period-end / immediate),
pause, resume — and their mirror-flag semantics.

Stripe is mocked at the orchestrator's ``stripe.*``; the mirror is updated
SYNCHRONOUSLY by each verb, and the webhook stays the (idempotent) confirm path.
"""
import pytest
from unittest.mock import patch, MagicMock

from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.orchestration.service import (
    SubscriptionOrchestrator,
    NoActiveSubscription,
)

SVC = "apps.subscriptions.orchestration.service.stripe"


def _charge_ready_tenant():
    return Tenant.objects.create(name="T", products=["metering", "billing"],
        stripe_connected_account_id="acct_T", charges_enabled=True)


def _mirror(tenant, customer, sub_id="sub_1", status="active"):
    now = timezone.now()
    return StripeSubscription.objects.create(
        tenant=tenant, customer=customer, stripe_subscription_id=sub_id,
        stripe_product_name="Pro", status=status, amount_micros=50_000_000,
        currency="usd", interval="month", quantity=1,
        current_period_start=now, current_period_end=now, last_synced_at=now)


@pytest.mark.django_db
def test_cancel_at_period_end_sets_flag_status_stays_active():
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    mirror = _mirror(t, biz)
    with patch(f"{SVC}.Subscription.modify") as mod, patch(f"{SVC}.Subscription.cancel") as can:
        SubscriptionOrchestrator.cancel(t, biz, at_period_end=True, change_event_id="e1")
        can.assert_not_called()
        _, kw = mod.call_args
        assert kw["cancel_at_period_end"] is True
        assert kw["id"] == "sub_1"
        assert kw["idempotency_key"] == "sub-cancel-sub_1-e1"
    mirror.refresh_from_db()
    assert mirror.cancel_at_period_end is True
    assert mirror.status == "active"          # Stripe keeps it active until period end
    assert mirror.canceled_at is None


@pytest.mark.django_db
def test_cancel_immediate_calls_stripe_cancel_and_marks_mirror_synchronously():
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    mirror = _mirror(t, biz)
    with patch(f"{SVC}.Subscription.cancel") as can, patch(f"{SVC}.Subscription.modify") as mod:
        SubscriptionOrchestrator.cancel(t, biz, at_period_end=False, change_event_id="e2")
        mod.assert_not_called()
        _, kw = can.call_args
        assert kw["subscription_exposed_id"] == "sub_1"
        assert kw["idempotency_key"] == "sub-cancel-now-sub_1-e2"
    mirror.refresh_from_db()
    assert mirror.status == "canceled"
    assert mirror.canceled_at is not None


@pytest.mark.django_db
def test_deleted_webhook_after_immediate_cancel_is_idempotent():
    """The webhook confirm path re-asserts canceled without clobbering canceled_at."""
    from apps.subscriptions.api.webhooks import handle_subscription_deleted

    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    mirror = _mirror(t, biz)
    with patch(f"{SVC}.Subscription.cancel"):
        SubscriptionOrchestrator.cancel(t, biz, at_period_end=False, change_event_id="e3")
    mirror.refresh_from_db()
    first_canceled_at = mirror.canceled_at

    event = MagicMock()
    event.data.object.id = "sub_1"
    handle_subscription_deleted(event)

    mirror.refresh_from_db()
    assert mirror.status == "canceled"
    assert mirror.canceled_at == first_canceled_at  # orchestrator's timestamp wins


@pytest.mark.django_db
def test_pause_voids_collection_and_sets_paused_flag_status_stays_active():
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    mirror = _mirror(t, biz)
    with patch(f"{SVC}.Subscription.modify") as mod:
        SubscriptionOrchestrator.pause(t, biz, change_event_id="e4")
        _, kw = mod.call_args
        assert kw["pause_collection"] == {"behavior": "void"}
        assert kw["idempotency_key"] == "sub-pause-sub_1-e4"
    mirror.refresh_from_db()
    assert mirror.paused is True
    assert mirror.status == "active"  # Stripe keeps status active under pause_collection


@pytest.mark.django_db
def test_resume_clears_pause_and_pending_cancel_in_one_modify():
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    mirror = _mirror(t, biz)
    mirror.paused = True
    mirror.cancel_at_period_end = True
    mirror.save(update_fields=["paused", "cancel_at_period_end"])
    with patch(f"{SVC}.Subscription.modify") as mod:
        SubscriptionOrchestrator.resume(t, biz, change_event_id="e5")
        mod.assert_called_once()
        _, kw = mod.call_args
        assert kw["pause_collection"] == ""
        assert kw["cancel_at_period_end"] is False
    mirror.refresh_from_db()
    assert mirror.paused is False
    assert mirror.cancel_at_period_end is False


@pytest.mark.django_db
def test_verbs_resolve_billing_owner_for_pooled_seat():
    """A pooled seat's lifecycle verbs act on the BUSINESS's subscription."""
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz",
        account_type="business", billing_topology="pooled", stripe_customer_id="cus_biz")
    seat = Customer.objects.create(tenant=t, external_id="alice",
        account_type="seat", parent=biz)
    mirror = _mirror(t, biz)
    with patch(f"{SVC}.Subscription.modify") as mod:
        SubscriptionOrchestrator.pause(t, seat, change_event_id="e6")
        assert mod.call_args.kwargs["id"] == mirror.stripe_subscription_id
    mirror.refresh_from_db()
    assert mirror.paused is True


@pytest.mark.django_db
@pytest.mark.parametrize("verb,kwargs", [
    ("cancel", {"at_period_end": True}),
    ("cancel", {"at_period_end": False}),
    ("pause", {}),
    ("resume", {}),
])
def test_verbs_raise_no_active_subscription_when_none(verb, kwargs):
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    # Only a CANCELED mirror exists -> not actionable.
    _mirror(t, biz, status="canceled")
    with pytest.raises(NoActiveSubscription):
        getattr(SubscriptionOrchestrator, verb)(t, biz, change_event_id="e7", **kwargs)


@pytest.mark.django_db
def test_lifecycle_verbs_target_latest_non_canceled_mirror():
    """An older canceled subscription doesn't shadow the live one."""
    t = _charge_ready_tenant()
    biz = Customer.objects.create(tenant=t, external_id="biz", stripe_customer_id="cus_biz")
    _mirror(t, biz, sub_id="sub_old", status="canceled")
    live = _mirror(t, biz, sub_id="sub_live")
    with patch(f"{SVC}.Subscription.modify") as mod:
        SubscriptionOrchestrator.cancel(t, biz, at_period_end=True, change_event_id="e8")
        assert mod.call_args.kwargs["id"] == "sub_live"
    live.refresh_from_db()
    assert live.cancel_at_period_end is True
