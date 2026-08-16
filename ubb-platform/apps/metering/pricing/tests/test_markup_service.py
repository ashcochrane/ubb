import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import TenantMarkup
from apps.metering.pricing.services.markup_service import MarkupService


@pytest.mark.django_db
class TestMarkupService:
    def test_no_markup_returns_provider_cost(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 100_000

    def test_tenant_default_markup_applied(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=20_000_000)  # 20%
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 120_000

    def test_customer_override_beats_tenant_default(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=20_000_000)
        TenantMarkup.objects.create(tenant=t, customer=c, markup_percentage_micros=50_000_000)
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 150_000

    def test_fixed_uplift_added(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        TenantMarkup.objects.create(tenant=t, customer=None, markup_percentage_micros=0, fixed_uplift_micros=500)
        assert MarkupService.apply(100_000, tenant=t, customer=c) == 100_500


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
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    markup_percentage_micros=20_000_000)
        self._assign("personal-lite", 50_000_000)
        # $0.50 provider cost -> 50% -> $0.75, NOT the default's $0.60.
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 750_000

    def test_customer_override_beats_plan(self):
        self._assign("personal-lite", 50_000_000)
        TenantMarkup.objects.create(tenant=self.tenant, customer=self.customer,
                                    markup_percentage_micros=10_000_000)
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 550_000

    def test_unassigned_customer_falls_through_to_tenant_default(self):
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    markup_percentage_micros=20_000_000)
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 600_000

    def test_no_markup_anywhere_bills_at_provider_cost(self):
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 500_000

    def test_resolve_reports_its_source(self):
        self._assign("personal-lite", 50_000_000)
        assert MarkupService.resolve(self.tenant, self.customer).source == "plan"

    def test_plan_fixed_uplift_is_applied(self):
        plan = Plan.objects.create(tenant=self.tenant, key="p", name="P",
                                   markup_percentage_micros=20_000_000,
                                   fixed_uplift_micros=7_000)
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 607_000

    def test_enterprise_and_personal_both_rate_at_twenty_percent(self):
        self._assign("enterprise", 20_000_000)
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 600_000

    def test_zero_markup_plan_shadows_tenant_default_and_pins_provider_cost(self):
        """A fee-only plan (markup left blank -> 0%) is a deliberate zero, same
        as a zero customer override: it pins the customer at provider cost and
        must NOT fall through to a non-zero tenant default."""
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    markup_percentage_micros=20_000_000)
        self._assign("fee-only", 0)
        resolved = MarkupService.resolve(self.tenant, self.customer)
        assert resolved.source == "plan"
        assert MarkupService.apply(500_000, self.tenant, self.customer) == 500_000


@pytest.mark.django_db
class TestAnUnresolvedCostHasNoMarkup:
    """The one site in slice 3's sweep that refuses instead of reporting a floor
    (#328).

    Every other reader of a supplier cost answers what it can and states what it
    left out. A markup cannot: it is not a total, so there is no "at least" to
    say about it, and marking up zero would put a price nobody stated on an
    invoice. So the answers are a real basis or a refusal.

    Both appliers are asserted, and separately. `MarkupCache.apply`'s whole
    contract is that it answers what `MarkupService.apply` answers, and a shared
    guard proved through only one of them is a guard that can quietly stop being
    shared.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")

    def test_the_service_refuses_a_cost_ubb_has_not_resolved(self):
        # The MESSAGE, not just the type: `TypeError`-shaped failures from the
        # arithmetic two lines down would satisfy a bare `raises(ValueError)`
        # against a version with no guard at all.
        with pytest.raises(ValueError, match="provider_cost_micros is unresolved"):
            MarkupService.apply(None, self.tenant, self.customer)

    def test_the_cache_refuses_it_on_the_same_terms(self):
        from apps.metering.pricing.services.markup_cache import MarkupCache

        with pytest.raises(ValueError, match="provider_cost_micros is unresolved"):
            MarkupCache.apply(None, tenant=self.tenant, customer=self.customer)

    def test_a_resolved_zero_is_still_a_basis_and_is_marked_up(self):
        """The control that stops the guard reaching a real number.

        Zero keeps a meaning of its own — resolved, and it was exactly nothing
        — which is the distinction the nullable column exists to hold. A guard
        written as a truthiness test would swallow it and refuse a cost UBB
        knows perfectly well.
        """
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    markup_percentage_micros=20_000_000,
                                    fixed_uplift_micros=1_000)
        assert MarkupService.apply(0, self.tenant, self.customer) == 1_000
