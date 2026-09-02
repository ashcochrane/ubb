"""Capstone integration test for Journey 1 (cost attribution).

A REAL live-server test that drives the `ubb` Python SDK over HTTP against a
running Django server. It proves a tenant can:
  - configure a cost rate-card (via the SDK, hitting the real URL route),
  - record a usage event of many quantities WITHOUT supplying a provider cost,
  - have the server compute COGS from the matching cost card, and
  - read per-customer / per-product provider cost (COGS) back through the SDK.

This exists because mocked-httpx unit tests let real wire-level mismatches ship
undetected (e.g. a `/api/v1/metering/pricing/cost-books` 404, or a response body
the SDK can't deserialize). A live-server test exercises real URL routing and
the real response contract end to end.
"""
import httpx
import pytest

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book, rate_in_default_book


def _post(api, path, body):
    """POST JSON to the live server's book-centric pricing surface (raw HTTP)."""
    r = api.post(path, json=body)
    r.raise_for_status()
    return r.json()


def _get(api, path):
    r = api.get(path)
    r.raise_for_status()
    return r.json()


# `_no_outbox_dispatch` lives in this package's `conftest.py` now (#422): the
# work-block live test needs the same neutralised dispatch, and one fixture
# with one docstring beats two.


@pytest.mark.django_db(transaction=True)
def test_journey1_cost_attribution_end_to_end_via_sdk(live_server, _no_outbox_dispatch):
    from ubb.metering import MeteringClient

    tenant = Tenant.objects.create(name="J1", products=["metering"])
    _, raw_key = TenantApiKey.create_key(tenant)
    customer = Customer.objects.create(tenant=tenant, external_id="acme")
    # dimensions= now resolves through the registry (#128 rework); an
    # identity declaration (key == slot) lets a declared dim1 value stay
    # groupable by "dim1".
    GroupingField.objects.create(tenant=tenant, key="dim1", slot="grouping_field_1", scope="event")
    # 2 micros per input token: per_unit, unit_quantity=1 token == 1 unit.
    # Rate.compute(units) == (units * rate + unit_quantity // 2) // unit_quantity + fixed
    #                         == (1000 * 2 + 0) // 1 + 0 == 2000.
    cost_rate_in_default_book(tenant, measurement_key="input_tokens",
                            rate_structure="per_unit", rate_per_unit_micros=2, unit_quantity=1,
                            currency="usd")
    # The quantity the rule opened over HTTP below prices. A rule names a
    # declared quantity (#326), and this journey opens one through the real
    # surface — declaring the change and publishing it, since #367 deleted the
    # immediate route — so the declaration is part of the journey rather than
    # of a fixture.
    declares_a_quantity(tenant, "output_tokens")

    client = MeteringClient(api_key=raw_key, base_url=live_server.url)
    api = httpx.Client(base_url=live_server.url,
                       headers={"Authorization": f"Bearer {raw_key}"})
    try:
        # (a) the book-centric create routes reach the REAL server over HTTP (a
        #     404/422 on a renamed route would raise here). Create a cost book,
        #     then add a rate under it -> every API rate is book-scoped.
        book_id = _post(api, "/api/v1/metering/pricing/cost-books", {
            "key": "extra", "provider_key": ""})["id"]
        # Opening a rule is a declared change published in the same breath
        # (#367) — the immediate route this journey used to POST to is gone.
        base = f"/api/v1/metering/pricing/books/{book_id}"
        declared = _post(api, f"{base}/publishes", {"changes": [{
            "kind": "add", "measurement_key": "output_tokens",
            "rate_structure": "per_unit", "rate_per_unit_micros": 5,
            "unit_quantity": 1}]})
        published = _post(api, f"{base}/publishes/{declared['id']}/publish", {})
        (opened,) = published["opened_rule_ids"]
        (row,) = _get(api, f"{base}/rates")["data"]
        assert row["id"] == opened
        assert row["measurement_key"] == "output_tokens"
        assert row["book_id"] == book_id

        # (b) record usage with measurements and NO caller cost -> engine computes COGS.
        #     Drive the SDK's real record_usage() over HTTP: real route, real response
        #     contract, real (tolerant) deserialization into RecordUsageResult.
        res = client.record_usage(customer_id=str(customer.id),
                                  idempotency_key="i1", dimensions={"dim1": "search"},
                                  measurements={"input_tokens": 1000})
        # The server computed COGS from the cost rate card (no caller cost supplied).
        assert res.provider_cost_micros == 2000  # 1000 * 2
        assert res.uncosted_measurement_keys == []   # input_tokens HAS a cost card

        # (c) analytics returns per-customer + per-product PROVIDER cost (COGS) via the SDK.
        rep = client.usage_analytics(customer_id=str(customer.id), dimensions=["dim1"])
        assert rep["total_provider_cost_micros"] == 2000
        assert any(r["customer__external_id"] == "acme" and r["total_provider_cost_micros"] == 2000
                   for r in rep["by_customer"])
        assert any(r["grouping_field_value"] == "search"
                   and r["total_provider_cost_micros"] == 2000
                   for r in rep["breakdowns"]["dim1"])
    finally:
        client.close()
        api.close()
