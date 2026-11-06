"""Subscription-mirror identity binds once and never rebinds (R10 Stage C4,
PLAN §7 items 30 and 33-38, "Option 1").

The C4 pre-authorisation inspection proved the defect at ``cf46154f``
(``R10-C4-PREAUTH-EVIDENCE/01-mirror-identity-probes.txt``): the sync rebound
an EXISTING mirror's customer and tenant on every pass to whichever duplicate
holder of the Stripe customer id the query plan returned last, a ``created``
replay raised on an already-bound mirror, and two tenants on one connected
account flipped a mirror between them. These tests drive the real sync (a
genuine ``stripe.ListObject``), the subscriptions receiver with signed
deliveries verified by Stripe's own verifier, and ``_persist_mirror`` itself.

The numbering follows the launcher's item-30 list. Test (2) and tests
(12)-(14) need the billing receiver's invoice handlers and live in
``api/v1/tests/test_an_invoice_waits_for_its_mirror.py``; test (6) drives the
Django admin change form below.
"""
import contextlib
import hashlib
import hmac
import json
import logging
import time
from unittest.mock import patch

import pytest
import stripe
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection, transaction
from django.test import RequestFactory
from django.utils import timezone

from apps.billing.stripe.models import StripeWebhookEvent
from apps.platform.customers.models import Customer
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.subscriptions.models import CustomerSubscriptionItem, StripeSubscription
from apps.subscriptions.tests._helpers import (
    SK, a_licensed_item, a_mirrored_subscription, a_stripe_subscription,
    CapturedLog, a_subscription_dict, a_subscription_event,
    clear_stripe_customer_id_in_the_admin)

SYNC = "apps.subscriptions.stripe.sync"
BINDING_LOGGER = "apps.subscriptions.stripe.binding"
WIRE_SECRET = "whsec_c4_subscriptions_receiver_test_only"


# --- fixtures ---------------------------------------------------------------

def _tenant(name, acct, **extra):
    return Tenant.objects.create(name=name, products=["metering", "billing"],
                                 stripe_connected_account_id=acct, charges_enabled=True,
                                 **extra)


def _customer(tenant, external_id, stripe_customer_id, **extra):
    return Customer.objects.create(tenant=tenant, external_id=external_id,
                                   stripe_customer_id=stripe_customer_id, **extra)


def _sub(sub_id, stripe_customer_id, status="active"):
    return a_subscription_dict(sub_id, stripe_customer_id, status,
                               items=[a_licensed_item(4900, product_name="Pro")])


def _mirror(tenant, customer, sub_id, status="trialing"):
    now = timezone.now()
    return a_mirrored_subscription(
        tenant=tenant, customer=customer, stripe_subscription_id=sub_id,
        stripe_product_name="Old", status=status, amount_micros=29_000_000,
        currency="usd", interval="month", current_period_start=now,
        current_period_end=now, last_synced_at=now)


def _sync(tenant, *sub_dicts):
    """The real sync over one genuine page of real Subscriptions."""
    from apps.subscriptions.stripe.sync import sync_subscriptions
    page = stripe.ListObject.construct_from(
        {"object": "list", "data": list(sub_dicts), "has_more": False,
         "url": "/v1/subscriptions"}, SK)
    with patch(f"{SYNC}.stripe.Subscription.list", return_value=page):
        return sync_subscriptions(tenant)


def _deliver_created(sub_dict, *, account, event_id):
    """One signed customer.subscription.created delivery through the
    subscriptions receiver, verified by Stripe's own verifier."""
    from django.test.utils import override_settings
    from apps.subscriptions.api.endpoints import subscriptions_stripe_webhook

    payload = json.dumps({
        "id": event_id, "object": "event", "type": "customer.subscription.created",
        "livemode": True, "created": int(time.time()), "account": account,
        "data": {"object": sub_dict}}).encode()
    ts = int(time.time())
    digest = hmac.new(WIRE_SECRET.encode(), f"{ts}.".encode() + payload,
                      hashlib.sha256).hexdigest()
    request = RequestFactory().post(
        "/api/v1/subscriptions/webhooks/stripe", data=payload,
        content_type="application/json", HTTP_STRIPE_SIGNATURE=f"t={ts},v1={digest}")
    with override_settings(STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=WIRE_SECRET,
                           STRIPE_TEST_WEBHOOK_SECRET=""):
        return subscriptions_stripe_webhook(request)


