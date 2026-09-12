"""Admission control — the kernel's bound on how fast NEW top-level work may
enter, and the customer's standing beside it, consulted by the composition
layer for EVERY start (#462, slice 6 §1, §6; #154 §3.4; #141 §4.5).

WHY THE KERNEL, AND WHY EVERY TENANT. A bound on how fast work enters is a
property of the work's admission, not of anybody's money: it says nothing
about supplier cost and is never spend protection. The registry's four
control families put it in the kernel (§1), and #141 §4.5 lists the
customer's standing — suspended or closed — among the refusals a tenant that
does not bill through UBB still gets. Until #462 both ran inside billing's
money-shaped verdict, which the composition layer asks only where the tenant
has a wallet, so such a tenant had neither. The customer is a kernel model,
so the standing check moved with the bound in one ticket rather than leaving
that tenant in a half-state between two commits.

WHAT IS BOUNDED (#154 §3.4). New top-level starts, per seat, in a fixed
window of one minute — the tenant's `max_task_starts_per_minute`. A replay
never reaches here (the composition layer answers it from the claim first);
contained work started inside admitted work consumes nothing (an active unit
must not be blocked because its own decomposition crossed the rate); a usage
report is always accepted; a close is never subject to it (the close half of
Pin 7, §22); configuration is never subject to it.

THE ORDER, AND THE ONE REORDERING IT MAKES. The rate is asked first, then the
standing. A customer both stopped and over the rate is told about the rate
first — the answer that changes on its own within a minute — and a caller
that backs off then meets the stop. The old throttle asked standing first;
§6 states and accepts the change. Its consequence is that a start refused
for standing has still entered the window, exactly as a start the old
throttle admitted and the wallet then refused had.

THE STORE. The Django cache — Redis — as the old throttle used, keyed on the
seat's id, which is what lets the kernel own the window without asking
billing who the billing owner is. Two keys per seat, both expiring with the
window: the count of starts admitted, and the instant the window ends, so a
refusal can say when to come back. Fail OPEN when the store is away, loudly:
the money is still guarded by the durable checks that follow, and a store
outage must not stop work entering.

THE WORDS. The three this module produces — the rate's, and the two
standings' — are the registry's `affordability_reason` values, bound from
`core.vocabulary` like the two start-shape refusals in `services.py`. A
suspension is the durable form of the customer-wide stop, so a suspended
customer is refused in the registry's word for a stop in force; the kernel
does not know, and must not ask billing, which line opened it. For a tenant
with a wallet the composition layer asks the money verdict to WORD the
refusal this module has already made (`RiskService.standing_word`: the
pool's word, or the wallet's) — so the refusal is the kernel's for every
tenant, the standing is walked once, here, and the word names the line
wherever there is one to name.

Nothing here reads or writes a row of its own.
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.platform.customers.models import (
    CUSTOMER_STATUS_CLOSED, CUSTOMER_STATUS_SUSPENDED)
from apps.platform.work.services import StartRefused
from core.vocabulary import (
    AFFORDABILITY_REASON_ACCOUNT_CLOSED,
    AFFORDABILITY_REASON_CUSTOMER_STOPPED,
    AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED)

logger = logging.getLogger(__name__)

#: The fixed window, in seconds — the setting's own unit of time.
WINDOW_SECONDS = 60

#: THE SCOPE KEY, PINNED AND EXPOSED (#154 §3.4): the window is keyed per
#: seat — the customer named on the start — never per tenant and never per
#: billing owner, and the rejection says so rather than varying between
#: endpoints.
SCOPE = "seat"


@dataclass(frozen=True, slots=True)
class AdmissionWindow:
    """What the window says after a start was counted, or refused: the
    retry information #154 §3.4 keeps verbatim."""

    #: The tenant's bound.
    limit: int
    #: How many more top-level starts this window admits; 0 on a refusal.
    remaining: int
    #: The instant the window ends and a fresh one begins.
    ends_at: datetime
    #: Whole seconds until then, at least one — a `Retry-After` of zero
    #: tells a caller to try again now.
    retry_after_seconds: int


class AdmissionRefused(StartRefused):
    """A start the kernel's admission check refused, carrying the reason and
    — for the rate's refusal only — the window a caller may retry after;
    for a standing refusal only, the row whose standing refused (the seat,
    or the business funding it), which is what lets a product that holds
    stop lines word the refusal without walking the standing again.
    `window` is None for a standing refusal; `who` is None for the rate's."""

    def __init__(self, reason, detail, *, window=None, who=None):
        super().__init__(reason, detail)
        self.window = window
        self.who = who


