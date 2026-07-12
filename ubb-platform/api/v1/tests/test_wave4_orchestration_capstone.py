"""Wave 4 capstone integration test: multi-axis orchestration — subscription + standalone usage.

A REAL live-server test driving the ``ubb`` Python SDK over HTTP against a running
Django server. It proves a tenant can orchestrate a whole multi-axis bill for a
pooled business account -- access fee + per-seat + metered usage -- where the
subscription axes (access + seats) land on the Stripe subscription invoice while
usage is ALWAYS pushed to its own standalone finalized invoice (Wave 4.5 C1),
and that the business margin is computed correctly (the regression proof that the
subscription-revenue sync fix landed: the business's subscription revenue is
counted ONCE, not 0 and not 10x).

What it exercises end to end:

  - ``create_plan`` -> POST /api/v1/platform/plans (access_fee + per_seat axes),
  - ``subscribe_customer`` -> POST .../subscribe: the orchestrator provisions a
    Stripe Product/Price per axis, opens a Subscription on the tenant's CONNECTED
    account, and mirrors it (StripeSubscription + 2 CustomerSubscriptionItem rows:
    access qty 1 + seat qty 10). amount_micros = 50M + 80M = 130M.
  - ``set_seats(12)`` -> POST .../seats: pushes the new seat quantity to Stripe with
    proration and bumps the mirrored seat item to 12.
  - metered usage attributed to the two seats (a business aggregates across its
    seats), pushed via PostpaidUsageService.push_customer_period -- the usage
    InvoiceItem carries NO subscription= kwarg (not pinned to the subscription cycle),
    and a standalone stripe.Invoice.create + finalize_invoice is called to collect
    it on its own correct-cycle invoice (Wave 4.5 C1: standalone usage routing).
  - ``MarginService.compute_business`` -> totals["subscription_revenue_micros"]
    == 146_000_000 (50M access + 12 seats*8M after set_seats(12); counted once
    for the business, not 0, not 10x).

Why live-server (not mocked httpx): mocked unit tests let real wire-level
mismatches ship undetected (a 404 on a renamed route, a response the SDK can't
deserialize). This exercises the real URL routing, the real orchestration state
machine, and the real SDK response contract end to end.

Stripe is MOCKED process-wide -- never network. The orchestration's ``stripe.*``
writes run synchronously in the live-server thread during each request; because
live_server runs in THIS process, the ``unittest.mock.patch`` of the Stripe SDK
symbols reaches that thread while the patch context is open here (the same trick
the Wave 3 capstone used for ``stripe.OAuth``).
"""
import datetime

import pytest
from unittest.mock import patch, MagicMock

from django.utils import timezone

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.subscriptions.models import StripeSubscription, CustomerSubscriptionItem

# A FULL calendar month window: subscription_nominal pro-rates amount_micros by
# overlap_days / days_in_month; a full month => 130M * 30 // 30 == 130M exactly.
# June 2026 has 30 days, and usage events (auto_now_add => "now", currently June
# 2026) are nudged to mid-June so they fall inside this same window.
PERIOD_START = datetime.date(2026, 6, 1)
PERIOD_END = datetime.date(2026, 7, 1)
USAGE_AT = timezone.make_aware(datetime.datetime(2026, 6, 15, 12, 0, 0))

# Unix timestamps for the subscription item billing period (mid-cycle), so the
# mirror's _period_start/_period_end read real values off the items.
_PERIOD_START_UNIX = int(datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc).timestamp())
_PERIOD_END_UNIX = int(datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc).timestamp())


def _fake_sub():
    """A Stripe Subscription dict: two licensed items (access price_a + seat price_s).

    Shapes match what _sum_items / _persist_mirror read: each item carries a
    ``price`` with ``unit_amount`` (cents) + ``recurring.usage_type=licensed``, a
    ``quantity``, an ``id`` (the subscription-item id), and per-item
    ``current_period_start/end`` (unix) for the mirror's period.
    """
    return {
        "id": "sub_1",
        "status": "active",
        "currency": "usd",
        "items": {"data": [
            {
                "id": "si_a",
                "price": {"id": "price_a", "unit_amount": 5000,
                          "recurring": {"interval": "month", "usage_type": "licensed"}},
                "quantity": 1,
                "current_period_start": _PERIOD_START_UNIX,
                "current_period_end": _PERIOD_END_UNIX,
            },
            {
                "id": "si_s",
                "price": {"id": "price_s", "unit_amount": 800,
                          "recurring": {"interval": "month", "usage_type": "licensed"}},
                "quantity": 10,
                "current_period_start": _PERIOD_START_UNIX,
                "current_period_end": _PERIOD_END_UNIX,
            },
        ]},
    }


