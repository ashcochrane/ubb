"""F3.2 parity gate: aggregate_lines output must be byte-identical after its
metering reads moved behind the apps.metering.queries contract.

The pre-F3.2 per-event Python loops are inlined below VERBATIM as the
reference implementation. Fixtures are adversarial on the label semantics:
an EMPTY-STRING value and an empty slot must ALL collapse into "(other)" —
note this differs from the analytics contract, where an absent value carries a
null and a status of its own rather than a heading.

⚠ **THE BAG READING WAS THE OTHER HALF OF THIS SUITE AND IS GONE (#503, slice 7
§11).** This docstring used to say the `tag:` prefix "keeps the spelling it is
published under, which is slice 7's to migrate onto the declared grouping
contract" — and this is that migration. Invoice grouping now takes one axis of
the same vocabulary every chart uses, so there is no free-text key branch left
to hold parity against, and the reference implementation loses it with the
reader it mirrors. **What parity still means, and what makes it worth keeping:**
the SLOT branch is unchanged behaviour reached through a new request word, so
the pre-F3.2 loop is still the independent second opinion on every label,
collapse and tiebreak this surface produces.

**The money-only rule is not parity's to check and is asserted elsewhere.** The
reference implementation totals every posting whatever its revenue state, which
is what it did; `test_invoice_lines_take_the_one_vocabulary.py` owns the claim
that a waived charge and a fixed-price unit's constituent calls produce no line,
so the fixtures here deliberately carry none of either — a parity fixture whose
two sides are entitled to disagree proves nothing about either.
"""
import datetime
from collections import defaultdict
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import Posting
from apps.billing.invoicing.models import PostpaidUsageConfig, PostpaidResidualLedger
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService
from apps.platform.grouping_fields.services import DimensionService
from core.time_windows import utc_day_start

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
PS2, PE2 = datetime.date(2026, 7, 1), datetime.date(2026, 8, 1)
# Fixture events must be stamped explicitly inside [PS, PE): effective_at defaults
# to "now", which is only inside a hardcoded window until the calendar rolls past it.
MID = timezone.make_aware(timezone.datetime(2026, 6, 15))


# --- pre-F3.2 reference implementations (inlined verbatim from aggregate_lines) ---

def _old_business_lines(tenant, customer, period_start, period_end):
    seats = {s.id: s.external_id for s in Customer.all_objects.filter(parent=customer)}
    if not seats:
        return 0, []
    qs = Posting.objects.filter(
        tenant=tenant, customer_id__in=list(seats.keys()),
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end))
    agg = defaultdict(int)
    for cid, billed in qs.values_list("customer_id", "billed_cost_micros"):
        agg[seats.get(cid, "(seat)")] += billed or 0
    lines = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
    return sum(a for _, a in lines), lines


def _old_grouped_lines(tenant, customer, period_start, period_end, slot):
    """The pre-F3.2 loop, over the slot the chosen axis resolves to.

    It took the stored configuration's own word and branched on the `tag:`
    prefix; #503 deleted that branch with the reader it mirrors, so it takes the
    COLUMN now. Nothing else about it moved — same query, same `or "(other)"`,
    same sort — which is what keeps it an independent opinion rather than a
    paraphrase of the code under test.
    """
    qs = Posting.objects.filter(
        tenant=tenant, customer=customer,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end))
    agg = defaultdict(int)
    for pid, billed in qs.values_list(slot, "billed_cost_micros"):
        agg[pid or "(other)"] += billed or 0
    lines = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
    return sum(a for _, a in lines), lines


def _grouped_by_a_declared_field(tenant, key="product", slot="grouping_field_1"):
    """Declare the axis and configure the invoice on it, returning its slot.

    Since #503 the stored value is an axis word rather than a column, so a
    fixture that wants lines grouped by a slot has to declare the field bound to
    it — and the reference implementation reads that slot directly, which is
    exactly the independence the parity is for.
    """
    DimensionService.declare(tenant, key=key, slot=slot, scope="event")
    PostpaidUsageConfig.objects.create(
        tenant=tenant, invoice_line_grouping=f"field:{key}")
    return slot


def _ev(t, c, key, billed, **kw):
    kw.setdefault("effective_at", MID)
    return Posting.objects.create(
        tenant=t, customer=c, idempotency_key=key,
        provider_cost_micros=1, billed_cost_micros=billed, **kw)


@pytest.mark.django_db
class TestBusinessBranchParity:
    def test_business_three_seats_byte_identical(self):
        t = Tenant.objects.create(name="T", billing_mode="postpaid",
                                  products=["metering", "billing"])
        biz = Customer.objects.create(tenant=t, external_id="biz",
                                      account_type="business", billing_topology="allocated")
        alice = Customer.objects.create(tenant=t, external_id="alice", account_type="seat", parent=biz)
        bob = Customer.objects.create(tenant=t, external_id="bob", account_type="seat", parent=biz)
        carol = Customer.objects.create(tenant=t, external_id="carol", account_type="seat", parent=biz)
        solo = Customer.objects.create(tenant=t, external_id="solo")  # NOT a seat
        _ev(t, alice, "a1", 800_000)
        _ev(t, alice, "a2", 50_000)            # two events aggregate into one seat line
        _ev(t, bob, "b1", 300_000)
        _ev(t, carol, "c1", 300_000)           # ties with bob -> label tiebreak
        _ev(t, solo, "s1", 999_999)            # excluded: not a seat of biz
        out = _ev(t, alice, "a3", 777_777)     # excluded: outside the window
        Posting.objects.filter(id=out.id).update(
            effective_at=timezone.make_aware(timezone.datetime(2026, 5, 31, 23, 59)))

        old_total, old_lines = _old_business_lines(t, biz, PS, PE)
        new_total, new_lines = PostpaidUsageService.aggregate_lines(t, biz, PS, PE)
        assert new_lines == old_lines
        assert new_total == old_total
        assert new_lines == [("alice", 850_000), ("bob", 300_000), ("carol", 300_000)]
        assert sum(a for _, a in new_lines) == new_total == 1_450_000

    def test_business_no_seats(self):
        t = Tenant.objects.create(name="T", billing_mode="postpaid",
                                  products=["metering", "billing"])
        biz = Customer.objects.create(tenant=t, external_id="biz",
                                      account_type="business", billing_topology="allocated")
        assert PostpaidUsageService.aggregate_lines(t, biz, PS, PE) == (0, [])