def _row(event_id):
    return StripeWebhookEvent.objects.get(receiver="subscriptions", stripe_event_id=event_id)


def _binding(sub_id):
    m = StripeSubscription.objects.get(stripe_subscription_id=sub_id)
    return m.customer_id, m.tenant_id


def _captured():
    """The binding module's own log lines."""
    return CapturedLog(BINDING_LOGGER)


#: The inspection's probe shape (probe A9): the same rows read under two
#: query plans. "last row wins" depended on which one Postgres chose.
_PLAN_FLAGS = {
    "index": ("enable_seqscan",),
    "sequential": ("enable_indexscan", "enable_bitmapscan", "enable_indexonlyscan"),
}


@contextlib.contextmanager
def _forced_plan(plan, tenant):
    """Force the planner for the duration, and prove it took: the duplicate
    holders' query explains as the plan asked for."""
    with transaction.atomic(), connection.cursor() as cursor:
        for flag in _PLAN_FLAGS[plan]:
            cursor.execute(f"SET LOCAL {flag} = off")
        cursor.execute(
            "EXPLAIN SELECT id, stripe_customer_id FROM ubb_customer "
            "WHERE tenant_id = %s AND stripe_customer_id > ''", [str(tenant.id)])
        explained = " | ".join(row[0] for row in cursor.fetchall())
        if plan == "sequential":
            assert "Seq Scan on ubb_customer" in explained, explained
        else:
            assert "Index" in explained and "Seq Scan" not in explained, explained
        yield explained
        for flag in _PLAN_FLAGS[plan]:
            cursor.execute(f"SET LOCAL {flag} TO DEFAULT")


# --- (1) an existing mirror is never rebound by the sync ----------------------

@pytest.mark.django_db
class TestTheSyncNeverRebindsAnExistingMirror:
    """(1) Two customers of one tenant hold the Stripe customer id; the mirror
    is bound to the first. The anchor's sync moved it to whichever holder its
    query returned last: ``cust-b`` here under either plan (inserted last,
    and the larger external id)."""

    def _scenario(self, plan):
        tenant = _tenant("T", "acct_one")
        bound = _customer(tenant, "cust-a", "cus_dup")
        _customer(tenant, "cust-b", "cus_dup")
        _mirror(tenant, bound, "sub_one")
        with _forced_plan(plan, tenant):
            first = _sync(tenant, _sub("sub_one", "cus_dup"))
            second = _sync(tenant, _sub("sub_one", "cus_dup"))
        assert first == second == {"synced": 1, "skipped": 0, "errors": 0}
        assert _binding("sub_one") == (bound.id, tenant.id)
        # The sync did run: the mutable facts are Stripe's now.
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_one")
        assert (mirror.status, mirror.stripe_product_name) == ("active", "Pro")

    def test_under_an_index_plan(self):
        self._scenario("index")

    def test_under_a_forced_sequential_plan(self):
        self._scenario("sequential")


# --- (3) a created replay on an existing mirror does not fail -----------------

@pytest.mark.django_db
def test_a_created_replay_on_a_bound_mirror_succeeds_and_changes_nothing():
    """(3) Probe A6: the replay raised MultipleObjectsReturned, a retryable
    500 Stripe would retry for days, because the handler re-resolved before
    it looked for the mirror."""
    tenant = _tenant("T", "acct_three")
    bound = _customer(tenant, "cust-a", "cus_dup")
    _customer(tenant, "cust-b", "cus_dup")
    _mirror(tenant, bound, "sub_three")

    response = _deliver_created(_sub("sub_three", "cus_dup"), account="acct_three",
                                event_id="evt_three")

    assert response.status_code == 200
    assert _row("evt_three").status == "succeeded"
    assert _binding("sub_three") == (bound.id, tenant.id)


# --- (4) an ambiguous NEW mirror binds to nobody -------------------------------

