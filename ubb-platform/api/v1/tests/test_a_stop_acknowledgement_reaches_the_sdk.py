"""The stop's mechanism, bound and measured amount reach the SDK, and a replay
through the SDK answers what the original acknowledgement said (#569).

`ubb-sdk/tests/test_stop_verdict.py` proves the client READS the three facts
off a mocked wire. What only a live server can prove is the end to end: the
real `MeteringClient` against the real routes, raising `UBBStopRequested`
with the facts the recording kept, carrying them typed on a batch item, and
— after the row they were measured on has moved — answering a replay of the
same key with the ORIGINAL figures, on either route.

The SDK is imported at module level on purpose: a stale install of it makes
this module fail to collect, loudly, rather than skip and leave the proof
vacuous (`test_sdk_work_block_over_the_wire.py`'s rule).
"""
from unittest import mock

import pytest

from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work import reasons
from apps.platform.work.models import Task
from core.vocabulary import TRIGGER_SOURCE_USAGE_INGEST
from ubb.exceptions import UBBStopRequested
from ubb.metering import MeteringClient

#: Where the outbox doorbell rings; silenced so a commit never reaches Celery.
DOORBELL = "apps.platform.events.tasks.process_single_event"


@pytest.fixture
def sdk(live_server):
    """A metering-only tenant whose Event Type admits a caller-supplied cost,
    one customer, and the real client pointed at the live server."""
    tenant = Tenant.objects.create(name="T", products=["metering"])
    _, raw_key = TenantApiKey.create_key(tenant)
    customer = Customer.objects.create(tenant=tenant, external_id="acme")
    declares_a_caller_supplied_cost(tenant, DECLARED)
    client = MeteringClient(api_key=raw_key, base_url=live_server.url,
                            max_retries=0)
    with mock.patch(DOORBELL):
        try:
            yield client, str(customer.id)
        finally:
            client.close()


def _a_unit_with_a_ceiling(client, customer_id, ceiling):
    return client.start_task(customer_id, f"work-{ceiling}",
                             task_cogs_ceiling_micros=ceiling).task_id


def _record(client, customer_id, key, task_id, cost):
    return client.record_usage(customer_id=customer_id, idempotency_key=key,
                               event_type=DECLARED, task_id=task_id,
                               provider_cost_micros=cost)


@pytest.mark.django_db(transaction=True)
def test_the_signal_carries_the_facts_and_a_replay_carries_the_originals(sdk):
    client, customer_id = sdk
    unit = _a_unit_with_a_ceiling(client, customer_id, 5_000_000)
    _record(client, customer_id, "k-under", unit, 3_000_000)

    with pytest.raises(UBBStopRequested) as crossed:
        _record(client, customer_id, "k-cross", unit, 2_500_000)
    stop = crossed.value
    assert (stop.stop_reason, stop.stop_scope) == (reasons.TASK_COGS_CEILING, "task")
    assert (stop.trigger_source, stop.stop_bound_micros,
            stop.stop_measured_micros) == (
        TRIGGER_SOURCE_USAGE_INGEST, 5_000_000, 5_500_000)

    # The row moves on: a new ceiling written directly (nothing else writes
    # one), and more cost on the work. The replay still says what was said.
    Task.objects.filter(id=unit).update(task_cogs_ceiling_micros=90_000_000)
    with pytest.raises(UBBStopRequested):
        _record(client, customer_id, "k-more", unit, 1_000_000)
    with pytest.raises(UBBStopRequested) as replayed:
        _record(client, customer_id, "k-cross", unit, 2_500_000)
    assert replayed.value.event_id == stop.event_id
    assert (replayed.value.trigger_source, replayed.value.stop_bound_micros,
            replayed.value.stop_measured_micros) == (
        TRIGGER_SOURCE_USAGE_INGEST, 5_000_000, 5_500_000)

    # The same key through the batch: one typed item, the same facts.
    [item] = client.record_batch([{
        "customer_id": customer_id, "idempotency_key": "k-cross",
        "event_type": DECLARED, "task_id": unit,
        "provider_cost_micros": 2_500_000}]).results
    assert item.event_id == stop.event_id
    assert (item.stop, item.stop_reason, item.trigger_source,
            item.stop_bound_micros, item.stop_measured_micros) == (
        True, reasons.TASK_COGS_CEILING, TRIGGER_SOURCE_USAGE_INGEST,
        5_000_000, 5_500_000)


@pytest.mark.django_db(transaction=True)
def test_a_key_first_recorded_in_a_batch_replays_identically_through_the_sdk(sdk):
    client, customer_id = sdk
    unit = _a_unit_with_a_ceiling(client, customer_id, 2_000_000)
    [first] = client.record_batch([{
        "customer_id": customer_id, "idempotency_key": "k-batch",
        "event_type": DECLARED, "task_id": unit,
        "provider_cost_micros": 2_100_000}]).results
    assert (first.stop, first.stop_bound_micros, first.stop_measured_micros) == (
        True, 2_000_000, 2_100_000)

    with pytest.raises(UBBStopRequested) as replayed:
        _record(client, customer_id, "k-batch", unit, 2_100_000)

    assert replayed.value.event_id == first.event_id
    assert (replayed.value.trigger_source, replayed.value.stop_bound_micros,
            replayed.value.stop_measured_micros) == (
        first.trigger_source, first.stop_bound_micros, first.stop_measured_micros)
