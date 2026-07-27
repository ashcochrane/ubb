import pytest
from django.db import IntegrityError

from apps.platform.customers.models import Customer
from apps.platform.plans.models import Plan, CustomerPlanAssignment
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestPlan:
    def _t(self):
        return Tenant.objects.create(name="T", products=["metering", "billing"])

    def test_key_unique_per_tenant(self):
        t = self._t()
        Plan.objects.create(tenant=t, key="pro", name="Pro")
        with pytest.raises(IntegrityError):
            Plan.objects.create(tenant=t, key="pro", name="Pro Again")

    def test_same_key_allowed_across_tenants(self):
        a, b = self._t(), self._t()
        Plan.objects.create(tenant=a, key="pro", name="Pro")
        Plan.objects.create(tenant=b, key="pro", name="Pro")
        assert Plan.objects.count() == 2

    def test_defaults_are_a_zero_fee_zero_markup_plan(self):
        t = self._t()
        p = Plan.objects.create(tenant=t, key="lite", name="Lite")
        assert p.access_fee_micros == 0
        assert p.per_seat_micros == 0
        assert p.markup_percentage_micros == 0
        assert p.fixed_uplift_micros == 0
        assert p.interval == "month"
        assert p.archived_at is None

    def test_personal_lite_shape_is_representable(self):
        # $0 access, $0 seat, 50% markup — the plan with no Stripe presence.
        t = self._t()
        p = Plan.objects.create(tenant=t, key="personal-lite", name="Personal Lite",
                                markup_percentage_micros=50_000_000)
        assert p.has_stripe_axes is False

    def test_enterprise_shape_has_stripe_axes(self):
        t = self._t()
        p = Plan.objects.create(tenant=t, key="enterprise", name="Enterprise",
                                access_fee_micros=100_000_000,
                                per_seat_micros=10_000_000,
                                markup_percentage_micros=20_000_000)
        assert p.has_stripe_axes is True


@pytest.mark.django_db
class TestCustomerPlanAssignment:
    def _t(self):
        return Tenant.objects.create(name="T", products=["metering", "billing"])

    def test_one_assignment_per_customer(self):
        t = self._t()
        c = Customer.objects.create(tenant=t, external_id="c1")
        a = Plan.objects.create(tenant=t, key="a", name="A")
        b = Plan.objects.create(tenant=t, key="b", name="B")
        CustomerPlanAssignment.objects.create(tenant=t, customer=c, plan=a)
        with pytest.raises(IntegrityError):
            CustomerPlanAssignment.objects.create(tenant=t, customer=c, plan=b)
