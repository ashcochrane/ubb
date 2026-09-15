"""Migration `0015` carries the recurring revenue amount onto the per-period
records that replaced it (#496, slice 7 §9, ADR-0007 §1).

⚠ **THE ARITHMETIC IS THE SUBJECT, NOT THE SCHEMA.** What the retired model
held was one amount per customer and a span it applied over; what the accrual
DID with that amount was divide it by day across every calendar month the span
touched, which is a fact about a function rather than about a column. So these
cases hold the migration's pure period-splitter to that function's own
arithmetic, month by month, and then hold the whole pass to the one thing a
carry has to be: **a tenant's revenue history reads the same afterwards.**

⚠ **THE DATA CASES CANNOT USE THE LIVE REGISTRY, WHICH IS THE ONE WAY THIS
MODULE DIFFERS FROM `gating/0014`'s.** That migration renamed a column on a
model that still exists, so its tests could plant rows through the live model.
This one DELETES its source, so at HEAD there is no `CustomerRevenueProfile`
and no `ubb_customer_revenue_profile` table to plant into. The cases below take
the state the migration's own predecessor leaves — `project_state` of `0014` —
and create that state's table for the duration of the class. That is the
retired model exactly as `0015` meets it, rather than a stand-in written here
that could drift from it.

⚠ **WHAT THEY STILL DO NOT COVER, said rather than left to be discovered:**
nothing here drives `0015` through the migration RUNNER. The added column and
the dropped table are the runner's, and `makemigrations --check` plus
`manage.py check` cover that half.
"""
import datetime
import importlib
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.subscriptions.economics.models import TenantSuppliedRevenue
from apps.subscriptions.economics.revenue import SuppliedRevenueService
from apps.subscriptions.economics.services import MARGIN_REVENUE_BASIS
from core.vocabulary import (
    RECOGNITION_METHOD_STRAIGHT_LINE, REVENUE_BASIS_RECOGNISED,
    REVENUE_BASIS_RECORDED)

MIGRATION = importlib.import_module(
    "apps.subscriptions.migrations."
    "0015_the_recurring_amount_becomes_the_periods_it_was_always_about")

#: The state `0015` starts from — the last one in which the retired model still
#: exists. Named rather than computed so that a later migration inserted before
#: `0015` fails here instead of silently changing what these cases plant into.
THE_STATE_BEFORE = ("subscriptions",
                    "0014_a_tenant_may_state_what_it_earned_elsewhere")


def a_profile(effective_from, effective_to=None, amount=500_000_000,
              interval="month", currency="usd"):
    """The retired model's fields, as the migration's splitter takes them.

    A plain namespace rather than the model, because `carried_rows` is pure.
    It carries all FIVE of the model's own fields even though the splitter
    reads only four: the fifth, `interval`, is here precisely so that
    `TestTheLabelAndTheArithmeticDisagreed` below can vary it and show that
    nothing moves.
    """
    return SimpleNamespace(
        recurring_amount_micros=amount, interval=interval, currency=currency,
        effective_from=effective_from, effective_to=effective_to)


class TestTheMethodIsTheRegistrysWord:
    """A migration may not import application code, so it spells the value it
    stamps — and the spelling is held to the constant here rather than trusted."""

    def test_the_stamped_method_is_the_registrys_straight_line(self):
        assert MIGRATION.RECOGNITION_METHOD == RECOGNITION_METHOD_STRAIGHT_LINE

    def test_the_source_reference_says_something(self):
        # Held against the RECORD'S OWN CONSTRAINT rather than against a
        # re-typed copy of the rule: `ck_supplied_revenue_says_where_it_came
        # _from` is `source_reference__regex=r"\S"`, and that regex is read off
        # the model here so the two cannot drift.
        import re
        constraint, = [
            c for c in TenantSuppliedRevenue._meta.constraints
            if c.name == "ck_supplied_revenue_says_where_it_came_from"]
        (lookup, pattern), = constraint.condition.children
        assert lookup == "source_reference__regex"
        assert re.search(pattern, MIGRATION.SOURCE_REFERENCE)


