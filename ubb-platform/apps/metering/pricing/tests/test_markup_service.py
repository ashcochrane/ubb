"""The markup rung: which percentage applies, and where it came from.

**A RUNG ANSWERS A PERCENTAGE AND ITS SOURCE, NOT A FINISHED PRICE (#356).**
These tests used to call an applier that took a supplier cost and returned the
marked-up figure. It is gone: the resolver is what decides whether a basis may
be marked up at all, and a function that handed back a number threw the source
away at the one point it was still known. So each case here resolves the rung
and applies it, which is what the resolver does, one step apart.

**AND "NOTHING CONFIGURED" IS NO LONGER A PRICE.** An unresolved rung used to
mean *bill the customer exactly what the call cost*, which is a decision nobody
made wearing a settled figure's clothes. It now means there is no rung, and what
that produces is `unknown` — asserted at the resolver, in
`test_the_price_ladder_resolves_as_of_an_instant.py`, because it is a statement
about resolution rather than about this module.

⚠ **THE LADDER HAD THREE RUNGS AND HAS ONE (#369).** A customer's own override
row and their plan's percentage column were both read here; both records are
deleted, and what one named customer or one plan's customers are charged is
decided further up the ladder, by a rule in a Pricing Book. This module's
precedence cases went with them — there is nothing left to take precedence over
— and the two that mattered are INVERTED at their own addresses below rather
than deleted, because what they pinned has changed rather than stopped being
worth pinning:

  * a plan's zero used to SHADOW a non-zero tenant default and pin the customer
    at provider cost. It cannot now: the plan supplies no rung, so the tenant's
    default is what answers;
  * a customer on a plan could never reach "no rung at all", because the plan's
    column defaulted to zero and a default is not a declaration. They can now,
    and that is the whole point of deleting the column.
"""
import pytest
from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.metering.pricing.models import TenantDefaultMarkup
from apps.metering.pricing.services.markup_service import (
    MARKUP_RUNG_TENANT_DEFAULT, MarkupService, ResolvedMarkup,
)


def _billed(basis_micros, tenant):
    """What the markup rung answers over a basis, or `None` if there is no rung.

    The resolver's two steps in one place, so a case below reads as the question
    it is asking. `None` is not a price: it is the absence of a rung, and what
    resolution makes of that is the resolver's to say.
    """
    markup = MarkupService.resolve(tenant)
    return markup.applied_to(basis_micros) if markup is not None else None


