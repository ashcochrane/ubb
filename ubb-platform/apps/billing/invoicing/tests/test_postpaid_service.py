import datetime
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.billing.invoicing.models import PostpaidUsageConfig
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


@pytest.mark.django_db
class TestAggregate:
    def _events(self, t, c):
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=600_000, billed_cost_micros=800_000, product_id="chat")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r2", idempotency_key="i2",
            provider_cost_micros=100_000, billed_cost_micros=200_000, product_id="")  # no product

    def test_single_line_default(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        self._events(t, c)
        total, lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert total == 1_000_000
        assert lines == [("", 1_000_000)]

    def test_group_by_product_with_other_bucket(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="product_id")
        self._events(t, c)
        total, lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert total == 1_000_000
        assert sum(a for _, a in lines) == total                 # invariant: lines sum to total
        labels = dict(lines)
        assert labels["chat"] == 800_000 and labels["(other)"] == 200_000

    def test_group_by_tag_with_other_bucket(self):
        t = Tenant.objects.create(name="T"); c = Customer.objects.create(tenant=t, external_id="c1")
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="tag:seat")
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=1, billed_cost_micros=500_000, tags={"seat": "alice"})
        UsageEvent.objects.create(tenant=t, customer=c, request_id="r2", idempotency_key="i2",
            provider_cost_micros=1, billed_cost_micros=300_000, tags=None)  # no tag
        total, lines = PostpaidUsageService.aggregate_lines(t, c, PS, PE)
        assert total == 800_000 and sum(a for _, a in lines) == 800_000
        assert dict(lines)["alice"] == 500_000 and dict(lines)["(other)"] == 300_000
