"""Who invoices a customer decides who invoices that customer, and nothing more.

⚠ **THE INVERSION THIS MODULE REFUSES** (#497, slice 7 §9). Until this ticket a
single writable column on the customer, resolving from the tenant's billing
mode wherever it was blank, decided whether that customer's usage counted as
revenue at all. It converted *"UBB does not raise this customer's invoices"*
into *"this customer produced no revenue"* — the exact inversion #141 §1.1's
governing invariant forbids, and a coarse customer-level answer to a question
#147 §7 already answers **precisely, per posting**.

**The per-posting answer is the one that was always right.** A posting carries
`pricing_status` and a nullable price: `known` is a resolved amount (including
a deliberate zero), `waived` is a charge nobody will pursue, `unknown` is an
amount UBB was never told — and `not_applicable` is a posting that was never
going to carry customer revenue, with `not_applicable_reason` saying which of
the two causes applies (`apps/metering/pricing/applicability.py`). Four facts,
one per posting, each written by the thing that knows it. Nothing above that
layer has to guess from a billing mode, and the layer that did guess got it
wrong for every tenant that prices its usage and sends the invoice itself.

**So a tenant that meters with UBB and bills its customers elsewhere is not a
tenant without revenue.** Its pricing rules exist precisely to say what its
customers are charged — the price resolver runs for it exactly as for anybody,
*"because the tenant's own margin reporting is what those prices are resolved
for"* (`applicability.py`'s own words). Where it has declared no prices, its
postings resolve `unknown` and the revenue really is unknown, with
`unpriced_event_count` beside the total saying so. That is an honest answer
arrived at from the postings; the switch produced a zero instead, arrived at
from the tenant's billing mode, and the two are not the same number.

**What is NOT re-opened here.** `applicability.py` rules that widening
`not_applicable` to *every* posting of a tenant that bills elsewhere is a
different question about a different subject; its regime, not its posture,
decides the status. This module holds the composition to the postings it is
given and does not touch what wrote them.
"""
import datetime

from django.test import TestCase

from apps.metering.usage.models import Posting
from apps.subscriptions.economics.models import TenantSuppliedRevenue
from apps.subscriptions.economics.revenue import SuppliedRevenueService
from apps.subscriptions.economics.services import (
    MARGIN_REVENUE_BASIS, MarginService)
from apps.subscriptions.tests._helpers import (
    MONTH_CLOSES, MONTH_OPENS, a_supplied_figure,
    a_tenant_billing_its_customers_elsewhere, a_tenant_ubb_invoices)
from core.vocabulary import PRICING_STATUS_UNKNOWN

#: The whole of April, half-open — the fixture's own month, BOUND rather
#: than restated, so a supplied figure written by its builder lands inside
#: the window read here and neither side can drift from the other.
OPENS, CLOSES = MONTH_OPENS, MONTH_CLOSES
#: Inside the window, stated rather than defaulted: `effective_at` defaults to
#: "now", which stops being inside a fixed month the moment the calendar moves.
MID = datetime.datetime(2026, 4, 15, tzinfo=datetime.timezone.utc)


def a_priced_event(tenant, customer, *, provider, billed, key="e1"):
    """One posting UBB costed and priced — the ordinary case, for both postures."""
    return Posting.objects.create(
        tenant=tenant, customer=customer, idempotency_key=key,
        provider_cost_micros=provider, billed_cost_micros=billed,
        effective_at=MID)


def an_event_ubb_could_not_price(tenant, customer, *, provider, key="e1"):
    """One posting UBB costed and could NOT price.

    `billed_cost_micros` is null and the status says why, which is what makes
    the resulting total a floor rather than a figure: a tenant that has
    declared no price for this work has revenue UBB does not know, and the
    count beside the total is how the surface says so.
    """
    return Posting.objects.create(
        tenant=tenant, customer=customer, idempotency_key=key,
        provider_cost_micros=provider, billed_cost_micros=None,
        pricing_status=PRICING_STATUS_UNKNOWN, effective_at=MID)