@pytest.mark.django_db
def test_an_ambiguous_new_mirror_is_bound_by_neither_the_sync_nor_the_webhook():
    """(4) Two holders, no mirror. The anchor's sync bound the holder its query
    returned last; now neither path chooses, and the ERROR names both."""
    tenant = _tenant("T", "acct_four")
    a = _customer(tenant, "cust-a", "cus_amb")
    b = _customer(tenant, "cust-b", "cus_amb")

    with _captured() as log:
        for plan in ("index", "sequential"):
            with _forced_plan(plan, tenant):
                assert _sync(tenant, _sub("sub_four", "cus_amb")) == {
                    "synced": 0, "skipped": 1, "errors": 0}
        response = _deliver_created(_sub("sub_four", "cus_amb"), account="acct_four",
                                    event_id="evt_four")

    assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_four").exists()
    assert response.status_code == 500                    # Stripe redelivers
    row = _row("evt_four")
    assert (row.status, row.failure_reason["retryable"]) == ("failed", True)
    ambiguous = log.named("subscription.mirror_ambiguous")
    assert len(ambiguous) == 3                            # two syncs, one webhook
    assert all(r.levelno == logging.ERROR for r in ambiguous)
    data = ambiguous[-1].data
    assert (data["holder_count"], data["via"]) == (2, "webhook")
    assert {h["customer_id"] for h in data["holders"]} == {str(a.id), str(b.id)}


@pytest.mark.django_db
def test_the_ambiguous_webhook_raises_the_retryable_kind():
    """(4) The handler itself: an ambiguity is an ``ObjectDoesNotExist`` (no
    unique owner exists), the kind the receiver records retryable without a
    traceback — never a guessed mirror."""
    from apps.subscriptions.api.webhooks import handle_subscription_created
    tenant = _tenant("T", "acct_four_b")
    _customer(tenant, "cust-a", "cus_amb")
    _customer(tenant, "cust-b", "cus_amb")
    event = a_subscription_event("evt_four_b", "customer.subscription.created",
                                 _sub("sub_four_b", "cus_amb"), account="acct_four_b")
    with pytest.raises(ObjectDoesNotExist):
        handle_subscription_created(event)
    assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_four_b").exists()


# --- (5) a NEW mirror nobody holds stays unmirrored ----------------------------

@pytest.mark.django_db
def test_a_new_mirror_with_no_holder_stays_unmirrored_and_says_so():
    """(5) No customer holds the Stripe id: nothing is bound, nothing guessed,
    and the structured line says it was unresolved (not ambiguous)."""
    tenant = _tenant("T", "acct_five")
    _customer(tenant, "cust-a", "cus_somebody_else")

    with _captured() as log:
        assert _sync(tenant, _sub("sub_five", "cus_nobody")) == {
            "synced": 0, "skipped": 1, "errors": 0}
        response = _deliver_created(_sub("sub_five", "cus_nobody"), account="acct_five",
                                    event_id="evt_five")

    assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_five").exists()
    assert response.status_code == 500
    assert _row("evt_five").failure_reason["retryable"] is True
    unresolved = log.named("subscription.mirror_unresolved")
    assert [r.data["via"] for r in unresolved] == ["sync", "webhook"]
    assert [r.levelno for r in unresolved] == [logging.INFO, logging.WARNING]
    assert all(r.data["holder_count"] == 0 for r in unresolved)
    assert not log.named("subscription.mirror_ambiguous")


# --- (6) the ambiguity removed through the supported maintenance path --------

@pytest.mark.django_db
def test_removing_the_ambiguity_lets_the_next_sync_bind_once():
    """(6) Ambiguous -> an operator clears the wrong customer's Stripe id in
    the admin -> the next hourly sync binds the one remaining holder -> the
    pass after it binds nothing new."""
    tenant = _tenant("T", "acct_six")
    # The admin change form requires non-empty metadata (C3's admin tests).
    right = _customer(tenant, "cust-a", "cus_six", metadata={"crm": "a"})
    wrong = _customer(tenant, "cust-b", "cus_six", metadata={"crm": "b"})

    assert _sync(tenant, _sub("sub_six", "cus_six"))["skipped"] == 1
    assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_six").exists()

    clear_stripe_customer_id_in_the_admin(wrong)

    assert _sync(tenant, _sub("sub_six", "cus_six")) == {"synced": 1, "skipped": 0, "errors": 0}
    mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_six")
    assert (mirror.customer_id, mirror.tenant_id) == (right.id, tenant.id)

    _sync(tenant, _sub("sub_six", "cus_six"))
    assert list(StripeSubscription.objects.filter(stripe_subscription_id="sub_six")
                .values_list("id", "customer_id")) == [(mirror.id, right.id)]


# --- (7) two same-mode tenants on one connected account -----------------------

