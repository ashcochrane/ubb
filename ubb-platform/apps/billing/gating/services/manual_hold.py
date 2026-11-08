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
  glossary's *manual hold*. No new reason value.
- **Placing a hold** is allowed only on an active, live customer. It writes the
  status and reason together, announces ``customer.suspended`` (reason
  ``""``) and, for a seat, notifies its business's roster once — all in one
  transaction under the customer's row lock. A customer already suspended for
  a system cause (``hard_floor``, ``customer_spend_pool``, ``payment_failed``,
  ``dispute_lost``) is REFUSED: a hold never overwrites the cause its own
  recovery owns. A customer already held is a no-op.
- **Releasing a hold REMOVES THE MANUAL CAUSE; it never forces the customer
  active** (Ruling B). It goes through the one reactivation site
  (``LiveCounter.clear_manual_hold``), which decides under the customer's row
  lock what holds now. With nothing else standing, the customer is active
  again, ``customer.reactivated`` is announced once and a seat's roster is
  notified once, exactly as every other clear. If a system condition still
  stands — a qualifying payment failure (RULED Q4), a stop line still open
  under ``enforcing``, or a wallet past its floor — that cause takes over: the
  customer stays suspended, nothing is announced (it entered no new state),
  and the release is answered ``HANDED_OVER``, naming the cause. Only a manual
  hold is released; a customer already suspended for a system cause is
  REFUSED. An active customer is a no-op.
- **Closing a customer is not a supported v1 transition**, and nothing here
  writes ``closed``.

The operator's id is logged on every outcome, refusals and failures included
(``customer.manual_hold``), and — since R10 Stage C5 (PLAN §7 item 42, FINAL
2026-11-06) — every SUCCESSFUL state change is also a durable governance audit
record under the operator actor, on the ``customer`` record:

- ``customer.manual_hold_set`` ONLY when a hold is actually established
  (``active -> suspended/manual``, outcome ``HELD``), written inside the same
  transaction as the state change;
- ``customer.manual_hold_released`` whenever THIS call actually removed an
  existing hold — both when the customer became ``active`` (``RELEASED``) and
  when a standing system cause took over and it stays ``suspended``
  (``HANDED_OVER``) — recording the resulting status and suspension reason.
  It means "the hold was removed", never "the customer became active". The
  release runs in ONE transaction that takes the Customer row lock BEFORE the
  reactivation site (whose own atomic nests as a savepoint), so the result is
  truthfully this call's: a concurrent release blocks, then finds the hold
  gone and writes nothing.

