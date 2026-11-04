"""Who a postpaid usage invoice is issued to: the canonical billing owner.

R10 Stage C3, F-7 (PLAN §5.3 and the rulings under LAUNCHER C3). The monthly
close targets `Customer.resolve_billing_owner()` — a POOLED seat's business,
and everyone else themselves, an ALLOCATED seat included — and an owner's
invoice sums exactly the postings pinned to it as their billing owner
(`Posting.billing_owner_id`, written by the recording path from the same
resolver). Until C3 the close keyed ANY seat with a parent on that parent and
a business summed every seat by `parent=`, so an allocated seat's usage was
invoiced to its business (Stage B step 14).

The four tests below the helpers held that misbilling in place, on an
`allocated` business whose seats' postings named no owner at all. They are
rewritten to the ruled outcome: the roll-up into one business invoice is a
POOLED business's, with its seats' postings pinned to it as the recording path
pins them, and the allocated topology bills each seat to itself.

This decides the owner of a NEW usage invoice from the economic facts at
close. It never reinterprets the owner of one that already exists (C2's
historical-owner rules, PLAN §7 items 27–29).
"""
import contextlib
import datetime
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService
from apps.billing.invoicing.tasks import _prior_month, close_postpaid_usage_periods
from apps.metering.usage.tests._helpers import a_posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
# Fixture events must be stamped explicitly inside [PS, PE): effective_at defaults
# to "now", which is only inside a hardcoded window until the calendar rolls past it.
MID = timezone.make_aware(timezone.datetime(2026, 6, 15))


def _recorded(t, customer, key, billed, effective_at=MID):
    """A posting as the recording path writes one: pinned to the billing owner
    `resolve_billing_owner()` names at the moment it is recorded."""
    return a_posting(
        tenant=t, customer=customer, idempotency_key=key,
        provider_cost_micros=1, billed_cost_micros=billed,
        effective_at=effective_at,
        billing_owner_id=customer.resolve_billing_owner().id)


def _prior_mid():
    """Mid-month of the period the monthly close addresses."""
    start, _end = _prior_month()
    return timezone.make_aware(timezone.datetime(start.year, start.month, 15))


def _charge_ready_tenant():
    return Tenant.objects.create(
        name="T", products=["metering", "billing"], billing_mode="postpaid",
        stripe_connected_account_id="acct_x", charges_enabled=True)


def _business(t, external_id, topology, stripe_customer_id=""):
    return Customer.objects.create(
        tenant=t, external_id=external_id, account_type="business",
        billing_topology=topology, stripe_customer_id=stripe_customer_id)


def _seat(t, biz, external_id, stripe_customer_id=""):
    return Customer.objects.create(
        tenant=t, external_id=external_id, account_type="seat", parent=biz,
        stripe_customer_id=stripe_customer_id)


@contextlib.contextmanager
def _closing():
    """The close, with every Stripe call answered by one stand-in invoice."""
    with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
         patch("apps.platform.events.tasks.process_single_event"):
        mock_sc.return_value = MagicMock(id="obj_1")
        yield mock_sc


def _invoiced_stripe_customers(mock_sc):
    """The Stripe customer each `Invoice.create` named, in call order."""
    return [ck.kwargs["customer"] for ck in mock_sc.call_args_list
            if ck.kwargs.get("idempotency_key", "").startswith("usage-invoice-")]


def _rows(t):
    return {r.customer.external_id: r for r in
            CustomerUsageInvoice.objects.filter(tenant=t).select_related("customer")}


