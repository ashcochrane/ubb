from unittest.mock import patch

import pytest

from apps.platform.customers.models import Customer
from apps.platform.plans.models import CustomerPlanAssignment, Plan
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestMarkupCacheInvalidation:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])

    def test_saving_a_plan_invalidates_the_tenant_markup_cache(self):
        target = "apps.metering.pricing.services.markup_cache.MarkupCache.invalidate"
        with patch(target) as invalidate:
            Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        invalidate.assert_called_once_with(self.tenant.id)

    def test_assigning_a_plan_invalidates_the_tenant_markup_cache(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        target = "apps.metering.pricing.services.markup_cache.MarkupCache.invalidate"
        with patch(target) as invalidate:
            CustomerPlanAssignment.objects.create(
                tenant=self.tenant, customer=customer, plan=plan)
        invalidate.assert_called_once_with(self.tenant.id)

    def test_deleting_an_assignment_invalidates_the_tenant_markup_cache(self):
        plan = Plan.objects.create(tenant=self.tenant, key="pro", name="Pro")
        customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        row = CustomerPlanAssignment.objects.create(
            tenant=self.tenant, customer=customer, plan=plan)
        target = "apps.metering.pricing.services.markup_cache.MarkupCache.invalidate"
        with patch(target) as invalidate:
            row.delete()
        invalidate.assert_called_once_with(self.tenant.id)
