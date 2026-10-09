"""Shared setup for the gating app's signal-ledger tests
(`docs/conventions/testing.md`).

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