class TestTheSpanBecomesItsCalendarMonths:
    """One row per calendar month the profile's span touched — which is the
    grain the accrual it replaces computed at, not a grain chosen here."""

    def test_a_whole_month_carries_the_whole_amount(self):
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 3, 1), datetime.date(2026, 4, 1)),
            horizon=datetime.date(2026, 6, 1))
        assert len(rows) == 1
        assert rows[0]["period_start"] == datetime.date(2026, 3, 1)
        assert rows[0]["period_end"] == datetime.date(2026, 4, 1)
        assert rows[0]["amount_micros"] == 500_000_000

    def test_three_months_are_three_rows_each_whole(self):
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 1, 1), datetime.date(2026, 4, 1)),
            horizon=datetime.date(2026, 6, 1))
        assert [(r["period_start"].month, r["amount_micros"]) for r in rows] == [
            (1, 500_000_000), (2, 500_000_000), (3, 500_000_000)]

    def test_a_profile_that_began_mid_period_lands_as_a_PART_period(self):
        # ⚠ THE WHOLE REASON §9 RULES THE MID-PERIOD AFFORDANCE INTO THIS
        # SLICE. April has 30 days; a profile beginning on the 14th applied
        # over 17 of them, and the accrual said so by dividing. The row says
        # so by DECLARING the span, which is the fact the retired model could
        # only express through arithmetic nobody could see.
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 4, 14), datetime.date(2026, 5, 1)),
            horizon=datetime.date(2026, 6, 1))
        assert len(rows) == 1
        assert rows[0]["period_start"] == datetime.date(2026, 4, 14)
        assert rows[0]["period_end"] == datetime.date(2026, 5, 1)
        assert rows[0]["amount_micros"] == 500_000_000 * 17 // 30

    def test_a_profile_that_ended_mid_period_lands_as_a_part_period_too(self):
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 4, 1), datetime.date(2026, 4, 11)),
            horizon=datetime.date(2026, 6, 1))
        assert len(rows) == 1
        assert rows[0]["period_end"] == datetime.date(2026, 4, 11)
        assert rows[0]["amount_micros"] == 500_000_000 * 10 // 30

    def test_every_row_declares_a_span_its_method_can_be_divided_over(self):
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 1, 14), datetime.date(2026, 4, 11)),
            horizon=datetime.date(2026, 6, 1))
        assert rows
        for row in rows:
            assert row["recognition_method"] == RECOGNITION_METHOD_STRAIGHT_LINE
            assert row["period_end"] > row["period_start"]


class TestTheOpenEndedProfileStopsAtTheHorizon:
    """An amount with no end asserted revenue forever; a per-period record
    asserts a period. The horizon is where that difference is paid."""

    def test_it_carries_through_the_month_the_migration_runs_in(self):
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 5, 1), None),
            horizon=datetime.date(2026, 7, 1))
        assert [r["period_start"].month for r in rows] == [5, 6]
        assert rows[-1]["period_end"] == datetime.date(2026, 7, 1)

    def test_it_claims_no_period_after_the_horizon(self):
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 5, 1), None),
            horizon=datetime.date(2026, 7, 1))
        assert all(r["period_end"] <= datetime.date(2026, 7, 1) for r in rows)

    def test_a_profile_whose_own_end_is_earlier_keeps_its_own_end(self):
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 5, 1), datetime.date(2026, 6, 1)),
            horizon=datetime.date(2027, 1, 1))
        assert [r["period_start"].month for r in rows] == [5]

    def test_a_profile_entirely_after_the_horizon_carries_nothing(self):
        assert MIGRATION.carried_rows(
            a_profile(datetime.date(2027, 5, 1), None),
            horizon=datetime.date(2026, 7, 1)) == []