@pytest.fixture
def _no_outbox_dispatch():
    """Neutralize the transactional-outbox Celery dispatch for this test.

    Under live_server there is no Celery worker/broker, so a fire-and-forget
    ``process_single_event.delay()`` on commit would raise. Patching the dispatch
    symbol to a no-op removes the broker dependency; because live_server runs in
    this same process, the patch applies to the server thread too.
    """
    with patch("apps.platform.events.tasks.process_single_event.delay"):
        yield


@pytest.mark.django_db(transaction=True)
def test_wave4_multi_axis_orchestration_one_bill_and_margin(
    live_server, _no_outbox_dispatch, settings
):
    # Process-wide -> reaches the live-server thread too (same process).
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"

    from ubb.client import UBBClient

    # A charge-ready tenant (connected account present + charges_enabled).
    tenant = Tenant.objects.create(
        name="W4",
        products=["metering", "billing"],
        billing_mode="postpaid",
        stripe_connected_account_id="acct_W4",
        charges_enabled=True,
    )
    _, raw_key = TenantApiKey.create_key(tenant)

    # A POOLED business + 2 seats under it. The business owns the money (wallet /
    # subscription); each seat's usage rolls up to the business at billing time.
    business = Customer.objects.create(
        tenant=tenant, external_id="biz",
        account_type="business", billing_topology="pooled",
    )
    seat1 = Customer.objects.create(
        tenant=tenant, external_id="alice", account_type="seat", parent=business,
    )
    seat2 = Customer.objects.create(
        tenant=tenant, external_id="bob", account_type="seat", parent=business,
    )
    # Sanity: a pooled seat's billing owner resolves to the business.
    assert seat1.resolve_billing_owner().id == business.id

    svc = "apps.subscriptions.orchestration.service.stripe"

    c = UBBClient(api_key=raw_key, base_url=live_server.url)
    try:
        # 1. Define the plan: $50/mo access + $8/seat/mo.
        plan = c.create_plan(
            "pro", "Pro",
            access_fee_micros=50_000_000, per_seat_micros=8_000_000,
        )
        assert plan["access_fee_micros"] == 50_000_000
        assert plan["per_seat_micros"] == 8_000_000

        # 2. Subscribe the business: 10 seats. The orchestrator provisions a
        #    Product/Price per axis, opens the Subscription, and the business has
        #    no Stripe Customer yet -> Customer.create is invoked too.
        with patch(f"{svc}.Product.create",
                   side_effect=[MagicMock(id="prod_access"), MagicMock(id="prod_seat")]), \
             patch(f"{svc}.Price.create",
                   side_effect=[MagicMock(id="price_a"), MagicMock(id="price_s")]), \
             patch(f"{svc}.Customer.create", return_value=MagicMock(id="cus_biz")), \
             patch(f"{svc}.Subscription.create", return_value=_fake_sub()):
            sub_resp = c.subscribe_customer("biz", "pro", seats=10)

        assert sub_resp["subscription_id"] == "sub_1"
        # access (5000c x1) + seat (800c x10) = 50M + 80M micros = 130M.
        assert sub_resp["amount_micros"] == 130_000_000
        assert sub_resp["quantity"] == 10

        # The mirror exists, keyed on the BUSINESS (the billing owner), 130M.
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_1")
        assert mirror.customer_id == business.id
        assert mirror.amount_micros == 130_000_000

        # Two line items: access qty 1 + seat qty 10.
        access_item = CustomerSubscriptionItem.objects.get(customer=business, axis="access")
        seat_item = CustomerSubscriptionItem.objects.get(customer=business, axis="seat")
        assert access_item.quantity == 1
        assert seat_item.quantity == 10

        # The business now has the Stripe Customer the orchestrator created.
        business.refresh_from_db()
        assert business.stripe_customer_id == "cus_biz"

        # 3. Change seats 10 -> 12: pushed to Stripe with proration; mirror bumped.
        with patch(f"{svc}.SubscriptionItem.modify", return_value=MagicMock()) as mock_modify:
            seats_resp = c.set_seats("biz", 12)
        assert seats_resp["seats"] == 12
        mock_modify.assert_called_once()
        modify_kwargs = mock_modify.call_args.kwargs
        assert modify_kwargs["quantity"] == 12
        assert modify_kwargs["proration_behavior"] == "create_prorations"
        assert modify_kwargs["id"] == seat_item.stripe_subscription_item_id
        seat_item.refresh_from_db()
        assert seat_item.quantity == 12

        # 4. Record metered usage attributed to the SEATS (a business aggregates
        #    across its seats). effective_at is auto_now_add ("now" == June 2026),
        #    so nudge it into the closed June window via a post-create update.
        #    This usage will be pushed to a standalone invoice (Wave 4.5 C1).
        from apps.metering.usage.models import UsageEvent
        for seat, key, billed, provider in [
            (seat1, "u-alice", 4_000_000, 1_000_000),
            (seat2, "u-bob", 3_000_000, 800_000),
        ]:
            ev = UsageEvent.objects.create(
                tenant=tenant, customer=seat, request_id=key, idempotency_key=key,
                provider_cost_micros=provider, billed_cost_micros=billed)
            UsageEvent.objects.filter(id=ev.id).update(effective_at=USAGE_AT)

        # Push the closed June period for the BUSINESS. Wave 4.5 C1: usage is ALWAYS
        # routed to its own standalone finalized invoice -- the InvoiceItem carries NO
        # subscription= kwarg, and stripe.Invoice.create + finalize_invoice are called
        # to collect it on a correct-cycle standalone invoice. Driven in-process (the
        # push is a background/beat task, not an SDK call); standalone routing + margin
        # are the goal.
        from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService
        psvc = "apps.billing.invoicing.services.postpaid_service.stripe"
        with patch(f"{psvc}.InvoiceItem.create", return_value=MagicMock(id="ii_1")) as mock_ii, \
             patch(f"{psvc}.Invoice.create", return_value=MagicMock(id="in_usage")) as mock_inv, \
             patch(f"{psvc}.Invoice.list", return_value=MagicMock()), \
             patch(f"{psvc}.Invoice.finalize_invoice",
                   return_value=MagicMock(id="in_usage")) as mock_finalize:
            rec = PostpaidUsageService.push_customer_period(
                tenant, business, PERIOD_START, PERIOD_END)

        assert rec.status == "pushed"
        # Business aggregates one line per seat: 4M + 3M = 7M billed.
        assert rec.total_billed_micros == 7_000_000

        # STANDALONE ROUTING (Wave 4.5 C1): usage InvoiceItem(s) have NO subscription=
        # kwarg -- they are NOT pinned to the subscription cycle.
        assert mock_ii.called
        for call in mock_ii.call_args_list:
            assert "subscription" not in call.kwargs, (
                "usage InvoiceItem must NOT carry subscription= (standalone routing, not pinned)")
            assert call.kwargs["customer"] == "cus_biz"  # the business, the billing owner
        # A standalone invoice was created and finalized.
        mock_inv.assert_called_once()
        mock_finalize.assert_called_once()

        # 5. THE REGRESSION PROOF: business subscription revenue is counted ONCE.
        #    Usage on its own standalone invoice doesn't affect subscription_revenue.
        from apps.subscriptions.economics.services import MarginService
        margin = MarginService.compute_business(
            tenant.id, business, PERIOD_START, PERIOD_END)
        totals = margin["totals"]
        # After set_seats(12) the mirror is updated: 50M access + 12*8M seat = 146M.
        assert totals["subscription_revenue_micros"] == 146_000_000, (
            "business subscription revenue must be 146M -- not 0 (sync regression) "
            "and not 10x=1.46B (per-seat double-count). "
            "50M access + 12 seats * 8M = 146M after set_seats(12).")
        # The seats' usage is the usage axis (default billed mode under postpaid),
        # so total revenue = 146M subscription + 7M usage = 153M.
        assert totals["usage_revenue_micros"] == 7_000_000
        assert totals["total_revenue_micros"] == 153_000_000
    finally:
        c.close()
