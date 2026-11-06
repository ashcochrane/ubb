"""Shared setup for the gating app's signal-ledger tests
(`docs/conventions/testing.md`), and — below — for the tests of suspension and
recovery that watch a customer's row and its seat roster while the real money
paths run.

WHICH STOP LINE A FIXTURE'S BARE CROSSING DRIVES. Until #458 the producers
forked on the owner's tenant billing mode to name the customer-wide stop, and
every test here reached for that fork to say what it EXPECTED. The fork is
gone from production — each lane names its own line now, and the ledger keys
by it — and since #459 the pool's line is driven in EVERY mode, so the mode
decides nothing in production at all. What the mode still decides in a
FIXTURE is which line a bare over-limit debit with no pool declared and a
wallet of nothing reaches: a `postpaid` fixture with a pool is driving the
pool's line, and every other mode's fixture with a wallet the wallet floor's.
The expectation lives here, in the tests' own words; a case about the OTHER
line on a mode names it outright rather than asking this.
"""
from apps.billing.gating.services.stop_signal_service import (
    StopSignalService, control_id_of, opening_facts)
from apps.platform.work import reasons
from core.vocabulary import TRIGGER_SOURCE_USAGE_INGEST

#: HOW A FIXTURE'S EPISODE OPENED, WHERE THE CASE IS NOT ABOUT IT (#569).
#: Every lane that opens an episode states its mechanism, bound and measured
#: amount, so a test driving the ledger directly states them too: a usage
#: report's lane, with figures the fixture does not claim — null, which is
#: what an episode says of a figure nobody stamped.
FIXTURE_OPENING = opening_facts(trigger_source=TRIGGER_SOURCE_USAGE_INGEST,
                                stop_bound_micros=None,
                                stop_measured_micros=None)


def stop_line(tenant):
    """The stop line the tenant's counter lane drives — the test's expectation."""
    if tenant.billing_mode == "postpaid":
        return reasons.CUSTOMER_SPEND_POOL
    return reasons.HARD_FLOOR


def drive_a_stop(owner_id, tenant, **kwargs):
    """Open the episode a crossing on this tenant's lane would open, with the
    control the lane would name — the resolved pool row or the row carrying
    the floor — so a case says only WHO crossed and lets the seam say what
    that stop carries. It opened as ``FIXTURE_OPENING`` unless the case says
    otherwise."""
    line = stop_line(tenant)
    return StopSignalService.drive_stop(
        owner_id, tenant, line=line,
        control_id=control_id_of(line, owner_id, tenant),
        **{**FIXTURE_OPENING, **kwargs})


# -- suspension and recovery (R10 Stage C4) -----------------------------------
#
# A hand-over between suspension causes must never pass through `active`, so
# these tests record every state the customer's row is SAVED with and every
# roster notification, and drive the money conditions through their real
# paths: usage billed after the customer stopped being active, a lost dispute's
# claw-back, a credit as it commits.


def record_saved_states(test, customer):
    """Every ``(status, suspension_reason)`` ``customer``'s row is SAVED with
    from here on, until the test ends — so a write of ``active`` undone in the
    same transaction still shows. It sees ``save()`` only (``post_save``), which
    is how the one reactivation site writes; a ``QuerySet.update()`` would
    pass it unseen."""
    from django.db.models.signals import post_save
    from apps.platform.customers.models import Customer

    states = []

    def record(sender, instance, **kwargs):
        if instance.pk == customer.pk:
            states.append((instance.status, instance.suspension_reason))

    post_save.connect(record, sender=Customer, weak=False)
    test.addCleanup(post_save.disconnect, record, sender=Customer)
    return states


def record_the_roster(test):
    """Swap the seat roster's listeners for a recorder until the test ends;
    answers the list of businesses notified."""
    from apps.platform.customers import hooks

    notified = []
    listeners = list(hooks._listeners)
    hooks._listeners[:] = [notified.append]
    test.addCleanup(lambda: hooks._listeners.__setitem__(slice(None), listeners))
    return notified


def bill_in_flight_usage(tenant, customer, usage_micros, key):
    """Usage the customer recorded while still active, billed after it stopped
    being active: the outbox handler draws the wallet down asynchronously."""
    import uuid
    from dataclasses import asdict
    from apps.billing.handlers import handle_usage_recorded_billing
    from apps.metering.usage.tests._helpers import a_posting
    from apps.platform.events.schemas import UsageRecorded

    posting = a_posting(tenant=tenant, customer=customer, idempotency_key=key,
                        provider_cost_micros=usage_micros, billed_cost_micros=usage_micros)
    handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
        pricing_status_reason=None, tenant_id=tenant.id, customer_id=customer.id,
        event_id=str(posting.id), cost_micros=usage_micros)))


def pay_a_top_up(tenant, customer, key, top_up_micros):
    """A paid top-up of ``top_up_micros`` on charge ``ch_<key>``, credited as a
    checkout top-up (the customer is its own billing owner)."""
    from apps.billing.topups.models import TopUpAttempt
    from apps.billing.wallets import operations as wallet_ops
    from core.vocabulary import GRANT_SOURCE_CHECKOUT

    attempt = TopUpAttempt.objects.create(
        customer=customer, billing_owner_id=customer.id, amount_micros=top_up_micros,
        trigger="manual", status="succeeded", stripe_charge_id=f"ch_{key}")
    wallet_ops.credit_top_up(
        customer_id=customer.id, tenant=tenant, amount_micros=top_up_micros,
        idempotency_key=f"topup:cs_{key}", source=GRANT_SOURCE_CHECKOUT,
        source_reference=str(attempt.id), description="Stripe top-up")


def lose_its_dispute(tenant, key, disputed_minor):
    """The dispute on charge ``ch_<key>`` (``pay_a_top_up``) closes lost for
    ``disputed_minor`` cents, through the real claw-back handler; the event
    names the tenant's connected account."""
    from unittest.mock import MagicMock
    from apps.billing.connectors.stripe.webhooks import handle_charge_dispute_closed

    lost = MagicMock()
    lost.data.object.id = f"dp_{key}"
    lost.data.object.charge = f"ch_{key}"
    lost.data.object.status = "lost"
    lost.data.object.amount = disputed_minor
    lost.data.object.currency = "usd"
    lost.account = tenant.stripe_connected_account_id
    handle_charge_dispute_closed(lost)


def credit_as_committed(test, tenant, customer, amount_micros, key):
    """A wallet credit as it commits in life: its on-commit credit hook runs
    (the floor's recovery), with the outbox's Celery hand-off patched away."""
    from unittest.mock import patch
    from apps.billing.wallets import operations as wallet_ops

    with patch("apps.platform.events.tasks.process_single_event"), \
            test.captureOnCommitCallbacks(execute=True):
        wallet_ops.credit(customer_id=customer.id, tenant=tenant,
                          amount_micros=amount_micros, idempotency_key=key)