@pytest.mark.django_db
class TestGroupByBranchParity:
    def test_a_declared_fields_many_values_are_byte_identical(self):
        """THE FIXTURE THE BAG TEST USED TO CARRY, ON THE AXIS THAT REPLACED IT.

        ⚠ **IT IS ADVERSARIAL ON MERGING NOW RATHER THAN ON ABSENCE, AND THAT IS
        A REAL LOSS WORTH NAMING.** The bag had FOUR ways to have no value — a
        missing key, an absent bag, an empty dict, a JSON-null — and the old
        fixture ran one posting through each to prove they all landed in one
        line. A declared slot has ONE, the empty string (`NULL` being
        unreachable on a `blank=True, default=""` column), so that variety has
        nowhere left to come from: it went with the unbounded keyspace, which is
        the point of the change rather than a gap in its testing.

        What survives is the half that still has teeth: six postings across two
        headings with four of them valueless, so the merge, the total and the
        sort are all still held to the pre-F3.2 loop.
        """
        t = Tenant.objects.create(name="T", billing_mode="postpaid",
                                  products=["metering", "billing"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        slot = _grouped_by_a_declared_field(t, key="seat")
        _ev(t, c, "i1", 500_000, grouping_field_1="alice")
        _ev(t, c, "i2", 40_000, grouping_field_1="")      # EMPTY STRING -> (other)
        _ev(t, c, "i3", 300_000, grouping_field_1="")     # merges into (other)
        _ev(t, c, "i4", 20_000, grouping_field_1="")      # and again
        _ev(t, c, "i5", 10_000, grouping_field_1="")      # and again
        _ev(t, c, "i6", 100_000, grouping_field_1="bob")

        old_total, old_lines = _old_grouped_lines(t, c, PS, PE, slot)
        new_total, new_lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert new_lines == old_lines
        assert new_total == old_total
        assert new_lines == [("alice", 500_000), ("(other)", 370_000), ("bob", 100_000)]
        assert sum(a for _, a in new_lines) == new_total == 970_000

    def test_a_declared_fields_empty_value_collapses_to_other(self):
        t = Tenant.objects.create(name="T", billing_mode="postpaid",
                                  products=["metering", "billing"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        slot = _grouped_by_a_declared_field(t)
        _ev(t, c, "i1", 800_000, grouping_field_1="chat")
        _ev(t, c, "i2", 150_000, grouping_field_1="")           # EMPTY -> (other)
        _ev(t, c, "i3", 50_000, grouping_field_1="")            # merges into (other)
        _ev(t, c, "i4", 200_000, grouping_field_1="api")        # ties with (other) -> label tiebreak

        old_total, old_lines = _old_grouped_lines(t, c, PS, PE, slot)
        new_total, new_lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert new_lines == old_lines
        assert new_total == old_total
        # "(other)" sorts before "api" on the label tiebreak ('(' < 'a').
        assert new_lines == [("chat", 800_000), ("(other)", 200_000), ("api", 200_000)]
        assert sum(a for _, a in new_lines) == new_total == 1_200_000


@pytest.mark.django_db
class TestResidualCarryAcrossPeriods:
    def test_subcent_residual_carries_unchanged(self):
        """Cent-flooring + carry (Wave 4.5 / F1.1) is downstream of aggregate_lines;
        with identical lines the residual chain must be unchanged across two periods."""
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="postpaid",
                                  stripe_connected_account_id="acct_x", charges_enabled=True)
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        _grouped_by_a_declared_field(t)
        # June: chat 15_500 (1.55c), "" 7_800 (0.78c)
        _ev(t, c, "j1", 15_500, grouping_field_1="chat")
        _ev(t, c, "j2", 7_800, grouping_field_1="")
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="obj_1")
            rec1 = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec1.refresh_from_db()
        # chat: 15_500 -> 1 cent, residual 5_500; (other): 7_800+5_500=13_300 -> 1 cent, residual 3_300
        assert rec1.status == "pushed"
        assert rec1.carry_in_micros == 0
        assert rec1.residual_micros == 3_300
        assert PostpaidResidualLedger.objects.get(customer=c).balance_micros == 3_300

        # July: chat 26_000 (2.6c) + carry 3_300 = 29_300 -> 2 cents, residual 9_300
        ev = _ev(t, c, "y1", 26_000, grouping_field_1="chat")
        Posting.objects.filter(id=ev.id).update(
            effective_at=timezone.make_aware(timezone.datetime(2026, 7, 15)))
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="obj_2")
            rec2 = PostpaidUsageService.push_customer_period(t, c, PS2, PE2)
        rec2.refresh_from_db()
        assert rec2.status == "pushed"
        assert rec2.carry_in_micros == 3_300
        assert rec2.residual_micros == 9_300
        assert PostpaidResidualLedger.objects.get(customer=c).balance_micros == 9_300