@pytest.mark.django_db
class TestMarkupService:
    def test_no_markup_leaves_the_rung_unresolved(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        assert MarkupService.resolve(t) is None

    def test_tenant_default_markup_applied(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        TenantDefaultMarkup.objects.create(tenant=t, markup_micro_percent=20_000_000)  # 20%
        assert _billed(100_000, t) == 120_000

    def test_the_declared_rung_names_itself_and_the_record_it_came_from(self):
        """What the receipt's provenance is written out of (#357).

        A rung answers a percentage, which rung it is, and the record the
        percentage was read from — never a finished number. The last of those
        is what lets a tenant asked "why is this line £36?" be shown the row,
        and it cannot be recovered later because the row can be edited.
        """
        t = Tenant.objects.create(name="T", products=["metering"])
        rung = TenantDefaultMarkup.objects.create(
            tenant=t, markup_micro_percent=20_000_000)

        resolved = MarkupService.resolve(t)

        assert resolved.source == MARKUP_RUNG_TENANT_DEFAULT
        assert resolved.source_id == str(rung.id)
        assert resolved.markup_micro_percent == 20_000_000

    def test_a_tenants_rung_is_their_own(self):
        """The record is a one-to-one on the tenant, and resolve filters on it.

        Cheap, and it is the case a resolve that dropped its filter would pass
        every other test in this module with.
        """
        mine = Tenant.objects.create(name="Mine", products=["metering"])
        theirs = Tenant.objects.create(name="Theirs", products=["metering"])
        TenantDefaultMarkup.objects.create(tenant=theirs,
                                           markup_micro_percent=20_000_000)
        assert MarkupService.resolve(mine) is None


class TestTheArithmetic:
    """The margin itself — half-up on the micro, over a basis and nothing else.

    ⚠ **THIS MOVED OFF A MODEL AND ONTO THE RESOLVED VALUE (#369).** It used to
    be a method on the deleted markup record, tested against rows in the
    database; the same sum now belongs to :class:`ResolvedMarkup`, which is what
    every rung answers, so the cases need no database at all.

    ⚠ **AND THE SECOND TERM IS GONE.** A per-event flat addend used to be added
    after the percentage, because two of the three rungs carried one. Rules
    never compose (#147 §2), the rung that remains has no such column, and the
    receipt's own required terms shed it in the same commit.
    """

    def _rung(self, micro_percent):
        return ResolvedMarkup(markup_micro_percent=micro_percent,
                              source=MARKUP_RUNG_TENANT_DEFAULT, source_id="x")

    def test_a_percentage_is_taken_over_the_basis(self):
        # (1_000_000 * 50_000_000 + 50_000_000) // 100_000_000 == 500_000
        assert self._rung(50_000_000).calculate_markup_micros(1_000_000) == 500_000

    def test_a_zero_percentage_takes_nothing(self):
        """A declared zero is *charge exactly what the call cost*, and it is a
        decision — which is why the ABSENCE of a rung is `None` rather than
        this."""
        assert self._rung(0).calculate_markup_micros(1_000_000) == 0
        assert self._rung(0).applied_to(1_000_000) == 1_000_000

    def test_the_half_micro_rounds_up(self):
        """The `+ 50_000_000` in the numerator, asserted rather than assumed.

        1% of 50 micros is 0.5 of a micro. Half-up answers 1; truncation would
        answer 0, and changing which would silently re-price every event.
        """
        assert self._rung(1_000_000).calculate_markup_micros(50) == 1

    def test_applied_to_is_the_basis_plus_the_margin(self):
        assert self._rung(20_000_000).applied_to(100_000) == 120_000


@pytest.mark.django_db
class TestAPlanNoLongerSuppliesARung:
    """The two plan-rung cases, inverted at their own addresses (#369).

    Each pinned something true of the deleted column, and each now pins the
    opposite. Relaxing them — deleting the plan from the fixture, say — would
    leave the module unable to tell "the plan rung was removed" from "the plan
    rung was never reached in this test".
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T",
                                            products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")

    def _assign(self, key):
        plan = a_plan(tenant=self.tenant, key=key, name=key)
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        return plan

    def test_a_customer_on_a_plan_resolves_to_the_tenants_declared_rung(self):
        """Was: *a fee-only plan's zero shadows the tenant default and pins the
        customer at provider cost.*

        It did, because the column defaulted to zero and every plan therefore
        supplied a rung. The plan supplies none now, so the tenant's own
        declaration is what answers — and the customer is billed the default's
        20% rather than pinned at cost.
        """
        TenantDefaultMarkup.objects.create(tenant=self.tenant,
                                           markup_micro_percent=20_000_000)
        self._assign("fee-only")

        resolved = MarkupService.resolve(self.tenant)

        assert resolved.source == MARKUP_RUNG_TENANT_DEFAULT
        assert _billed(500_000, self.tenant) == 600_000

    def test_a_customer_on_a_plan_can_now_reach_no_rung_at_all(self):
        """Was: *a customer on a plan always has a rung.*

        They always did, and that was the defect: a column defaulting to zero
        made "the tenant has said nothing about what to charge" indistinguishable
        from "the tenant said charge cost", and the second settles a price. With
        the column gone the honest answer is reachable, and resolution turns it
        into `unknown` — no amount at all.
        """
        self._assign("personal-lite")

        assert MarkupService.resolve(self.tenant) is None


@pytest.mark.django_db
class TestAResolvedZeroIsStillABasis:
    """The control that stops "no basis" reaching a real number (#328, #356).

    Zero keeps a meaning of its own — resolved, and it was exactly nothing —
    which is the distinction the nullable cost column exists to hold. A rule
    written as a truthiness test would swallow it and refuse a cost UBB knows
    perfectly well.

    ⚠ **THE REFUSAL THAT USED TO LIVE HERE HAS MOVED AND CHANGED SHAPE.** The
    applier raised on a cost UBB had not resolved, because a markup is not a
    total: there is no "at least" to state about a single price, so the honest
    answers were a real basis or an error. The resolver now asks that question
    before a percentage is resolved at all and answers it in the vocabulary it
    belongs in — a margin over a cost UBB never learned is a `waived` charge —
    so what was an exception is a recorded status, asserted in
    `test_the_price_ladder_resolves_as_of_an_instant.py`.

    ⚠ **THE ASSERTION IS WEAKER THAN IT WAS, AND SAYING SO IS THE POINT.** It
    used to reach a NON-ZERO figure, because the rung it went through carried a
    flat addend that survived a zero basis. No rung carries one now (#369), so
    what separates a resolved zero from a missing basis here is `0` against
    `None` — a real distinction, and the only one the arithmetic can still make.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])

    def test_a_resolved_zero_is_a_basis_and_not_an_absent_rung(self):
        TenantDefaultMarkup.objects.create(tenant=self.tenant,
                                           markup_micro_percent=20_000_000)
        assert _billed(0, self.tenant) == 0

    def test_no_rung_over_the_same_basis_is_not_a_zero(self):
        assert _billed(0, self.tenant) is None
