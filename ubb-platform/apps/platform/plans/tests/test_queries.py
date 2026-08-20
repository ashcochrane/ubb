import pytest

from apps.platform.customers.models import Customer
from apps.platform.plans import queries
from apps.platform.plans.models import CustomerPlanAssignment
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestPlanQueries:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_markup_for_unassigned_customer_is_none(self):
        assert queries.get_plan_markup_for_customer(
            self.tenant.id, self.customer.id) is None

    def test_markup_for_assigned_customer_is_plain_data(self):
        plan = a_plan(tenant=self.tenant, key="lite", name="Lite",
                      markup_percentage_micros=50_000_000,
                      fixed_uplift_micros=1_000)
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        # The plan's ID rides with the terms (#357): a price resolved from this
        # rung is recorded on a receipt that names the record the percentage
        # came from, and a plan's markup can be edited. A cross-reference, not
        # a term — the percentage itself is written into the receipt by value.
        assert queries.get_plan_markup_for_customer(self.tenant.id, self.customer.id) == {
            "plan_id": str(plan.id),
            "markup_percentage_micros": 50_000_000,
            "fixed_uplift_micros": 1_000,
        }

    def test_archived_plan_yields_no_markup(self):
        from django.utils import timezone
        plan = a_plan(tenant=self.tenant, key="old", name="Old",
                      markup_percentage_micros=50_000_000,
                      archived_at=timezone.now())
        CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=self.customer, plan=plan)
        assert queries.get_plan_markup_for_customer(
            self.tenant.id, self.customer.id) is None

    def test_list_plans_excludes_archived_by_default(self):
        from django.utils import timezone
        a_plan(tenant=self.tenant, key="live", name="Live")
        a_plan(tenant=self.tenant, key="gone", name="Gone",
               archived_at=timezone.now())
        assert [p.key for p in queries.list_plans(self.tenant.id)] == ["live"]
        assert len(queries.list_plans(self.tenant.id, include_archived=True)) == 2

    def test_get_plan_by_key(self):
        a_plan(tenant=self.tenant, key="pro", name="Pro")
        assert queries.get_plan_by_key(self.tenant.id, "pro").name == "Pro"
        assert queries.get_plan_by_key(self.tenant.id, "nope") is None