No record for a no-op (already held / already active), a refusal or a failed
or rolled-back operation — those stay in the operational log, and there is no
attempt/refusal/failure action; the two names are never used for an
unsuccessful request. The ledger entry commits with its state change or not at
all: ``apps.platform.audit.ledger.record`` is called inside the mutation's own
transaction. ``customer.suspended`` / ``customer.reactivated`` are unchanged.
"""
import logging

from django.db import transaction

from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.gating.services.stop_signal_service import announced_balance
from apps.platform.audit.actors import operator_actor
from apps.platform.audit.ledger import record as audit_record
from apps.platform.customers.hooks import notify_if_a_seat
from apps.platform.customers.models import (
    CUSTOMER_STATUS_ACTIVE, CUSTOMER_STATUS_SUSPENDED, Customer)
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import CustomerSuspended
from core.exceptions import UBBError
from core.vocabulary import (
    AUDIT_ACTION_CUSTOMER_MANUAL_HOLD_RELEASED,
    AUDIT_ACTION_CUSTOMER_MANUAL_HOLD_SET,
    AUDIT_RESOURCE_TYPE_CUSTOMER,
)

logger = logging.getLogger(__name__)

MANUAL_HOLD_REASON = LiveCounter.MANUAL_HOLD_REASON


class Outcome(str):
    """What one operation came to: one of the five kinds below — it compares
    and prints as that word (``outcome == HELD``), so a caller that only asks
    which kind needs nothing more — carrying, for a hand-over, the system
    ``cause`` the customer remains suspended for, as the service read it after
    the reactivation site's own transaction, so a caller reports the cause
    without asking the database again."""

    cause: str

    def __new__(cls, kind, cause=""):
        outcome = super().__new__(cls, kind)
        outcome.cause = cause
        return outcome


#: The kinds of outcome.
HELD = "held"
ALREADY_HELD = "already_held"
RELEASED = "released"
ALREADY_ACTIVE = "already_active"
#: A release that removed the manual cause while a system condition still
#: stands (a payment failure, a stop line still open under ``enforcing``, a
#: wallet past its floor): the customer stays suspended, now for that cause,
#: which its own recovery lifts. The hold is gone — this is not a failure — and
#: nothing was announced.
HANDED_OVER = "handed_over"


#: A refused or failed operation, as logged.
REFUSED = "refused"
FAILED = "failed"


class ManualHoldRefused(UBBError):
    """The operation would act on something that is not a manual hold: a
    customer that does not exist or is deleted, one suspended for a system
    cause, or one in a state a hold does not apply to. Nothing was written."""


class ManualHoldFailed(UBBError):
    """A release the reactivation site did not carry out although the customer
    is still under a manual hold — an internal failure there, which it logs as
    ``live_counter.unsuspend_failed``. Nothing was written; it can be retried."""


def _log(customer_id, outcome, operator, *, tenant_id=None, detail=""):
    data = {"customer_id": str(customer_id), "outcome": outcome,
            "operator": str(operator)}
    if tenant_id is not None:
        data["tenant_id"] = str(tenant_id)
    if detail:
        data["detail"] = detail
    log = logger.warning if outcome in (REFUSED, FAILED) else logger.info
    log("customer.manual_hold", extra={"data": data})


def _refuse(customer_id, operator, message, *, tenant_id=None):
    _log(customer_id, REFUSED, operator, tenant_id=tenant_id, detail=message)
    raise ManualHoldRefused(message)


def _is_held(customer):
    return (customer.status == CUSTOMER_STATUS_SUSPENDED
            and customer.suspension_reason == MANUAL_HOLD_REASON)


def _audit(action, customer, operator, outcome):
    """The durable governance record of a SUCCESSFUL hold or release (PLAN §7
    item 42): under the operator actor, on the customer record, carrying the
    resulting status and suspension reason so a reader can tell a release
    that reactivated from one a system cause took over. Called inside the
    transaction that holds the state change, so it commits with it or not at
    all."""
    audit_record(
        action=action, tenant_id=customer.tenant_id,
        resource_type=AUDIT_RESOURCE_TYPE_CUSTOMER, resource_id=customer.id,
        metadata={"customer_id": str(customer.id),
                  "external_id": customer.external_id,
                  "operator": str(operator),
                  "outcome": str(outcome),
                  "resulting_status": customer.status,
                  "resulting_suspension_reason": customer.suspension_reason},
        actor=operator_actor(operator))


def place_manual_hold(customer_id, *, operator):
    """Suspend one live, active customer under a manual hold. Answers
    ``HELD`` or ``ALREADY_HELD`` (an ``Outcome``); raises
    ``ManualHoldRefused`` otherwise."""
    with transaction.atomic():
        customer = (Customer.objects.select_for_update(of=("self",))
                    .select_related("tenant").filter(id=customer_id).first())
        if customer is None:
            _refuse(customer_id, operator, f"no live customer {customer_id}")
        if _is_held(customer):
            outcome = ALREADY_HELD
        elif customer.status == CUSTOMER_STATUS_SUSPENDED:
            _refuse(customer.id, operator,
                    f"customer {customer.id} is suspended for "
                    f"{customer.suspension_reason!r}, a cause its own recovery owns; "
                    "a manual hold never overwrites it", tenant_id=customer.tenant_id)
        elif customer.status != CUSTOMER_STATUS_ACTIVE:
            _refuse(customer.id, operator,
                    f"customer {customer.id} is {customer.status!r}; only an active "
                    "customer can be held", tenant_id=customer.tenant_id)
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
            # The durable record of the hold, in this same transaction: only
            # an actually established hold writes one (item 42).
            _audit(AUDIT_ACTION_CUSTOMER_MANUAL_HOLD_SET, customer, operator, HELD)
    _log(customer.id, outcome, operator, tenant_id=customer.tenant_id)
    return Outcome(outcome)


def release_manual_hold(customer_id, *, operator):
    """Remove one customer's manual hold through the one reactivation site.
    Answers ``RELEASED`` (active again), ``ALREADY_ACTIVE`` or ``HANDED_OVER``
    (an ``Outcome``: the hold is gone and its ``cause``, a standing system
    cause, keeps the customer suspended); raises
    ``ManualHoldRefused`` for anything that is not a manual hold, and
    ``ManualHoldFailed`` when the reactivation site did not carry it out."""
    def refuse_deleted(customer):
        _refuse(customer.id, operator,
                f"no live customer {customer.id}: it was deleted while its "
                "release was asked", tenant_id=customer.tenant_id)

    def no_op_or_refusal(customer):
        """What a release can do with ``customer`` short of releasing it: the
        no-op (``ALREADY_ACTIVE``), or a refusal, raised. ``None`` means a
        manual hold stands to be released. Asked before the lock, so a plain
        refusal costs no lock, and again UNDER it, so the decision is this
        call's."""
        if customer is None:
            _refuse(customer_id, operator, f"no live customer {customer_id}")
        tenant_id = customer.tenant_id
        if customer.deleted_at is not None:
            refuse_deleted(customer)
        if customer.status == CUSTOMER_STATUS_ACTIVE:
            return ALREADY_ACTIVE
        if customer.status != CUSTOMER_STATUS_SUSPENDED:
            _refuse(customer.id, operator,
                    f"customer {customer.id} is {customer.status!r}; there is no hold "
                    "to release", tenant_id=tenant_id)
        if not _is_held(customer):
            _refuse(customer.id, operator,
                    f"customer {customer.id} is suspended for "
                    f"{customer.suspension_reason!r}, which is not a manual hold; "
                    "its own recovery owns it", tenant_id=tenant_id)
        return None

    def answered(customer, no_op):
        _log(customer.id, no_op, operator, tenant_id=customer.tenant_id)
        return Outcome(no_op)

    customer = Customer.objects.filter(id=customer_id).first()
    no_op = no_op_or_refusal(customer)
    tenant_id = customer.tenant_id
    if no_op is not None:
        return answered(customer, no_op)

    # ONE TRANSACTION, THE CUSTOMER ROW LOCK FIRST (PLAN §7 item 42): the
    # reactivation site's own atomic nests as a savepoint under this lock, so
    # what it leaves is this call's doing — a concurrent release blocks here,
    # then finds the hold already gone and writes nothing — and the audit
    # record of a removed hold commits with the state change or not at all. A
    # failure the site swallowed rolls back its savepoint only; the hold
    # stands and no record is written.
    with transaction.atomic():
        customer = (Customer.all_objects.select_for_update(of=("self",))
                    .filter(id=customer_id).first())
        no_op = no_op_or_refusal(customer)
        if no_op is not None:
            return answered(customer, no_op)
        moved = LiveCounter.clear_manual_hold(customer.id)
        customer.refresh_from_db()
        if not moved and customer.deleted_at is not None:
            refuse_deleted(customer)
        cause = detail = ""
        if moved:
            outcome = RELEASED
        elif (customer.status == CUSTOMER_STATUS_SUSPENDED
              and customer.suspension_reason != MANUAL_HOLD_REASON):
            # Only the reactivation site changes a suspended customer's reason —
            # every suspend path acts on an active one — and it ran under this
            # lock, so a system cause here is the one it handed the hold over
            # to: the hold is gone, and that cause's recovery owns the rest.
            outcome, cause = HANDED_OVER, customer.suspension_reason
            detail = f"still suspended for {cause!r}"
        elif _is_held(customer):
            message = (f"the reactivation site did not release customer {customer.id} "
                       "(see live_counter.unsuspend_failed); it is still held, and the "
                       "release can be retried")
            _log(customer.id, FAILED, operator, tenant_id=tenant_id, detail=message)
            raise ManualHoldFailed(message)
        else:
            _refuse(customer.id, operator,
                    f"customer {customer.id} was not released: it is now "
                    f"{customer.status!r} for {customer.suspension_reason!r}",
                    tenant_id=tenant_id)
        # THIS call removed the hold (released or handed over): the durable
        # record, carrying what the customer is now (item 42).
        _audit(AUDIT_ACTION_CUSTOMER_MANUAL_HOLD_RELEASED, customer, operator, outcome)
    _log(customer.id, outcome, operator, tenant_id=tenant_id, detail=detail)
    return Outcome(outcome, cause)
