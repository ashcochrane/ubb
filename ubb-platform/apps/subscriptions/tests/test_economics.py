import datetime
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.models import (
    CustomerCostAccumulator, TenantSuppliedRevenue)
from apps.subscriptions.economics.revenue import SuppliedRevenueService
from apps.subscriptions.economics.services import (
    MARGIN_REVENUE_BASIS, MarginService)
from core.vocabulary import RECOGNITION_METHOD_STRAIGHT_LINE


class MarginServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.ps = datetime.date(2026, 6, 1)
        self.pe = datetime.date(2026, 7, 1)

    def test_billed_usage_is_revenue_and_the_margin_is_what_is_left_of_it(self):
        """⚠ **THIS CASE ASSERTED THE OPPOSITE UNTIL #497, AND ITS NAME SAID
        SO.** It was `test_meter_only_margin_is_billed_minus_provider`, and the
        margin it asserted was the NEGATIVE of the cost: this tenant's billing
        mode resolved its customer away from billed usage, so a million micros
        of resolved customer price was struck out of the revenue on the way
        through and the snapshot reported a loss of the whole supplier cost.

        The number moves because the old one was wrong, not because the
        arithmetic changed. UBB resolved that price, for this tenant, and a
        tenant that meters here and invoices elsewhere is exactly who those
        prices are resolved for. Who sends the invoice decides who sends the
        invoice (slice 7 §9).
        """
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=800_000, total_billed_cost_micros=1_000_000, event_count=2)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        assert econ.subscription_revenue_micros == 0
        assert econ.usage_billed_micros == 1_000_000
        assert econ.provider_cost_micros == 800_000
        assert econ.gross_margin_micros == 200_000
        assert float(econ.margin_percentage) == 20.0

    def test_the_subscription_accrual_takes_the_nominal_not_the_paid_invoice(self):
        """A subscription accrues what it is worth over the window, which is
        not what Stripe has collected against it.

        Rehomed here from `test_margin_modes.py` when #497 deleted that module
        with the switch it was named for. It is about the Stripe half and was
        never about the switch — and the module it sat in existed only to prove
        the two revenue "modes" behaved differently, which is now not a fact.
        """
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
        from apps.subscriptions.tests._helpers import a_tenant_ubb_invoices
        from django.utils import timezone
        tenant, customer = a_tenant_ubb_invoices()
        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer, stripe_subscription_id="s1",
            stripe_product_name="Pro", status="active", amount_micros=20_000_000,
            quantity=1, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now)
        # Stripe collected MORE than the subscription is nominally worth; the
        # accrual must still report the nominal, or a customer who overpaid one
        # month shows a margin they did not earn.
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id="in_1", amount_paid_micros=25_000_000,
            currency="usd", period_start=now, period_end=now, paid_at=now)
        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=3_000_000, total_billed_cost_micros=5_000_000,
            event_count=1)

        econ = MarginService.snapshot_customer(tenant.id, customer.id, self.ps, self.pe)

        assert econ.subscription_revenue_micros == 20_000_000
        assert econ.total_revenue_micros == 25_000_000  # nominal 20M + billed usage 5M
        assert econ.gross_margin_micros == 22_000_000

    def supply(self, amount=500_000_000, source_reference="INV-2026-06"):
        """What the tenant says it earned from this customer over the period.

        The posture the retired recurring profile was carrying badly (#496):
        a tenant that meters with UBB and bills its customers somewhere else.
        """
        return TenantSuppliedRevenue.objects.create(
            tenant=self.tenant, customer=self.customer, amount_micros=amount,
            currency="usd", period_start=self.ps, period_end=self.pe,
            recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
            source_reference=source_reference)

    def test_margin_includes_supplied_revenue_under_its_own_name(self):
        # Three sources, each in its own column: nothing from Stripe, the
        # figure the tenant supplied, and the usage UBB priced — which counts
        # for this tenant as for any other since #497.
        self.supply()
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=800_000, total_billed_cost_micros=1_000_000, event_count=2)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        assert econ.supplied_revenue_micros == 500_000_000
        # The snapshot keeps no usage-revenue column of its own — the billed
        # total IS that figure since #497 — so the third source shows up in
        # the total, which is the only place it could.
        assert econ.usage_billed_micros == 1_000_000
        assert econ.total_revenue_micros == 501_000_000
        assert econ.gross_margin_micros == 500_200_000

    def test_a_supplied_figure_never_lands_in_the_stripe_column(self):
        # ⚠ THE DEFECT #496 EXISTS TO END. The retired profile's amount was
        # added into `subscription_revenue_micros`, so a reader of that number
        # could not say whether it came from a subscription UBB drives through
        # Stripe or from a figure a tenant typed about a system UBB has never
        # seen. Two sources, two columns — and this is the assertion that
        # fails if anyone ever adds them back together.
        self.supply()
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        assert econ.subscription_revenue_micros == 0
        assert econ.supplied_revenue_micros == 500_000_000
        assert econ.total_revenue_micros == 500_000_000

    def test_two_sources_covering_one_period_are_two_facts(self):
        # Two invoices covering one month are two figures, which is what the
        # record's uniqueness key means — and both belong in the margin.
        self.supply(amount=200_000_000, source_reference="INV-A")
        self.supply(amount=300_000_000, source_reference="INV-B")
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        assert econ.supplied_revenue_micros == 500_000_000

    def test_a_cost_tracking_only_tenant_is_left_with_no_revenue_of_its_own(self):
        """⚠ THE OTHER POSTURE, which #153 §3.2 rules must survive alongside
        the one above, and which no gate would catch the loss of.

        ⚠ **THE CASE HAD TO CHANGE ITS INPUT IN #497, AND THAT IS THE LESSON
        RATHER THAN A REPAIR.** It used to give this customer a billed usage
        total of a million micros and then assert the total revenue was zero —
        which was true only because the tenant's billing mode struck the figure
        out. That is precisely the "cost tracking only" that was not: UBB had
        priced the work and then declined to call the price revenue. A tenant
        genuinely tracking cost only is one that has declared no prices, so the
        input here is now usage UBB **could not** price, and the zero is the
        empty sum rather than a suppressed one.

        ⚠ **WHAT THIS CASE DOES NOT ASSERT, AND WHY.** §9 says revenue
        `unknown` means margin **unavailable, never zero** — and this record
        cannot say "unavailable". `gross_margin_micros` is a NOT NULL column
        that always computes, so asserting a value for it here would be
        blessing a number the spec says should not be presented as a margin at
        all. That half had no surface to be asserted against until the
        route-collapsing tickets built slice 7 §5's scope rule and #502 demoted
        this record to the alerting state machine it is. The one economic query
        now answers it in its own states — a floor labelled `incomplete`, never
        a `known` figure — asserted through its route
        (`api/v1/tests/test_the_one_economic_query.py::
        TestUsageNobodyPricedIsNeverAKnownFigure`).

        What IS asserted is the half this ticket owns: no revenue figure was
        invented, the cost side still flows, the total travels with the count
        saying it is a floor, and **the surface that answers the revenue
        question answers `unknown`** rather than nil. The margin value is read
        only to show the cost reached it — it is named `cost_only` rather than
        `margin` so nobody quotes it as one.
        """
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=800_000, total_billed_cost_micros=0,
            unpriced_event_count=2, event_count=2)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)

        assert not TenantSuppliedRevenue.objects.exists()
        assert econ.supplied_revenue_micros == 0
        assert econ.total_revenue_micros == 0
        # And the zero says so: two events UBB could not price, carried onto
        # the snapshot, which is what makes the total above a floor rather than
        # a figure. A zero with no count beside it would be the silent zero.
        assert econ.unpriced_event_count == 2
        cost_only = econ.gross_margin_micros
        assert cost_only == -econ.provider_cost_micros == -800_000

        # The question "is this customer's revenue known?" is the supplied
        # read's, not this record's, and it answers `unknown` with an empty
        # list rather than a zero.
        assert SuppliedRevenueService.in_window(
            self.tenant.id, self.customer.id, self.ps, self.pe,
            MARGIN_REVENUE_BASIS) == []

    def test_month_to_date_gets_the_month_to_date_share_not_the_whole_month(self):
        """⚠ THE BASIS THE MARGIN SURFACES SERVE, pinned where it is decided.

        Every margin surface defaults to a month-to-DATE window, and a supplied
        figure read on the `recorded` basis lands whole on the day its record
        opens. Three days into the period that would put a whole month's
        revenue against three days of cost and call the result a margin. The
        retired recurring accrual prorated by day, so serving `recorded` here
        would ALSO have silently changed a published number on the commit that
        retired it.

        `MARGIN_REVENUE_BASIS` is `recognised` for both reasons, and the
        numbers below are what makes that a fact rather than a comment.
        """
        self.supply()  # 500_000_000 over the whole of June
        three_days_in = datetime.date(2026, 6, 4)
        econ = MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, self.ps, three_days_in)
        assert econ.supplied_revenue_micros == 500_000_000 * 3 // 30

    def test_a_period_the_tenant_said_nothing_about_gets_nothing(self):
        # A per-period record says something about ITS period and nothing about
        # any other — which is the fact the retired model could not express,
        # since one recurring amount applied to every period there would ever
        # be. The snapshot for May must not pick up June's figure.
        self.supply()
        may = MarginService.snapshot_customer(
            self.tenant.id, self.customer.id,
            datetime.date(2026, 5, 1), datetime.date(2026, 6, 1))
        assert may.supplied_revenue_micros == 0

    def test_compute_live_matches(self):
        from apps.metering.pricing.tests._helpers import (
            a_rule_that_prices_what_it_measures, priced_at)
        from apps.metering.usage.services.usage_service import UsageService
        from unittest.mock import patch
        # The billed figure is CONFIGURED now, not stated on the call (#365).
        a_rule_that_prices_what_it_measures(self.tenant)
        with patch("apps.platform.events.tasks.process_single_event"):
            UsageService.record_usage(
                tenant=self.tenant, customer=self.customer,
                idempotency_key="i1", provider_cost_micros=800_000,
                measurements=priced_at(1_000_000))
        # live window covering today; just assert the shape + margin math
        data = MarginService.compute_live(
            self.tenant.id, self.customer.id, datetime.date(2026, 1, 1), datetime.date(2100, 1, 1))
        assert data["provider_cost_micros"] == 800_000
        assert data["usage_billed_micros"] == 1_000_000
        # The priced usage is the revenue (#497): no subscription, nothing
        # supplied, so the margin is the price less the supplier cost.
        assert data["usage_revenue_micros"] == 1_000_000
        assert data["gross_margin_micros"] == 200_000
