import pytest

from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.plans.services import PlanInUse, PlanService
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestPlanService:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_assign_creates_the_row(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        PlanService.assign(self.tenant, self.customer, plan)
        assert CustomerPlanAssignment.objects.filter(
            tenant=self.tenant, customer=self.customer, plan=plan).exists()

    def test_reassign_moves_the_customer_rather_than_duplicating(self):
        a = Plan.objects.create(tenant=self.tenant, key="a", name="A")
        b = Plan.objects.create(tenant=self.tenant, key="b", name="B")
        PlanService.assign(self.tenant, self.customer, a)
        PlanService.assign(self.tenant, self.customer, b)
        rows = CustomerPlanAssignment.objects.filter(customer=self.customer)
        assert rows.count() == 1
        assert rows.first().plan_id == b.id

    def test_archive_marks_the_plan(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        PlanService.archive(plan)
        plan.refresh_from_db()
        assert plan.archived_at is not None

    def test_archive_refuses_an_assigned_plan(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        PlanService.assign(self.tenant, self.customer, plan)
        with pytest.raises(PlanInUse):
            PlanService.archive(plan)
