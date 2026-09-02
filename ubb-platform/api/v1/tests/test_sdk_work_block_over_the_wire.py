"""The SDK's work block, driven over HTTP against the real server, with the
unit of work's state read back off the database after each exit (#422; #187
story 26 and §24; #179 §2).

`ubb-sdk/tests/test_work_block.py` proves what the client SENDS on each of
the five exits, against a mocked wire. What a mocked wire cannot prove is the
claim the ticket makes about the RECORD: that a forgotten declaration leaves
the unit of work OPEN — not `cancelled`, not `failed`, still `active` on the
row with nothing written onto it — and that the declaration the block forgot
then lands on that same row rather than on a second one. Only a live server
can say that, so this module drives the real SDK through `live_server` and
asserts on `Task` rows, never on the client's own bookkeeping.

The SDK is imported at module level on purpose: a stale install of it makes
this module fail to collect, loudly, rather than skip and leave the proof
vacuous.
"""
import pytest

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task
from core.vocabulary import (
    OUTCOME_REASON_EXECUTION_FAILED, TASK_STATUS_ACTIVE, TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
)
from ubb.exceptions import TaskOutcomeRequired
from ubb.metering import MeteringClient

#: The caller's own identifier for the unit of work, stable across retries.
THE_KEY = "nightly-42"


@pytest.fixture
def sdk(live_server):
    """A metering-only tenant with one customer, and the real client pointed
    at the live server. Metering-only, because the start is ungated and this
    module is about the record, not the wallet."""
    tenant = Tenant.objects.create(name="T", products=["metering"])
    _, raw_key = TenantApiKey.create_key(tenant)
    customer = Customer.objects.create(tenant=tenant, external_id="acme")
    client = MeteringClient(api_key=raw_key, base_url=live_server.url,
                            max_retries=0)
    try:
        yield client, str(customer.id)
    finally:
        client.close()


def _row(task_id):
    return Task.objects.get(id=task_id)


@pytest.mark.django_db(transaction=True)
def test_a_clean_exit_with_no_declaration_leaves_the_row_open_and_the_declaration_still_lands(sdk):
    """Story 26, at the database. The row is `active` with no outcome written
    onto it — nothing was invented — and the same row is what the forgotten
    declaration then closes, so recovery is a close and not a second start."""
    client, customer_id = sdk
    with pytest.raises(TaskOutcomeRequired) as caught:
        with client.start_task(customer_id, THE_KEY, external_task_id="run-7") as task:
            pass

    row = _row(task.task_id)
    assert row.status == TASK_STATUS_ACTIVE
    assert row.outcome_reason == ""
    assert row.reason_detail == ""
    assert row.completed_at is None
    assert caught.value.task is task
    assert Task.objects.count() == 1

    ack = caught.value.task.complete()
    assert ack.replayed is False
    row.refresh_from_db()
    assert row.status == TASK_STATUS_COMPLETED
    assert row.completed_at is not None
    assert Task.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_an_ordinary_exception_records_failed_with_execution_failed(sdk):
    """The one ending the wrapper may declare on its own, on the row: the
    reason is the registry's `execution_failed` and the sentence beside it is
    the exception's type, not its message."""
    client, customer_id = sdk
    with pytest.raises(ValueError):
        with client.start_task(customer_id, THE_KEY) as task:
            raise ValueError("the provider returned garbage")

    row = _row(task.task_id)
    assert row.status == TASK_STATUS_FAILED
    assert row.outcome_reason == OUTCOME_REASON_EXECUTION_FAILED
    assert row.reason_detail == "ValueError"
    assert row.completed_at is not None


@pytest.mark.django_db(transaction=True)
def test_an_interrupt_leaves_the_row_exactly_as_it_was(sdk):
    """Story 27, at the database: a Ctrl-C is not evidence of business
    failure, so the row it interrupted is still open and carries nothing."""
    client, customer_id = sdk
    with pytest.raises(KeyboardInterrupt):
        with client.start_task(customer_id, THE_KEY) as task:
            raise KeyboardInterrupt

    row = _row(task.task_id)
    assert row.status == TASK_STATUS_ACTIVE
    assert row.outcome_reason == ""
    assert row.completed_at is None


@pytest.mark.django_db(transaction=True)
def test_a_replayed_start_hands_back_the_original_row(sdk):
    """The key's claim is permanent: a second start with the same key answers
    with the row the first one created — its label standing over the retry's
    — and creates nothing."""
    client, customer_id = sdk
    first = client.start_task(customer_id, THE_KEY, external_task_id="attempt-1")
    again = client.start_task(customer_id, THE_KEY, external_task_id="attempt-2")

    assert again.replayed is True
    assert first.replayed is False
    assert again.task_id == first.task_id
    assert again.external_task_id == "attempt-1"
    assert Task.objects.count() == 1
    assert _row(first.task_id).external_task_id == "attempt-1"