@pytest.mark.django_db
def test_two_tenants_on_one_account_neither_create_nor_steal_and_never_flip():
    """(7) Probe C2: tenants X and Y share ``acct_shared`` and both hold
    ``cus_s``. The anchor's syncs moved one mirror X -> Y -> X."""
    x = _tenant("X", "acct_shared")
    y = _tenant("Y", "acct_shared")
    _customer(x, "x-cust", "cus_s")
    _customer(y, "y-cust", "cus_s")

    # A NEW subscription: ambiguous in the account-wide namespace.
    assert _sync(x, _sub("sub_new", "cus_s"))["skipped"] == 1
    assert _sync(y, _sub("sub_new", "cus_s"))["skipped"] == 1
    assert _deliver_created(_sub("sub_new", "cus_s"), account="acct_shared",
                            event_id="evt_seven").status_code == 500
    assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_new").exists()

    # An EXISTING mirror bound to X: Y's sync writes nothing of X's.
    x_mirror = _mirror(x, Customer.objects.get(external_id="x-cust"), "sub_old")
    for tenant in (y, x, y):
        _sync(tenant, _sub("sub_old", "cus_s"))
        assert _binding("sub_old") == (x_mirror.customer_id, x.id)
    x_mirror.refresh_from_db()
    assert x_mirror.status == "active"     # refreshed by X's own sync only


@pytest.mark.django_db
def test_another_tenants_sync_leaves_a_bound_mirror_unwritten():
    """(7) Tenant Y's sync skips X's mirror entirely: not even its facts."""
    x = _tenant("X", "acct_shared_b")
    y = _tenant("Y", "acct_shared_b")
    holder = _customer(x, "x-cust", "cus_s")
    _customer(y, "y-cust", "cus_s")
    mirror = _mirror(x, holder, "sub_x")
    assert _sync(y, _sub("sub_x", "cus_s")) == {"synced": 0, "skipped": 1, "errors": 0}
    mirror.refresh_from_db()
    assert (mirror.status, mirror.stripe_product_name, mirror.tenant_id) == (
        "trialing", "Old", x.id)


# --- (8) the unique holder is another tenant's --------------------------------

@pytest.mark.django_db
def test_a_tenant_sync_leaves_another_tenants_unique_holder_to_that_tenant():
    """(8) Only tenant B holds ``cus_b`` on the shared account. Tenant A's
    on-demand sync creates nothing and writes nothing of B's; B's own sync
    binds it, and so does the account-scoped webhook."""
    a = _tenant("A", "acct_eight")
    b = _tenant("B", "acct_eight")
    holder = _customer(b, "b-cust", "cus_b")

    assert _sync(a, _sub("sub_eight", "cus_b")) == {"synced": 0, "skipped": 1, "errors": 0}
    assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_eight").exists()
    assert _sync(b, _sub("sub_eight", "cus_b")) == {"synced": 1, "skipped": 0, "errors": 0}
    assert _binding("sub_eight") == (holder.id, b.id)
    # A's next sync still writes nothing of B's.
    before = StripeSubscription.objects.get(stripe_subscription_id="sub_eight").last_synced_at
    _sync(a, _sub("sub_eight", "cus_b", status="past_due"))
    after = StripeSubscription.objects.get(stripe_subscription_id="sub_eight")
    assert (after.status, after.last_synced_at, after.tenant_id) == ("active", before, b.id)

    # The account-scoped webhook binds a fresh one to B's holder.
    assert _deliver_created(_sub("sub_eight_w", "cus_b"), account="acct_eight",
                            event_id="evt_eight").status_code == 200
    assert _binding("sub_eight_w") == (holder.id, b.id)


# --- (9) livemode separates a live tenant from its sandbox --------------------

@pytest.mark.django_db
def test_a_live_tenant_and_its_sandbox_stay_separated_by_livemode(settings):
    """(9) The intentional same-account posture: one ``acct_`` and one
    ``cus_`` in both modes, kept apart by livemode at both paths."""
    from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
    from apps.subscriptions.api.webhooks import handle_subscription_created

    settings.STRIPE_TEST_SECRET_KEY = "sk_test_sentinel"
    live = _tenant("Live", "acct_pair")
    sandbox = get_or_create_sandbox(live)
    Tenant.objects.filter(id=sandbox.id).update(stripe_connected_account_id="acct_pair",
                                                charges_enabled=True)
    sandbox.refresh_from_db()
    live_holder = _customer(live, "alice", "cus_same")
    sandbox_holder = _customer(sandbox, "alice", "cus_same")

    for sub_id, livemode in (("sub_live", True), ("sub_test", False)):
        handle_subscription_created(a_subscription_event(
            f"evt_{sub_id}", "customer.subscription.created",
            _sub(sub_id, "cus_same"), account="acct_pair", livemode=livemode))
    assert _binding("sub_live") == (live_holder.id, live.id)
    assert _binding("sub_test") == (sandbox_holder.id, sandbox.id)

    assert _sync(live, _sub("sub_live_2", "cus_same"))["synced"] == 1
    assert _sync(sandbox, _sub("sub_test_2", "cus_same"))["synced"] == 1
    assert _binding("sub_live_2") == (live_holder.id, live.id)
    assert _binding("sub_test_2") == (sandbox_holder.id, sandbox.id)


