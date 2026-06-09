"""Capstone integration test for Journey 1 (cost attribution).

A REAL live-server test that drives the `ubb` Python SDK over HTTP against a
running Django server. It proves a tenant can:
  - configure a cost rate-card (via the SDK, hitting the real URL route),
  - record a multi-metric usage event WITHOUT supplying a provider cost,
  - have the server compute COGS from the matching cost card, and
  - read per-customer / per-product provider cost (COGS) back through the SDK.

This exists because mocked-httpx unit tests let real wire-level mismatches ship
undetected (e.g. a `/api/v1/metering/pricing/rate-cards` 404, or a response body
the SDK can't deserialize). A live-server test exercises real URL routing and
the real response contract end to end.
"""
import pytest

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import RateCard


@pytest.fixture
def celery_eager():
    """Run the on-commit outbox dispatch (process_single_event.delay) in-process.

    record_usage fires a transactional-outbox Celery task on commit. Under
    live_server there is no Celery worker / broker, so we run the task eagerly
    (synchronously, no broker) for the duration of the test. This keeps the test
    a real HTTP / routing / pricing exercise while making the async event
    fan-out deterministic. Restored afterwards.
    """
    from config.celery import app

    prev_eager = app.conf.task_always_eager
    prev_propagate = app.conf.task_eager_propagates
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    try:
        yield
    finally:
        app.conf.task_always_eager = prev_eager
        app.conf.task_eager_propagates = prev_propagate


@pytest.mark.django_db(transaction=True)
def test_journey1_cost_attribution_end_to_end_via_sdk(live_server, celery_eager):
    from ubb.metering import MeteringClient

    tenant = Tenant.objects.create(name="J1", products=["metering"])
    _, raw_key = TenantApiKey.create_key(tenant)
    customer = Customer.objects.create(tenant=tenant, external_id="acme")
    # 2 micros per input token: per_unit, unit_quantity=1 token == 1 unit.
    # RateCard.compute(units) == (units * rate + unit_quantity // 2) // unit_quantity + fixed
    #                         == (1000 * 2 + 0) // 1 + 0 == 2000.
    RateCard.objects.create(tenant=tenant, card_type="cost", metric_name="input_tokens",
                            pricing_model="per_unit", rate_per_unit_micros=2, unit_quantity=1,
                            currency="usd")

    client = MeteringClient(api_key=raw_key, base_url=live_server.url)
    try:
        # (a) rate-card create reaches the REAL route (would 404 before the URL fix).
        #     A 404 here would raise UBBAPIError -> test fails. It does not.
        card = client.create_rate_card(card_type="cost", metric_name="output_tokens",
                                       pricing_model="per_unit", rate_per_unit_micros=5,
                                       unit_quantity=1)
        assert card.card_type == "cost"
        assert card.metric_name == "output_tokens"

        # (b) record usage with usage_metrics and NO caller cost -> engine computes COGS.
        #     Drive the SDK's real record_usage() over HTTP: real route, real response
        #     contract, real (tolerant) deserialization into RecordUsageResult.
        res = client.record_usage(customer_id=str(customer.id), request_id="r1",
                                  idempotency_key="i1", product_id="search",
                                  usage_metrics={"input_tokens": 1000})
        # The server computed COGS from the cost rate card (no caller cost supplied).
        assert res.provider_cost_micros == 2000  # 1000 * 2
        assert res.uncosted_metrics == []   # input_tokens HAS a cost card

        # (c) analytics returns per-customer + per-product PROVIDER cost (COGS) via the SDK.
        rep = client.usage_analytics(customer_id=str(customer.id))
        assert rep["total_provider_cost_micros"] == 2000
        assert any(r["customer__external_id"] == "acme" and r["total_provider_cost_micros"] == 2000
                   for r in rep["by_customer"])
        assert any(r["product_id"] == "search" and r["total_provider_cost_micros"] == 2000
                   for r in rep["by_product"])
    finally:
        client.close()