# --- The four tests that held the misbilling, rewritten to the ruled outcome --


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_business_aggregates_across_seats_one_line_per_seat():
    t = Tenant.objects.create(name="T", billing_mode="postpaid", products=["metering", "billing"])
    biz = _business(t, "biz", "pooled")
    s1 = _seat(t, biz, "alice")
    s2 = _seat(t, biz, "bob")
    _recorded(t, s1, "i1", 800_000)
    _recorded(t, s2, "i2", 300_000)
    total, lines = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
    assert total == 1_100_000 and sum(a for _, a in lines) == total
    assert dict(lines)["alice"] == 800_000 and dict(lines)["bob"] == 300_000


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_close_rolls_seats_into_one_business_invoice():
    t = _charge_ready_tenant()
    biz = _business(t, "biz", "pooled", stripe_customer_id="cus_biz")
    s1 = _seat(t, biz, "alice")
    s2 = _seat(t, biz, "bob")
    _recorded(t, s1, "i1", 800_000, effective_at=_prior_mid())
    _recorded(t, s2, "i2", 300_000, effective_at=_prior_mid())
    with _closing() as mock_sc:
        close_postpaid_usage_periods()
    invs = CustomerUsageInvoice.objects.filter(tenant=t)
    assert invs.count() == 1                       # ONE invoice, keyed on the business
    inv = invs.first()
    assert str(inv.customer_id) == str(biz.id) and inv.total_billed_micros == 1_100_000
    assert inv.line_items.count() == 2             # one line per seat
    assert not CustomerUsageInvoice.objects.filter(customer__in=[s1, s2]).exists()  # seats not invoiced
    assert _invoiced_stripe_customers(mock_sc) == ["cus_biz"]


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_business_total_unchanged_when_seat_soft_deleted_mid_period():
    t = Tenant.objects.create(name="T", billing_mode="postpaid", products=["metering", "billing"])
    biz = _business(t, "biz", "pooled")
    s1 = _seat(t, biz, "alice")
    s2 = _seat(t, biz, "bob")
    _recorded(t, s1, "i1", 800_000)
    _recorded(t, s2, "i2", 300_000)
    before, _ = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
    s2.soft_delete()
    after, lines = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
    assert after == before == 1_100_000
    assert dict(lines)["bob"] == 300_000


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_close_invoices_soft_deleted_seat_usage():
    t = _charge_ready_tenant()
    biz = _business(t, "biz", "pooled", stripe_customer_id="cus_biz")
    s1 = _seat(t, biz, "alice")
    _recorded(t, s1, "i1", 500_000, effective_at=_prior_mid())
    s1.soft_delete()
    with _closing():
        close_postpaid_usage_periods()
    invs = CustomerUsageInvoice.objects.filter(tenant=t)
    assert invs.count() == 1
    inv = invs.first()
    assert str(inv.customer_id) == str(biz.id)
    assert inv.total_billed_micros == 500_000