# --- (10) _persist_mirror never overwrites another binding -------------------

def _plan(tenant):
    return a_plan(tenant=tenant, key="pro", name="Pro", access_fee_micros=49_000_000,
                  interval="month", stripe_access_price_id="price_4900",
                  provisioned_at=timezone.now())


@pytest.mark.django_db
def test_persist_mirror_refuses_a_mirror_bound_to_someone_else():
    """(10) The mirror is bound to B; UBB persists a subscription it opened
    for A. The anchor's update_or_create rebound it to A."""
    from apps.subscriptions.orchestration.service import (
        OrchestrationError, SubscriptionOrchestrator)
    tenant = _tenant("T", "acct_ten")
    a = _customer(tenant, "a", "cus_a")
    b = _customer(tenant, "b", "cus_b")
    _mirror(tenant, b, "sub_ten")
    sub = a_stripe_subscription("sub_ten", "cus_a", "active",
                                items=[a_licensed_item(4900, item_id="si_ten")])

    with pytest.raises(OrchestrationError, match="never rewritten"):
        SubscriptionOrchestrator._persist_mirror(tenant, a, _plan(tenant), sub)

    assert _binding("sub_ten") == (b.id, tenant.id)
    assert not CustomerSubscriptionItem.objects.filter(stripe_subscription_item_id="si_ten").exists()


@pytest.mark.django_db
def test_persist_mirror_confirms_its_own_binding_and_refreshes_the_facts():
    """(10) The same owner again (an idempotent subscribe replay): confirmed,
    and only the mutable facts move."""
    from apps.subscriptions.orchestration.service import SubscriptionOrchestrator
    tenant = _tenant("T", "acct_ten_b")
    a = _customer(tenant, "a", "cus_a")
    mirror = _mirror(tenant, a, "sub_ten_b")
    sub = a_stripe_subscription("sub_ten_b", "cus_a", "active",
                                items=[a_licensed_item(4900, item_id="si_ten_b")])
    SubscriptionOrchestrator._persist_mirror(tenant, a, _plan(tenant), sub)
    mirror.refresh_from_db()
    assert (mirror.customer_id, mirror.tenant_id, mirror.status) == (a.id, tenant.id, "active")


# --- (11) the webhook racing UBB's own subscribe ------------------------------

@pytest.mark.django_db
def test_an_ambiguous_webhook_before_persist_mirror_retries_then_finds_the_binding():
    """(11) UBB opens the subscription for A; another customer also holds the
    Stripe id; the ``created`` webhook beats ``_persist_mirror``."""
    from apps.subscriptions.orchestration.service import SubscriptionOrchestrator
    tenant = _tenant("T", "acct_eleven")
    a = _customer(tenant, "a", "cus_r")
    _customer(tenant, "z", "cus_r")
    sub_dict = _sub("sub_eleven", "cus_r")

    # 1. The webhook fails retryably and guesses no mirror.
    assert _deliver_created(sub_dict, account="acct_eleven",
                            event_id="evt_eleven").status_code == 500
    assert _row("evt_eleven").failure_reason["retryable"] is True
    assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_eleven").exists()

    # 2. _persist_mirror binds A, the owner UBB opened it for.
    SubscriptionOrchestrator._persist_mirror(
        tenant, a, _plan(tenant), stripe.Subscription.construct_from(sub_dict, SK))
    assert _binding("sub_eleven") == (a.id, tenant.id)

    # 3. Stripe's redelivery finds the mirror first and succeeds.
    assert _deliver_created(sub_dict, account="acct_eleven",
                            event_id="evt_eleven").status_code == 200
    assert _row("evt_eleven").status == "succeeded"

    # 4. A later sync cannot move it.
    for plan in ("index", "sequential"):
        with _forced_plan(plan, tenant):
            _sync(tenant, sub_dict)
        assert _binding("sub_eleven") == (a.id, tenant.id)
