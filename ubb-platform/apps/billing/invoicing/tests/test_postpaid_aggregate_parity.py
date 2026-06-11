"""F3.2 parity gate: aggregate_lines output must be byte-identical after its
metering reads moved behind the apps.metering.queries contract.

The pre-F3.2 per-event Python loops are inlined below VERBATIM as the
reference implementation. Fixtures are adversarial on the label semantics:
an EMPTY-STRING tag value, a missing tag key, NULL tags, an empty dict tags,
and an empty product_id must ALL collapse into "(other)" (the `or` in
`(tags or {}).get(key) or "(other)"` maps both ''-valued and absent tags to
the same bucket — note this differs from the analytics contract where ""
stays a distinct dimension).
"""
import datetime
from collections import defaultdict
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.invoicing.models import PostpaidUsageConfig, PostpaidResidualLedger
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService
from core.time_windows import utc_day_start

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
PS2, PE2 = datetime.date(2026, 7, 1), datetime.date(2026, 8, 1)


# --- pre-F3.2 reference implementations (inlined verbatim from aggregate_lines) ---

def _old_business_lines(tenant, customer, period_start, period_end):
    seats = {s.id: s.external_id for s in Customer.all_objects.filter(parent=customer)}
    if not seats:
        return 0, []
    qs = UsageEvent.objects.filter(
        tenant=tenant, customer_id__in=list(seats.keys()),
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end))
    agg = defaultdict(int)
    for cid, billed in qs.values_list("customer_id", "billed_cost_micros"):
        agg[seats.get(cid, "(seat)")] += billed or 0
    lines = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
    return sum(a for _, a in lines), lines


def _old_grouped_lines(tenant, customer, period_start, period_end, group_by):
    qs = UsageEvent.objects.filter(
        tenant=tenant, customer=customer,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end))
    agg = defaultdict(int)
    if group_by.startswith("tag:"):
        tag_key = group_by[4:]
        for tags, billed in qs.values_list("tags", "billed_cost_micros"):
            label = (tags or {}).get(tag_key) or "(other)"
            agg[label] += billed or 0
    else:  # "product_id"
        for pid, billed in qs.values_list("product_id", "billed_cost_micros"):
            agg[pid or "(other)"] += billed or 0
    lines = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
    return sum(a for _, a in lines), lines


def _ev(t, c, key, billed, **kw):
    return UsageEvent.objects.create(
        tenant=t, customer=c, request_id=f"r-{key}", idempotency_key=key,
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
        UsageEvent.objects.filter(id=out.id).update(
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
    def test_tag_grouping_empty_string_and_missing_collapse_to_other(self):
        t = Tenant.objects.create(name="T", billing_mode="postpaid",
                                  products=["metering", "billing"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="tag:seat")
        _ev(t, c, "i1", 500_000, tags={"seat": "alice"})
        _ev(t, c, "i2", 40_000, tags={"seat": ""})       # EMPTY STRING value -> (other)
        _ev(t, c, "i3", 300_000, tags=None)               # NULL tags -> (other)
        _ev(t, c, "i4", 20_000, tags={})                  # empty dict -> (other)
        _ev(t, c, "i5", 10_000, tags={"other": "x"})      # key missing -> (other)
        _ev(t, c, "i6", 100_000, tags={"seat": "bob"})

        old_total, old_lines = _old_grouped_lines(t, c, PS, PE, "tag:seat")
        new_total, new_lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert new_lines == old_lines
        assert new_total == old_total
        assert new_lines == [("alice", 500_000), ("(other)", 370_000), ("bob", 100_000)]
        assert sum(a for _, a in new_lines) == new_total == 970_000

    def test_product_grouping_empty_product_id_collapses_to_other(self):
        t = Tenant.objects.create(name="T", billing_mode="postpaid",
                                  products=["metering", "billing"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="product_id")
        _ev(t, c, "i1", 800_000, product_id="chat")
        _ev(t, c, "i2", 150_000, product_id="")           # EMPTY product_id -> (other)
        _ev(t, c, "i3", 50_000, product_id="")            # merges into (other)
        _ev(t, c, "i4", 200_000, product_id="api")        # ties with (other) -> label tiebreak

        old_total, old_lines = _old_grouped_lines(t, c, PS, PE, "product_id")
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
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="product_id")
        # June: chat 15_500 (1.55c), "" 7_800 (0.78c)
        _ev(t, c, "j1", 15_500, product_id="chat")
        _ev(t, c, "j2", 7_800, product_id="")
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
        ev = _ev(t, c, "y1", 26_000, product_id="chat")
        UsageEvent.objects.filter(id=ev.id).update(
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