def window_keys(customer_id):
    """The store's two keys for one seat's window: the count of admitted
    starts, and the instant the window ends."""
    return (f"admission:{customer_id}:starts",
            f"admission:{customer_id}:window_ends_at")


def admit(tenant, customer, *, contained):
    """Admit a start for ``customer`` under ``tenant``, or raise
    `AdmissionRefused`.

    A top-level start (``contained`` False) is counted against the seat's
    window first and refused with the retry information once the window is
    full; contained work is never counted. Then the customer's standing —
    suspended or closed, for the seat and for the business funding a pooled
    seat — refuses in the registry's word. Returns the window after
    counting, or None where nothing was counted (contained work, no bound
    declared, the store away).
    """
    window = None if contained else _count_a_start(tenant, customer)
    reason, who = standing_refusal(customer)
    if reason is not None:
        raise AdmissionRefused(
            reason,
            f"{'this customer' if who is customer else 'the business funding this seat'} "
            f"is {who.status}", who=who)
    return window


def standing_refusal(customer):
    """The registry's word for a customer that may not begin work, and the
    row that says so — the seat, or the business funding a pooled seat —
    or (None, None) where both stand. The seat is asked first, then the
    owner, in the order the money verdict has always asked them; the
    verdict asks THIS walk now rather than keeping a second one, and words
    a suspension by the line holding it, which only it can name."""
    owner = customer.resolve_billing_owner()
    for who in ((customer,) if owner.id == customer.id else (customer, owner)):
        if who.status == CUSTOMER_STATUS_SUSPENDED:
            return AFFORDABILITY_REASON_CUSTOMER_STOPPED, who
        if who.status == CUSTOMER_STATUS_CLOSED:
            return AFFORDABILITY_REASON_ACCOUNT_CLOSED, who
    return None, None


def _count_a_start(tenant, customer):
    """Count one top-level start against the seat's window and answer the
    window, or raise the rate's refusal once the window is full. None where
    the tenant declares no bound or the store is away. A refused start is
    not counted — the count is of starts the bound admitted, as the old
    throttle counted, so hammering a full window does not deepen it."""
    bound = tenant.max_task_starts_per_minute
    if not bound:
        return None
    starts_key, ends_key = window_keys(customer.id)
    now = timezone.now()
    try:
        counted = cache.get(starts_key, 0)
        if counted >= bound:
            full = _window(bound, counted, _window_ends_at(ends_key, now), now)
            raise AdmissionRefused(
                AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED,
                f"this customer has begun as much new work as its tenant's "
                f"configuration admits in one minute ({bound}); the window ends at "
                f"{full.ends_at.isoformat()}",
                window=full)
        # The end of the window is recorded before the count so it can never
        # outlive it: on the window's last moment a refusal may read no end
        # and answer a whole window's wait, which errs the safe way, where an
        # end outliving its count would hand the next window a moment already
        # past and a `Retry-After` of one for a full minute.
        cache.add(ends_key, (now + timedelta(seconds=WINDOW_SECONDS)).timestamp(),
                  timeout=WINDOW_SECONDS)
        try:
            counted = cache.incr(starts_key)
        except ValueError:
            cache.set(starts_key, 1, timeout=WINDOW_SECONDS)
            counted = 1
        ends_at = _window_ends_at(ends_key, now)
    except AdmissionRefused:
        raise
    except Exception:
        logger.warning("work.admission_store_unavailable",
                       extra={"data": {"tenant_id": str(tenant.id),
                                       "customer_id": str(customer.id)}},
                       exc_info=True)
        return None
    return _window(bound, counted, ends_at, now)


def _window(bound, counted, ends_at, now):
    return AdmissionWindow(limit=bound, remaining=max(bound - counted, 0),
                           ends_at=ends_at,
                           retry_after_seconds=_seconds_until(ends_at, now))


def _window_ends_at(ends_key, now):
    recorded = cache.get(ends_key)
    if recorded is None:
        return now + timedelta(seconds=WINDOW_SECONDS)
    return datetime.fromtimestamp(float(recorded), tz=now.tzinfo)


def _seconds_until(ends_at, now):
    return max(1, math.ceil((ends_at - now).total_seconds()))