# --- The ruled outcome for the allocated topology (red on the C2 anchor) ------


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_an_allocated_business_owes_none_of_its_seats_usage():
    """Each allocated seat is its own billing owner, so its postings are pinned
    to itself and none of them is the business's to invoice."""
    t = Tenant.objects.create(name="T", billing_mode="postpaid", products=["metering", "billing"])
    biz = _business(t, "biz", "allocated")
    _recorded(t, _seat(t, biz, "alice"), "i1", 800_000)
    _recorded(t, _seat(t, biz, "bob"), "i2", 300_000)
    assert PostpaidUsageService.aggregate_lines(t, biz, PS, PE) == (0, [])


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_close_bills_each_allocated_seat_to_itself():
    t = _charge_ready_tenant()
    biz = _business(t, "biz", "allocated", stripe_customer_id="cus_biz")
    alice = _seat(t, biz, "alice", stripe_customer_id="cus_alice")
    bob = _seat(t, biz, "bob", stripe_customer_id="cus_bob")
    _recorded(t, alice, "i1", 800_000, effective_at=_prior_mid())
    _recorded(t, bob, "i2", 300_000, effective_at=_prior_mid())
    with _closing() as mock_sc:
        close_postpaid_usage_periods()
    rows = _rows(t)
    assert set(rows) == {"alice", "bob"}           # no business row at all
    assert rows["alice"].status == "pushed" and rows["alice"].total_billed_micros == 800_000
    assert rows["bob"].status == "pushed" and rows["bob"].total_billed_micros == 300_000
    assert sorted(_invoiced_stripe_customers(mock_sc)) == ["cus_alice", "cus_bob"]


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_close_bills_a_soft_deleted_allocated_seat_to_itself():
    t = _charge_ready_tenant()
    biz = _business(t, "biz", "allocated", stripe_customer_id="cus_biz")
    alice = _seat(t, biz, "alice", stripe_customer_id="cus_alice")
    _recorded(t, alice, "i1", 500_000, effective_at=_prior_mid())
    alice.soft_delete()
    with _closing() as mock_sc:
        close_postpaid_usage_periods()
    rows = _rows(t)
    assert set(rows) == {"alice"}
    assert rows["alice"].total_billed_micros == 500_000
    assert _invoiced_stripe_customers(mock_sc) == ["cus_alice"]


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_one_close_bills_every_topology_to_its_canonical_owner():
    """Standalone, pooled seat and allocated seat in ONE close: one invoice per
    canonical billing owner, each on its own Stripe customer."""
    t = _charge_ready_tenant()
    solo = Customer.objects.create(tenant=t, external_id="solo", stripe_customer_id="cus_solo")
    pooled = _business(t, "pooled-biz", "pooled", stripe_customer_id="cus_pooled")
    p1, p2 = _seat(t, pooled, "p1"), _seat(t, pooled, "p2")
    allocated = _business(t, "allocated-biz", "allocated", stripe_customer_id="cus_allocated")
    a1 = _seat(t, allocated, "a1", stripe_customer_id="cus_a1")
    a2 = _seat(t, allocated, "a2", stripe_customer_id="cus_a2")
    for customer, key, billed in [(solo, "s", 200_000), (p1, "p1", 100_000),
                                  (p2, "p2", 50_000), (a1, "a1", 70_000),
                                  (a2, "a2", 30_000)]:
        _recorded(t, customer, key, billed, effective_at=_prior_mid())
    with _closing() as mock_sc:
        close_postpaid_usage_periods()
    rows = _rows(t)
    assert set(rows) == {"solo", "pooled-biz", "a1", "a2"}
    assert {k: r.total_billed_micros for k, r in rows.items()} == {
        "solo": 200_000, "pooled-biz": 150_000, "a1": 70_000, "a2": 30_000}
    assert sorted(li.grouping_field_value for li in rows["pooled-biz"].line_items.all()) == ["p1", "p2"]
    assert all(r.status == "pushed" for r in rows.values())
    assert sorted(_invoiced_stripe_customers(mock_sc)) == [
        "cus_a1", "cus_a2", "cus_pooled", "cus_solo"]


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_an_allocated_seat_whose_usage_priced_at_nothing_is_nothing_to_bill():
    """`billing_owner_recorded_anything` follows the owner: the seat recorded
    something priced at exactly nothing, so its row says `nothing_to_bill` —
    not a business row claiming `no_usage`."""
    t = _charge_ready_tenant()
    biz = _business(t, "biz", "allocated", stripe_customer_id="cus_biz")
    alice = _seat(t, biz, "alice", stripe_customer_id="cus_alice")
    _recorded(t, alice, "i1", 0, effective_at=_prior_mid())
    with _closing() as mock_sc:
        close_postpaid_usage_periods()
    rows = _rows(t)
    assert set(rows) == {"alice"}
    assert rows["alice"].status == "skipped"
    assert rows["alice"].skip_reason == "nothing_to_bill"
    assert _invoiced_stripe_customers(mock_sc) == []


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_the_business_aggregation_takes_only_postings_pinned_to_it():
    """A posting on a seat that names another billing owner is that owner's,
    whatever the seat's parent is: the business sums only what is pinned to
    it, and never reads `parent` to decide."""
    t = Tenant.objects.create(name="T", billing_mode="postpaid", products=["metering", "billing"])
    biz = _business(t, "biz", "pooled")
    s1 = _seat(t, biz, "s1")
    _recorded(t, s1, "pinned-to-biz", 400_000)
    a_posting(tenant=t, customer=s1, idempotency_key="pinned-to-seat",
              provider_cost_micros=1, billed_cost_micros=250_000,
              effective_at=MID, billing_owner_id=s1.id)
    assert PostpaidUsageService.aggregate_lines(t, biz, PS, PE) == (
        400_000, [("s1", 400_000)])


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_a_posting_the_business_recorded_itself_is_on_its_own_invoice():
    t = Tenant.objects.create(name="T", billing_mode="postpaid", products=["metering", "billing"])
    biz = _business(t, "biz", "pooled")
    _recorded(t, _seat(t, biz, "s1"), "seat", 400_000)
    _recorded(t, biz, "own", 100_000)
    assert PostpaidUsageService.aggregate_lines(t, biz, PS, PE) == (
        500_000, [("s1", 400_000), ("biz", 100_000)])


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
def test_stage_b_step_14_an_allocated_seats_backfill_is_billed_to_the_seat():
    """Stage B step 14, end to end through the real recording path: an
    allocated business with one seat; the seat's prior-month usage arrives as
    a backfill of 6,000,000; the close bills it to the SEAT on the seat's own
    Stripe customer, with no business row; and the seat's period is then
    closed to further backfills (the closed-period guard follows the owner —
    under the misbilling it stayed open, so a later backfill was recorded and
    never billed)."""
    from apps.metering.pricing.tests._helpers import (
        a_rule_that_prices_what_it_measures, priced_at)
    from apps.metering.usage.services.usage_service import (
        EffectiveAtError, UsageService)
    from apps.metering.usage.models import Posting

    t = _charge_ready_tenant()
    biz = _business(t, "biz-alloc", "allocated", stripe_customer_id="cus_bizalloc")
    seat = _seat(t, biz, "seat-alloc", stripe_customer_id="cus_seatalloc")
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    eff = month_start - timedelta(days=2)          # in the prior month, inside the window
    a_rule_that_prices_what_it_measures(t, valid_from=eff - timedelta(days=1))
    recorded = UsageService.record_usage(
        t, seat, "seat-prior-month", measurements=priced_at(6_000_000), effective_at=eff)
    assert Posting.objects.get(id=recorded["event_id"]).billing_owner_id == seat.id

    with _closing() as mock_sc:
        close_postpaid_usage_periods()

    rows = _rows(t)
    assert set(rows) == {"seat-alloc"}
    assert rows["seat-alloc"].status == "pushed"
    assert rows["seat-alloc"].total_billed_micros == 6_000_000
    assert _invoiced_stripe_customers(mock_sc) == ["cus_seatalloc"]

    with pytest.raises(EffectiveAtError) as refused:
        UsageService.record_usage(
            t, seat, "seat-prior-month-late", measurements=priced_at(1_000_000),
            effective_at=eff)
    assert refused.value.code == "billing_period_closed"