class TestTheLabelAndTheArithmeticDisagreed:
    """⚠ The retired model's interval was DISPLAY ONLY — nothing divided by it.

    A yearly profile of X accrued X *every month*, because the accrual walked
    calendar months and multiplied by the amount without ever consulting the
    interval, while its Stripe sibling one function below it divided a yearly
    amount by twelve. The carry follows the arithmetic, because the arithmetic
    is what a tenant's reported revenue was actually made of; restating that
    history to match a label nothing read would be this migration inventing a
    number rather than moving one.
    """

    def test_a_yearly_interval_carries_the_same_monthly_amount(self):
        # ⚠ NEAR-VACUOUS BY CONSTRUCTION, AND KEPT ANYWAY. `carried_rows` never
        # reads `interval`, so the two calls below are the same call — which is
        # the claim, not a weakness in the case. It is a REGRESSION GUARD: a
        # later reader who finds a dropped field suspicious and "restores" it
        # by dividing a yearly amount by twelve would be silently restating
        # every yearly tenant's revenue history, and this goes red.

        monthly = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 4, 1), datetime.date(2026, 5, 1),
                      interval="month"),
            horizon=datetime.date(2026, 6, 1))
        yearly = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 4, 1), datetime.date(2026, 5, 1),
                      interval="year"),
            horizon=datetime.date(2026, 6, 1))
        assert [r["amount_micros"] for r in yearly] == [
            r["amount_micros"] for r in monthly]

    def test_the_currency_is_the_profiles_own(self):
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 4, 1), datetime.date(2026, 5, 1),
                      currency="gbp"),
            horizon=datetime.date(2026, 6, 1))
        assert [r["currency"] for r in rows] == ["gbp"]


class TestAnAmountOfNothingWasNeverAFigure:
    """The accrual's own first line returned zero for a profile holding zero
    and never looked at its span. Carrying a row for it would turn "the tenant
    configured nothing" into "the tenant earned nothing", which is a claim
    §9's four revenue states keep apart on purpose."""

    def test_a_zero_amount_profile_carries_no_rows(self):
        assert MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 1, 1), datetime.date(2026, 4, 1),
                      amount=0),
            horizon=datetime.date(2026, 6, 1)) == []


