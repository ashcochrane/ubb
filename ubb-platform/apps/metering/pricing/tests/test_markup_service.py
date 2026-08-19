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
"""
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import TenantDefaultMarkup, TenantMarkup
from apps.metering.pricing.services.markup_service import MarkupService


def _billed(basis_micros, tenant, customer):
    """What the markup rung answers over a basis, or `None` if there is no rung.

    The resolver's two steps in one place, so a case below reads as the question
    it is asking. `None` is not a price: it is the absence of a rung, and what
    resolution makes of that is the resolver's to say.
    """
    markup = MarkupService.resolve(tenant, customer)
    return markup.applied_to(basis_micros) if markup is not None else None


@pytest.mark.django_db
class TestMarkupService:
    def test_no_markup_leaves_the_rung_unresolved(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert MarkupService.resolve(t, c) is None

    def test_tenant_default_markup_applied(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantDefaultMarkup.objects.create(tenant=t, markup_micro_percent=20_000_000)  # 20%
        assert _billed(100_000, t, c) == 120_000

    def test_customer_override_beats_tenant_default(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantDefaultMarkup.objects.create(tenant=t, markup_micro_percent=20_000_000)
        TenantMarkup.objects.create(tenant=t, customer=c, markup_percentage_micros=50_000_000)
        assert _billed(100_000, t, c) == 150_000
        assert MarkupService.resolve(t, c).source == "customer"

    def test_a_customer_overrides_fixed_uplift_is_added(self):
        """⚠ THE UPLIFT IS A TERM OF THE TWO RUNGS BEING DELETED (#357).

        A rule that takes a margin over cost does not also carry a flat addend
        (#147 §2), so the tenant-default rung a tenant declares now has no
        uplift column at all. The customer override and the plan's own column
        still do until the commit that deletes both records, so the term is
        exercised where it is actually reachable rather than through a rung
        that cannot express it.
        """
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=c, markup_percentage_micros=0, fixed_uplift_micros=500)
        assert _billed(100_000, t, c) == 100_500

    def test_the_declared_rung_names_itself_and_the_record_it_came_from(self):
        """What the receipt's provenance is written out of (#357).

        A rung answers a percentage, which rung it is, and the record the
        percentage was read from — never a finished number. The last of those
        is what lets a tenant asked "why is this line £36?" be shown the row,
        and it cannot be recovered later because the row can be edited.
        """
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        rung = TenantDefaultMarkup.objects.create(
            tenant=t, markup_micro_percent=20_000_000)

        resolved = MarkupService.resolve(t, c)

        assert resolved.source == "tenant_default"
        assert resolved.source_id == str(rung.id)
        assert resolved.markup_micro_percent == 20_000_000
        assert resolved.fixed_uplift_micros == 0


from apps.platform.plans.models import CustomerPlanAssignment, Plan


@pytest.mark.django_db
class TestMarkupPrecedenceWithPlans:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _assign(self, key, pct):
        plan = Plan.objects.create(tenant=self.tenant, key=key, name=key,
                                   markup_percentage_micros=pct)
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        return plan

    def test_plan_markup_beats_tenant_default(self):
        """THE REVENUE LEAK, PINNED. A Personal Lite customer (50%) must not
        fall through to the tenant default (20%). If this test ever passes
        with 600_000, the plan rung has been lost."""
        TenantDefaultMarkup.objects.create(tenant=self.tenant,
                                           markup_micro_percent=20_000_000)
        self._assign("personal-lite", 50_000_000)
        # $0.50 provider cost -> 50% -> $0.75, NOT the default's $0.60.
        assert _billed(500_000, self.tenant, self.customer) == 750_000

    def test_customer_override_beats_plan(self):
        self._assign("personal-lite", 50_000_000)
        TenantMarkup.objects.create(tenant=self.tenant, customer=self.customer,
                                    markup_percentage_micros=10_000_000)
        assert _billed(500_000, self.tenant, self.customer) == 550_000

    def test_unassigned_customer_falls_through_to_tenant_default(self):
        TenantDefaultMarkup.objects.create(tenant=self.tenant,
                                           markup_micro_percent=20_000_000)
        assert _billed(500_000, self.tenant, self.customer) == 600_000

    def test_no_markup_anywhere_leaves_the_rung_unresolved(self):
        """What used to be "bills at provider cost" (#356).

        The old answer charged a customer exactly what the call cost and called
        it settled, which is a price nobody stated. There is no rung here, and
        the resolver's own module is where what that produces is asserted.
        """
        assert MarkupService.resolve(self.tenant, self.customer) is None

    def test_resolve_reports_its_source(self):
        self._assign("personal-lite", 50_000_000)
        assert MarkupService.resolve(self.tenant, self.customer).source == "plan"

    def test_plan_fixed_uplift_is_applied(self):
        plan = Plan.objects.create(tenant=self.tenant, key="p", name="P",
                                   markup_percentage_micros=20_000_000,
                                   fixed_uplift_micros=7_000)
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        assert _billed(500_000, self.tenant, self.customer) == 607_000

    def test_enterprise_and_personal_both_rate_at_twenty_percent(self):
        self._assign("enterprise", 20_000_000)
        assert _billed(500_000, self.tenant, self.customer) == 600_000

    def test_zero_markup_plan_shadows_tenant_default_and_pins_provider_cost(self):
        """A fee-only plan (markup left blank -> 0%) is a deliberate zero, same
        as a zero customer override: it pins the customer at provider cost and
        must NOT fall through to a non-zero tenant default.

        The distinction the rung has to keep is between a rung that resolved to
        zero and no rung at all — one is the tenant saying "charge cost", the
        other is nobody having said anything.
        """
        TenantDefaultMarkup.objects.create(tenant=self.tenant,
                                           markup_micro_percent=20_000_000)
        self._assign("fee-only", 0)
        resolved = MarkupService.resolve(self.tenant, self.customer)
        assert resolved.source == "plan"
        assert _billed(500_000, self.tenant, self.customer) == 500_000


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
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")

    def test_a_resolved_zero_is_marked_up_to_the_uplift(self):
        # Through the customer override, which is the rung that still carries
        # an uplift: the tenant-default rung has no such column, because a
        # margin over cost never composes with a flat addend (#147 §2).
        TenantMarkup.objects.create(tenant=self.tenant, customer=self.customer,
                                    markup_percentage_micros=20_000_000,
                                    fixed_uplift_micros=1_000)
        assert _billed(0, self.tenant, self.customer) == 1_000
