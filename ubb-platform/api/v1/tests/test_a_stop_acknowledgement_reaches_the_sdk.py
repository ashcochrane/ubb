"""The stop's mechanism, bound and measured amount reach the SDK, and a replay
through the SDK answers what the original acknowledgement said (#569;
ADR-0019).

`ubb-sdk/tests/test_stop_verdict.py` proves the client READS the three facts
off a mocked wire. What only a live server can prove is the end to end: the
real `MeteringClient` against the real routes, raising `UBBStopRequested`
with the facts the recording kept, carrying them typed on a batch item, and —
after every live fact they were measured on has moved — answering a replay
of the same key with the ORIGINAL acknowledgement, a unit's and a customer's
stop alike, on either route.

The SDK is imported at module level on purpose: a stale install of it makes
this module fail to collect, loudly, rather than skip and leave the proof
vacuous (`test_sdk_work_block_over_the_wire.py`'s rule).
"""
from unittest import mock

import pytest

from api.v1.tests._helpers import a_live_client
from apps.billing.gating.models import CustomerSpendPool
from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.gating.tests.test_a_blocking_pool_stops_prepaid_work_as_it_stops_postpaid import (
    DOORBELL)
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at)
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import UsageRecorded
from apps.platform.work import reasons
from apps.platform.work.models import Task
from core.vocabulary import (
    CEILING_STATUS_WITHIN_CEILING, CUSTOMER_BILLING_MODE_PREPAID,
    SPEND_POOL_ENFORCE_MODE_BLOCKING, TRIGGER_SOURCE_USAGE_INGEST)
from ubb.exceptions import UBBStopRequested


@pytest.fixture
def sdk(live_server):
    """A metering-only tenant whose Event Type admits a caller-supplied cost,
    and the real client pointed at the live server."""
    client, tenant, customer = a_live_client(live_server)
    declares_a_caller_supplied_cost(tenant, DECLARED)
    with mock.patch(DOORBELL):
        try:
            yield client, str(customer.id)
        finally:
            client.close()


@pytest.fixture
def billing_sdk(live_server):
    """An enforcing prepaid tenant that prices what each report measures, a
    customer with a wallet no floor bites through, and the real client."""
    client, tenant, customer = a_live_client(
        live_server, products=["metering", "billing"],
        billing_mode=CUSTOMER_BILLING_MODE_PREPAID, enforcement_mode="enforcing")
    declares_a_caller_supplied_cost(tenant, DECLARED)
    a_rule_that_prices_what_it_measures(tenant)
    Wallet.objects.create(customer=customer, balance_micros=100_000_000)
    with mock.patch(DOORBELL):
        try:
            yield client, tenant, customer
        finally:
            client.close()


def _a_unit_with_a_ceiling(client, customer_id, ceiling):
    return client.start_task(customer_id, f"work-{ceiling}",
                             task_cogs_ceiling_micros=ceiling).task_id


def _record(client, customer_id, key, task_id, cost):
    return client.record_usage(customer_id=customer_id, idempotency_key=key,
                               event_type=DECLARED, task_id=task_id,
                               provider_cost_micros=cost)


def _bill(client, customer, key, bills):
    return client.record_usage(customer_id=str(customer.id), idempotency_key=key,
                               event_type=DECLARED, provider_cost_micros=1_000,
                               measurements=priced_at(bills))


def _facts(signal):
    return (signal.trigger_source, signal.stop_bound_micros,
            signal.stop_measured_micros)


def _a_pool(tenant, customer, *, cap, pct):
    return CustomerSpendPool.objects.create(
        tenant=tenant, customer=customer, cap_micros=cap, hard_stop_pct=pct,
        enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)


@pytest.mark.django_db(transaction=True)
def test_the_signal_carries_the_facts_and_a_replay_carries_the_originals(sdk):
    client, customer_id = sdk
    unit = _a_unit_with_a_ceiling(client, customer_id, 5_000_000)
    _record(client, customer_id, "k-under", unit, 3_000_000)

    with pytest.raises(UBBStopRequested) as crossed:
        _record(client, customer_id, "k-cross", unit, 2_500_000)
    stop = crossed.value
    assert (stop.stop_reason, stop.stop_scope) == (reasons.TASK_COGS_CEILING, "task")
    assert _facts(stop) == (TRIGGER_SOURCE_USAGE_INGEST, 5_000_000, 5_500_000)

    # The row moves on: a new ceiling written directly (nothing else writes
    # one), and more cost on the work. The replay still says what was said.
    Task.objects.filter(id=unit).update(task_cogs_ceiling_micros=90_000_000)
    with pytest.raises(UBBStopRequested):
        _record(client, customer_id, "k-more", unit, 1_000_000)
    with pytest.raises(UBBStopRequested) as replayed:
        _record(client, customer_id, "k-cross", unit, 2_500_000)
    assert replayed.value.event_id == stop.event_id
    assert _facts(replayed.value) == (TRIGGER_SOURCE_USAGE_INGEST, 5_000_000, 5_500_000)

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
def test_an_unstopped_original_replays_unstopped_with_its_own_assessment(sdk):
    """Pins 3 and 6: the work has since stopped at its ceiling; the replay of
    a report first acknowledged unstopped raises nothing and carries the
    assessment the original made (40 %), not where the unit stands now."""
    client, customer_id = sdk
    unit = _a_unit_with_a_ceiling(client, customer_id, 10_000_000)
    first = _record(client, customer_id, "k-first", unit, 4_000_000)
    with pytest.raises(UBBStopRequested):
        _record(client, customer_id, "k-then", unit, 6_000_000)

    replayed = _record(client, customer_id, "k-first", unit, 4_000_000)

    assert replayed.event_id == first.event_id
    assert replayed.stop is False
    assert (replayed.trigger_source, replayed.stop_bound_micros,
            replayed.stop_measured_micros) == (None, None, None)
    assert replayed.ceiling_status.value == CEILING_STATUS_WITHIN_CEILING
    assert replayed.ceiling_used_percentage == 40


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
    assert _facts(replayed.value) == (
        first.trigger_source, first.stop_bound_micros, first.stop_measured_micros)


