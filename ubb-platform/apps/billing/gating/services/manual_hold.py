"""The manual hold — an accountable operator's suspension of one customer, and
its release (R10 Stage C4; owner/consultant ruling 2026-11-05, PLAN §7 item
41, FINAL).

UBB keeps the deliberate manual ("admin/fraud") suspension: a hold no
automatic recovery lifts. Until C4 the only way to place or lift one was to
edit raw fields in the Django Customer admin, which bypassed every lifecycle
side effect — the announcement, the seat-roster notification — and let an
operator rewrite a system cause (a `hard_floor` suspension edited to
`payment_failed` was then lifted by the AR pass with the wallet still past
its floor). Those fields are read-only in the admin now. This module is the
ONE workflow for the concept, and `manage.py set_customer_manual_hold` is its
operator surface.

- **The representation is the existing one:** ``status = suspended`` with an
  EMPTY ``suspension_reason`` (``LiveCounter.MANUAL_HOLD_REASON``) — the
  glossary's manual suspension. No new reason value.
- **Placing a hold** is allowed only on an active, live customer. It writes the
  status and reason together, announces ``customer.suspended`` (reason
  ``""``) and, for a seat, notifies its business's roster once — all in one
  transaction under the customer's row lock. A customer already suspended for
  a system cause (``hard_floor``, ``customer_spend_pool``, ``payment_failed``,
  ``dispute_lost``) is REFUSED: a hold never overwrites the cause its own
  recovery owns. A customer already held is a no-op.
- **Releasing a hold** goes through the one reactivation site
  (``LiveCounter.release_manual_hold``), which announces
  ``customer.reactivated`` and notifies a seat's roster, exactly as every
  other clear. Only a manual hold is released; a system cause is REFUSED. If a
  qualifying payment failure still stands, the customer stays suspended and
  that failure becomes the cause (RULED Q4) — the release is answered as
  handed over, not done. An active customer is a no-op.
- **Closing a customer is not a supported v1 transition**, and nothing here
  writes ``closed``.

The operator's id is logged on every outcome (``customer.manual_hold``). The
governance audit ledger has no action for a hold, and its action set is a
closed concept published in the API contract, so a ledger entry waits on that
ruling (see the C4 PR).
"""
import logging

from django.db import transaction

from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.gating.services.stop_signal_service import announced_balance
from apps.platform.customers.hooks import notify_if_a_seat
from apps.platform.customers.models import (
    CUSTOMER_STATUS_ACTIVE, CUSTOMER_STATUS_SUSPENDED, Customer)
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import CustomerSuspended
from apps.platform.work import reasons

logger = logging.getLogger(__name__)

MANUAL_HOLD_REASON = LiveCounter.MANUAL_HOLD_REASON

#: What one operation came to.
HELD = "held"
ALREADY_HELD = "already_held"
RELEASED = "released"
ALREADY_ACTIVE = "already_active"
#: A release that met a standing payment failure: the customer stays
#: suspended, now for ``payment_failed``, which its own recovery owns.
HANDED_OVER = "handed_over_to_payment_failed"


class ManualHoldRefused(Exception):
    """The operation would act on something that is not a manual hold: a
    customer that does not exist or is deleted, one suspended for a system
    cause, or one in a state a hold does not apply to. Nothing was written."""


def _log(customer, outcome, operator):
    logger.info("customer.manual_hold", extra={"data": {
        "tenant_id": str(customer.tenant_id), "customer_id": str(customer.id),
        "outcome": outcome, "operator": str(operator)}})


def place_manual_hold(customer_id, *, operator):
    """Suspend one live, active customer under a manual hold. Answers
    ``HELD`` or ``ALREADY_HELD``; raises ``ManualHoldRefused`` otherwise."""
    with transaction.atomic():
        customer = (Customer.objects.select_for_update(of=("self",))
                    .select_related("tenant").filter(id=customer_id).first())
        if customer is None:
            raise ManualHoldRefused(f"no live customer {customer_id}")
        if (customer.status == CUSTOMER_STATUS_SUSPENDED
                and customer.suspension_reason == MANUAL_HOLD_REASON):
            outcome = ALREADY_HELD
        elif customer.status == CUSTOMER_STATUS_SUSPENDED:
            raise ManualHoldRefused(
                f"customer {customer.id} is suspended for "
                f"{customer.suspension_reason!r}, a cause its own recovery owns; "
                "a manual hold never overwrites it")
        elif customer.status != CUSTOMER_STATUS_ACTIVE:
            raise ManualHoldRefused(
                f"customer {customer.id} is {customer.status!r}; only an active "
                "customer can be held")
        else:
            customer.status = CUSTOMER_STATUS_SUSPENDED
            customer.suspension_reason = MANUAL_HOLD_REASON
            customer.save(update_fields=["status", "suspension_reason", "updated_at"])
            write_event(CustomerSuspended(
                tenant_id=str(customer.tenant_id), customer_id=str(customer.id),
                reason=MANUAL_HOLD_REASON,
                balance_micros=announced_balance(customer.id, customer.tenant)))
            notify_if_a_seat(customer)
            outcome = HELD
    _log(customer, outcome, operator)
    return outcome


def release_manual_hold(customer_id, *, operator):
    """Release one customer's manual hold through the one reactivation site.
    Answers ``RELEASED``, ``ALREADY_ACTIVE`` or ``HANDED_OVER``; raises
    ``ManualHoldRefused`` for anything that is not a manual hold."""
    customer = Customer.objects.filter(id=customer_id).first()
    if customer is None:
        raise ManualHoldRefused(f"no live customer {customer_id}")
    if customer.status == CUSTOMER_STATUS_ACTIVE:
        _log(customer, ALREADY_ACTIVE, operator)
        return ALREADY_ACTIVE
    if not (customer.status == CUSTOMER_STATUS_SUSPENDED
            and customer.suspension_reason == MANUAL_HOLD_REASON):
        raise ManualHoldRefused(
            f"customer {customer.id} is {customer.status!r} for "
            f"{customer.suspension_reason!r}, which is not a manual hold; its own "
            "recovery owns it")
    # The reactivation site re-checks all of this under the row lock.
    moved = LiveCounter.release_manual_hold(customer.id)
    customer.refresh_from_db()
    if moved:
        outcome = RELEASED
    elif customer.status == CUSTOMER_STATUS_ACTIVE:
        outcome = ALREADY_ACTIVE               # a concurrent release won
    elif (customer.status == CUSTOMER_STATUS_SUSPENDED
          and customer.suspension_reason == reasons.PAYMENT_FAILED):
        outcome = HANDED_OVER
    else:
        raise ManualHoldRefused(
            f"customer {customer.id} was not released: it is {customer.status!r} "
            f"for {customer.suspension_reason!r}")
    _log(customer, outcome, operator)
    return outcome
