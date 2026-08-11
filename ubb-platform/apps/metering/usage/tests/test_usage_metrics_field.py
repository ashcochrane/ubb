import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import Posting


@pytest.mark.django_db
def test_posting_stores_usage_metrics_and_tenant_flag_default():
    t = Tenant.objects.create(name="T")
    assert t.require_cost_card_coverage is False
    c = Customer.objects.create(tenant=t, external_id="c1")
    e = Posting.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i",
                                  usage_metrics={"input_tokens": 1500})
    e.refresh_from_db()
    assert e.usage_metrics == {"input_tokens": 1500}