@pytest.mark.django_db(transaction=True)
def test_a_customer_stop_replays_its_facts_after_its_pool_moves_and_clears(billing_sdk):
    """Pins 1, 3 and 5 for a customer-wide stop: the Pool is raised, the
    hourly pass clears the stop and a new report is not stopped — and the
    replay still raises with the original mechanism and figures."""
    client, tenant, customer = billing_sdk
    pool = _a_pool(tenant, customer, cap=10_000_000, pct=80)
    with pytest.raises(UBBStopRequested) as original:
        _bill(client, customer, "k-pool", 9_000_000)
    assert original.value.stop_reason == reasons.CUSTOMER_SPEND_POOL
    assert _facts(original.value) == (TRIGGER_SOURCE_USAGE_INGEST, 8_000_000, 9_000_000)

    CustomerSpendPool.objects.filter(id=pool.id).update(cap_micros=100_000_000)
    LiveCounter.reconcile(customer.id, tenant)
    assert _bill(client, customer, "k-after", 1_000).stop is False

    with pytest.raises(UBBStopRequested) as replayed:
        _bill(client, customer, "k-pool", 9_000_000)
    assert replayed.value.event_id == original.value.event_id
    assert _facts(replayed.value) == (TRIGGER_SOURCE_USAGE_INGEST, 8_000_000, 9_000_000)


@pytest.mark.django_db(transaction=True)
def test_a_hard_floor_reaches_the_sdk_as_signed_figures(billing_sdk):
    """The owner's review of #612: the figures are signed. A floor is
    published as a balance (the negated minimum, -1,000,000) and the wallet
    sits below it (-1,500,000); both reach the generated client as negative
    integers — on the raised signal and on a typed batch item alike."""
    client, _, customer = billing_sdk
    Wallet.objects.filter(customer=customer).update(balance_micros=3_000_000)
    CustomerBillingProfile.objects.create(customer=customer,
                                          min_balance_micros=1_000_000)

    with pytest.raises(UBBStopRequested) as floor:
        _bill(client, customer, "k-floor", 4_500_000)
    assert floor.value.stop_reason == reasons.HARD_FLOOR
    assert _facts(floor.value) == (TRIGGER_SOURCE_USAGE_INGEST, -1_000_000, -1_500_000)

    [item] = client.record_batch([{
        "customer_id": str(customer.id), "idempotency_key": "k-floor",
        "event_type": DECLARED, "provider_cost_micros": 1_000,
        "measurements": priced_at(4_500_000)}]).results
    assert (item.stop_bound_micros, item.stop_measured_micros) == (-1_000_000, -1_500_000)


@pytest.mark.django_db(transaction=True)
def test_609s_precedence_is_replayed_as_it_was_selected(billing_sdk):
    """Pin 7: a pooled seat's report named the business's Pool line over the
    seat's own (4,500,000 / 5,000,000 against 3,000,000 / 3,200,000). The
    business's line clears and the seat's own is named now — and the replay
    still raises with the business line's figures."""
    client, tenant, _ = billing_sdk
    biz = Customer.objects.create(tenant=tenant, external_id="biz",
                                  account_type="business",
                                  billing_topology="pooled")
    Wallet.objects.create(customer=biz, balance_micros=100_000_000)
    seat = Customer.objects.create(tenant=tenant, external_id="s1",
                                   account_type="seat", parent=biz)
    _a_pool(tenant, None, cap=3_000_000, pct=100)          # every seat's own
    business_pool = _a_pool(tenant, biz, cap=5_000_000, pct=90)
    _bill(client, seat, "k-seat", 3_200_000)
    for row in OutboxEvent.objects.filter(event_type=UsageRecorded.EVENT_TYPE,
                                          tenant_id=tenant.id):
        handle_usage_recorded_billing(str(row.id), row.payload)  # the seat's line
    with pytest.raises(UBBStopRequested):
        _bill(client, seat, "k-business", 1_800_000)            # the business's
    with pytest.raises(UBBStopRequested) as original:
        _bill(client, seat, "k-named", 1_000)
    assert _facts(original.value) == (TRIGGER_SOURCE_USAGE_INGEST, 4_500_000, 5_000_000)

    CustomerSpendPool.objects.filter(id=business_pool.id).update(
        cap_micros=100_000_000)
    LiveCounter.reconcile(biz.id, tenant)
    with pytest.raises(UBBStopRequested) as now:
        _bill(client, seat, "k-now", 1_000)
    assert _facts(now.value) == (TRIGGER_SOURCE_USAGE_INGEST, 3_000_000, 3_200_000)

    with pytest.raises(UBBStopRequested) as replayed:
        _bill(client, seat, "k-named", 1_000)
    assert replayed.value.event_id == original.value.event_id
    assert _facts(replayed.value) == (TRIGGER_SOURCE_USAGE_INGEST, 4_500_000, 5_000_000)
