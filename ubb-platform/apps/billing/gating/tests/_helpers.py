"""Shared setup for the gating app's signal-ledger tests
(`docs/conventions/testing.md`).

WHICH STOP LINE A FIXTURE'S TENANT DRIVES. Until #458 the producers forked on
the owner's tenant billing mode to name the customer-wide stop, and every
test here reached for that fork to say what it EXPECTED. The fork is gone
from production — each lane names its own line now, and the ledger keys by
it — so the expectation lives here, in the tests' own words: a fixture that
chose `postpaid` is driving the pool's line and every other mode the wallet
floor's, because that is which lane the mode's counter feeds. If a lane ever
drives a different line for a mode, this is the statement that goes red.
"""
from apps.billing.gating.services.stop_signal_service import (
    StopSignalService, control_id_of)
from apps.platform.work import reasons


def stop_line(tenant):
    """The stop line the tenant's counter lane drives — the test's expectation."""
    if tenant.billing_mode == "postpaid":
        return reasons.CUSTOMER_SPEND_POOL
    return reasons.HARD_FLOOR


def drive_a_stop(owner_id, tenant, **kwargs):
    """Open the episode a crossing on this tenant's lane would open, with the
    control the lane would name — the resolved pool row or the row carrying
    the floor — so a case says only WHO crossed and lets the seam say what
    that stop carries."""
    line = stop_line(tenant)
    return StopSignalService.drive_stop(
        owner_id, tenant, line=line,
        control_id=control_id_of(line, owner_id, tenant), **kwargs)