class TestTheHistoryReadsTheSameAfterwards:
    """The one property a carry has to have, and it takes BOTH halves.

    ⚠ **SUMMING THE CARRIED ROWS IS NOT THE PROPERTY.** The rows are only half
    of it: what a tenant sees is a window's revenue, and a window is read
    through `SuppliedRevenueService`. So these cases carry the rows and then
    READ them the way margin does — `MARGIN_REVENUE_BASIS`, which is
    `recognised` — over windows that deliberately do NOT line up with the
    rows' spans, and hold the answer to the retired accrual's own arithmetic.

    A version of this that compared row sums over the whole span would pass
    against a reading rule that put every month's amount on the first of the
    month, which is exactly the defect the basis choice exists to avoid.

    The retired accrual is gone, so it is reproduced below from its own
    published arithmetic — per calendar month, prorated by whole days,
    floor-rounded.
    """

    @staticmethod
    def the_accrual_as_it_stood(amount, effective_from, effective_to, start, end):
        import calendar
        eff_start = max(start, effective_from)
        eff_end = end if effective_to is None else min(end, effective_to)
        if eff_end <= eff_start or not amount:
            return 0
        total, cur = 0, eff_start.replace(day=1)
        while cur < eff_end:
            nxt = (cur.replace(year=cur.year + 1, month=1, day=1)
                   if cur.month == 12 else cur.replace(month=cur.month + 1, day=1))
            overlap = (min(eff_end, nxt) - max(eff_start, cur)).days
            total += amount * overlap // calendar.monthrange(cur.year, cur.month)[1]
            cur = nxt
        return total

    @staticmethod
    def as_records(rows):
        """The carried rows as the reading side meets them.

        `attributed_micros` reads four fields off a record and touches no
        database, so a namespace is the honest stand-in — and using one keeps
        these cases pure while still driving the REAL attribution rule rather
        than a copy of it.
        """
        return [SimpleNamespace(**row) for row in rows]

    def read_over(self, rows, start, end):
        return sum(
            SuppliedRevenueService.attributed_micros(
                record, start, end, MARGIN_REVENUE_BASIS)
            for record in self.as_records(rows))

    @pytest.mark.parametrize("effective_from,effective_to,start,end", [
        # A whole month, read whole.
        (datetime.date(2026, 4, 1), datetime.date(2026, 5, 1),
         datetime.date(2026, 4, 1), datetime.date(2026, 5, 1)),
        # ⚠ MONTH-TO-DATE, which is what every margin surface defaults to: three
        # days into a month the tenant must see three days' revenue, not a
        # month's. This is the case a `recorded` reading fails.
        (datetime.date(2026, 4, 1), None,
         datetime.date(2026, 4, 1), datetime.date(2026, 4, 4)),
        # A window that starts mid-month and ends mid-another.
        (datetime.date(2026, 1, 1), None,
         datetime.date(2026, 2, 10), datetime.date(2026, 4, 20)),
        # A mid-period start read over a window that opens before it.
        (datetime.date(2026, 4, 14), datetime.date(2026, 5, 1),
         datetime.date(2026, 4, 1), datetime.date(2026, 5, 1)),
        # A mid-period start read over a window that opens INSIDE it.
        (datetime.date(2026, 4, 14), datetime.date(2026, 5, 1),
         datetime.date(2026, 4, 20), datetime.date(2026, 5, 1)),
        # A profile that opened and closed inside one month.
        (datetime.date(2026, 1, 20), datetime.date(2026, 4, 11),
         datetime.date(2026, 1, 1), datetime.date(2026, 5, 1)),
    ])
    def test_a_window_reads_what_the_accrual_used_to_return(
            self, effective_from, effective_to, start, end):
        horizon = datetime.date(2026, 6, 1)
        rows = MIGRATION.carried_rows(
            a_profile(effective_from, effective_to), horizon=horizon)
        assert self.read_over(rows, start, end) == self.the_accrual_as_it_stood(
            500_000_000, effective_from,
            effective_to if effective_to else horizon, start, end)

    def test_the_month_to_date_case_is_not_vacuous(self):
        """The guard on the case above: it has to be a window the two bases
        DISAGREE about, or the parametrised row proves nothing.

        Three days into April, `recognised` gives three days of the month's
        revenue and `recorded` gives the whole month. Asserting the gap here
        means that if anyone moves `MARGIN_REVENUE_BASIS` back to the default,
        the case above goes red for the right reason rather than by luck.
        """
        rows = MIGRATION.carried_rows(
            a_profile(datetime.date(2026, 4, 1), None),
            horizon=datetime.date(2026, 6, 1))
        window = (datetime.date(2026, 4, 1), datetime.date(2026, 4, 4))
        recognised = self.read_over(rows, *window)
        recorded = sum(
            SuppliedRevenueService.attributed_micros(
                record, *window, REVENUE_BASIS_RECORDED)
            for record in self.as_records(rows))
        assert recognised == 500_000_000 * 3 // 30
        assert recorded == 500_000_000
        assert MARGIN_REVENUE_BASIS == REVENUE_BASIS_RECOGNISED