class WhoInvoicesDecidesOnlyWhoInvoicesTest(TestCase):
    """The headline: two postures, one set of facts, one answer."""

    def test_the_same_postings_earn_the_same_margin_whoever_sends_the_invoice(self):
        """⚠ **THE ASSERTION THE DELETED SWITCH WOULD FAIL.**

        Both tenants are given the *same* two numbers — a supplier cost and a
        resolved customer price — and nothing else differs but who raises the
        invoice. Before #497 the second tenant's price was struck out of its
        revenue on the way through and its margin came back as the negative of
        its cost; after it, the two answers are one answer.

        **Both sides construct something**, which is the half a one-sided
        comparison quietly drops: each posture gets its own tenant, its own
        customer and its own posting, and the equality below is between two
        computed dicts rather than between a computed one and a literal.
        """
        invoiced_tenant, invoiced_customer = a_tenant_ubb_invoices()
        elsewhere_tenant, elsewhere_customer = (
            a_tenant_billing_its_customers_elsewhere())
        for tenant, customer in ((invoiced_tenant, invoiced_customer),
                                 (elsewhere_tenant, elsewhere_customer)):
            a_priced_event(tenant, customer, provider=800_000, billed=1_000_000)

        invoiced = MarginService.compute_live(
            invoiced_tenant.id, invoiced_customer.id, OPENS, CLOSES)
        elsewhere = MarginService.compute_live(
            elsewhere_tenant.id, elsewhere_customer.id, OPENS, CLOSES)

        shared = ["provider_cost_micros", "usage_billed_micros",
                  "usage_revenue_micros", "total_revenue_micros",
                  "gross_margin_micros", "margin_percentage"]
        assert {key: invoiced[key] for key in shared} == {
            key: elsewhere[key] for key in shared}
        # And the shared answer is the one the postings state, not nil: the
        # price UBB resolved is revenue, and the margin is what is left of it.
        assert elsewhere["usage_revenue_micros"] == 1_000_000
        assert elsewhere["gross_margin_micros"] == 200_000

    def test_a_tenant_billing_elsewhere_gets_margin_at_the_scope_it_supplied(self):
        """The second of §9's two surviving workflows: cost tracking PLUS a
        figure the tenant states for a system UBB has never seen.

        The supplied figure reaches the margin under its own name, and it is
        the WHOLE revenue for the customer and the month it covers (#537): the
        usage UBB priced inside that month is still reported as billed, and is
        superseded rather than added. Until #537 this total was 4,000,000 —
        the supplied month plus the usage inside it, counted twice.
        """
        tenant, customer = a_tenant_billing_its_customers_elsewhere()
        a_priced_event(tenant, customer, provider=800_000, billed=1_000_000)
        TenantSuppliedRevenue.objects.create(
            tenant=tenant, customer=customer, **a_supplied_figure())

        margin = MarginService.compute_live(tenant.id, customer.id, OPENS, CLOSES)

        assert margin["subscription_revenue_micros"] == 0
        assert margin["supplied_revenue_micros"] == 3_000_000
        assert margin["usage_billed_micros"] == 1_000_000
        assert margin["usage_revenue_micros"] == 0
        assert margin["total_revenue_micros"] == 3_000_000
        assert margin["gross_margin_micros"] == 3_000_000 - 800_000

    def test_where_nothing_was_supplied_and_nothing_priced_revenue_is_unknown(self):
        """The first of §9's two workflows: cost tracking only.

        ⚠ **WHAT THIS ASSERTS AND WHAT IT CANNOT.** §9 says revenue `unknown`
        means margin **unavailable, never zero**, and the live composition has
        no way to say "unavailable" — `gross_margin_micros` is an integer that
        always computes. ⚠ **AND WHAT IT COMPUTES HERE IS NOT EVEN THE ZERO §9
        FORBIDS: it is MINUS THE SUPPLIER COST**, a figure that reads as a loss
        UBB has no revenue to measure against. That is the sharper form of the
        same defect, and stating it is the honest thing this case can do — the
        fix is a surface that publishes no margin at this scope, which §5's
        scope rule builds and the route-collapsing tickets own (§21 puts them
        in phase B). What is asserted here is the half this ticket owns:
        **nothing was invented.** No revenue
        figure was conjured from the tenant's billing mode, the usage total is
        a zero that travels with the count saying it is a floor rather than a
        figure, and the surface that answers *is this customer's revenue
        known?* answers with an empty list rather than with a number.
        """
        tenant, customer = a_tenant_billing_its_customers_elsewhere()
        an_event_ubb_could_not_price(tenant, customer, provider=800_000)

        margin = MarginService.compute_live(tenant.id, customer.id, OPENS, CLOSES)

        assert margin["usage_billed_micros"] == 0
        assert margin["unpriced_event_count"] == 1
        assert margin["supplied_revenue_micros"] == 0
        assert not TenantSuppliedRevenue.objects.exists()
        assert SuppliedRevenueService.in_window(
            tenant.id, customer.id, OPENS, CLOSES, MARGIN_REVENUE_BASIS) == []
        # The cost still reached the composition, which is the whole point of
        # metering for a tenant that bills elsewhere. Read under a name nobody
        # can quote as a margin, because §9 says this is not one.
        assert margin["provider_cost_micros"] == 800_000
