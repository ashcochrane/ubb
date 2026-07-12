import pytest
from apps.metering.usage.models import RawIngestEvent
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="TestTenant")


@pytest.fixture
def customer(tenant):
    return Customer.objects.create(
        tenant=tenant,
        external_id="test-customer",
        account_type="business",
        billing_topology="standalone"
    )


def test_raw_ingest_defaults(tenant, customer):
    raw = RawIngestEvent.objects.create(
        tenant=tenant, customer=customer, billing_owner_id=customer.id,
        idempotency_key="k1", payload={"event_type": "llm_call"},
        estimate_micros=120_000)
    assert raw.status == "pending"
    assert raw.attempts == 0
    assert raw.held is True
    assert raw.estimate_exact is False
    assert raw.run_id is None


def test_duplicate_idempotency_keys_allowed(tenant, customer):
    for _ in range(2):  # retry-append is by design; settle dedups
        RawIngestEvent.objects.create(
            tenant=tenant, customer=customer, billing_owner_id=customer.id,
            idempotency_key="same", payload={}, estimate_micros=1)
    assert RawIngestEvent.objects.filter(idempotency_key="same").count() == 2