class TestTheDataPassItself(TestCase):
    """The two functions the migration runs, against the state it meets.

    The registry is `0014`'s project state and the retired table is created
    from that state's own model, so what these cases plant is what `0015`
    reads — not a copy of it written here.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.old_apps = MigrationExecutor(connection).loader.project_state(
            THE_STATE_BEFORE).apps
        cls.Profile = cls.old_apps.get_model("subscriptions", "CustomerRevenueProfile")
        cls.Supplied = cls.old_apps.get_model("subscriptions", "TenantSuppliedRevenue")
        with connection.schema_editor() as editor:
            editor.create_model(cls.Profile)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(cls.Profile)
        super().tearDownClass()

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def plant(self, customer=None, **kwargs):
        return self.Profile.objects.create(
            tenant_id=self.tenant.id,
            customer_id=(customer or self.customer).id, **kwargs)

    def carry(self, horizon=datetime.date(2026, 7, 1)):
        MIGRATION.carry_the_amounts_onto_their_periods(
            self.old_apps, None, horizon=horizon)

    def test_a_profile_becomes_its_months(self):
        self.plant(recurring_amount_micros=500_000_000,
                   effective_from=datetime.date(2026, 4, 14),
                   effective_to=datetime.date(2026, 6, 1))
        self.carry()
        carried = list(self.Supplied.objects.order_by("period_start"))
        self.assertEqual(
            [(r.period_start, r.period_end) for r in carried],
            [(datetime.date(2026, 4, 14), datetime.date(2026, 5, 1)),
             (datetime.date(2026, 5, 1), datetime.date(2026, 6, 1))])
        self.assertEqual([r.source_reference for r in carried],
                         [MIGRATION.SOURCE_REFERENCE] * 2)

    def test_running_it_twice_states_the_same_figures_rather_than_doubling_them(self):
        # The record's uniqueness key is (customer, period open, source
        # reference), so a second pass re-states each row instead of adding a
        # second one — which is what makes a half-finished migration safe to
        # run again.
        self.plant(recurring_amount_micros=500_000_000,
                   effective_from=datetime.date(2026, 4, 1),
                   effective_to=datetime.date(2026, 6, 1))
        self.carry()
        self.carry()
        self.assertEqual(self.Supplied.objects.count(), 2)

    def test_a_second_customers_profile_lands_on_its_own_customer(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        self.plant(recurring_amount_micros=100_000_000,
                   effective_from=datetime.date(2026, 4, 1),
                   effective_to=datetime.date(2026, 5, 1))
        self.plant(customer=other, recurring_amount_micros=200_000_000,
                   effective_from=datetime.date(2026, 4, 1),
                   effective_to=datetime.date(2026, 5, 1))
        self.carry()
        self.assertEqual(
            {(r.customer_id, r.amount_micros) for r in self.Supplied.objects.all()},
            {(self.customer.id, 100_000_000), (other.id, 200_000_000)})

    def test_the_reverse_rebuilds_a_profile_from_the_rows_it_made(self):
        self.plant(recurring_amount_micros=500_000_000, currency="gbp",
                   effective_from=datetime.date(2026, 4, 1),
                   effective_to=datetime.date(2026, 6, 1))
        self.carry()
        self.Profile.objects.all().delete()

        MIGRATION.put_the_amounts_back(self.old_apps, None)

        rebuilt = self.Profile.objects.get()
        self.assertEqual(rebuilt.recurring_amount_micros, 500_000_000)
        self.assertEqual(rebuilt.currency, "gbp")
        self.assertEqual(rebuilt.effective_from, datetime.date(2026, 4, 1))
        self.assertEqual(rebuilt.effective_to, datetime.date(2026, 6, 1))
        # And it takes back only what it put there.
        self.assertFalse(self.Supplied.objects.filter(
            source_reference=MIGRATION.SOURCE_REFERENCE).exists())

    def test_the_reverse_leaves_a_figure_the_tenant_supplied_itself_alone(self):
        self.Supplied.objects.create(
            tenant_id=self.tenant.id, customer_id=self.customer.id,
            amount_micros=7_000_000, currency="usd",
            period_start=datetime.date(2026, 4, 1),
            period_end=datetime.date(2026, 5, 1),
            recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
            source_reference="INV-2026-04")

        MIGRATION.put_the_amounts_back(self.old_apps, None)

        self.assertTrue(self.Supplied.objects.filter(
            source_reference="INV-2026-04").exists())
        self.assertFalse(self.Profile.objects.exists())
