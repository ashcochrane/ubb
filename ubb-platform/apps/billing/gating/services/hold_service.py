"""Accept-time hold for the async ingest path (estimate-hold-settle).

Task 4: HoldService is the money mirror for the async ingestion feature — the
ONLY place an ESTIMATED cost is atomically reserved before the async worker
actually appends/records the real usage event (Tasks 5/6).

It reuses the Tier-2 live-ledger keys/semantics wholesale
(live_ledger_service.py): the SAME owner-keyed prepaid balance
(``ubb:livebal:{owner}``) / postpaid month-to-date spend
(``ubb:livespend:{owner}:{YYYY-MM}``) counter and cooperative customer-wide
stop flag (``ubb:stop:{owner}``) that ``record_usage_debit`` maintains
synchronously on the accept-time path. There is only ONE live counter per
owner — a hold taken here is immediately visible to (and races fairly
against) the synchronous path, and vice versa.

One-rule (#37): the acquire ALWAYS holds, against the wallet only. The old
accept-time per-unit cap lane (its per-unit counter key family and its
check-then-increment reject branch) retired unreplaced — task limits are
provider-cost (COGS) denominated and exact provider cost exists only at
settle, so unit-limit detection lives there (UsageService.settle_raw), not
here. Nothing on this path ever rejects an item.

Per item, ONE Lua eval (``_ACQUIRE``), pipelined across the whole batch so an
N-item batch is still N atomic server-side ops:

  1. prepaid: seed-if-absent (from the durable wallet balance) then DECRBY
     the estimate — mirrors ``_SEED_AND_DECR``.
     postpaid: INCRBY the estimate onto the live spend counter — mirrors
     ``_SPEND_INCR``. EXCEPT when the item's ``effective_at`` is backdated to
     a PRIOR calendar month (I9 parity with ``record_usage_debit``): the
     spend move is skipped for that one item so a legitimate backfill cannot
     uncorrectably inflate the CURRENT month's live spend (the MAX-merge
     reconcile only ever raises).
  2. Back in Python: the owner's crossing threshold is resolved ONCE per
     ``acquire()`` call (``LiveLedgerService._threshold`` — not per item, to
     avoid an ORM query per item) and every held item's post-hold value is
     compared against it in Python. A crossing sets the cooperative stop
     flag. This NEVER rejects or rolls back the hold that crossed it (I3 —
     cooperative, not transactional); the item is still held. This is the
     arrival-time fast trigger of the signal suite.

``settle``/``release`` credit back (or further debit) through
``LiveLedgerService.credit`` — the same MIN-merge-safe site every other
credit hook (top-up, refund-reversal, manual credit) uses.

Fails OPEN on any error (Redis down, etc): every item is held, no stop —
identical contract to ``record_usage_debit`` ("NEVER raises ... the durable
start-gate remains the backstop").
"""
import logging

from apps.platform.tenants.flags import enforcement_on
from apps.billing.gating.services.live_ledger_service import (
    LiveLedgerService,
    LEDGER_TTL_SECONDS,
    _livebal_key,
    _livespend_key,
    _month_label_bounds,
    _same_month,
    _client,
)

logger = logging.getLogger("ubb.billing")

# KEYS[1] = balance/spend key (livebal for prepaid, livespend for postpaid)
# ARGV[1] = seed (prepaid: durable wallet balance; postpaid: unused, pass 0)
# ARGV[2] = estimate_micros — ALWAYS POSITIVE. ARGV[4] (not the sign of this
#           value) selects the balance-move direction.
# ARGV[3] = ttl seconds — refreshed (EXPIRE) on every key this script touches.
# ARGV[4] = '1' => postpaid (INCRBY the spend counter, mirrors _SPEND_INCR);
#           '0' => prepaid (seed-if-absent then DECRBY, mirrors _SEED_AND_DECR).
# ARGV[5] = '1' => skip the balance/spend move entirely (I9 parity: a
#           postpaid item backdated to a PRIOR month must not inflate THIS
#           month's live spend counter — mirrors record_usage_debit's
#           _same_month guard). Prepaid callers always pass '0' here (livebal
#           is not month-scoped — a backfill still legitimately reduces
#           spendable balance). When skipped, returns the CURRENT (untouched)
#           KEYS[1] value (0 if absent) so the caller's crossing check still
#           sees whatever a SIBLING item in the same batch already moved it to.
# Returns the post-hold counter value. Always holds — nothing here rejects.
_ACQUIRE = """
if tonumber(ARGV[5]) == 1 then
    local cur = redis.call('GET', KEYS[1])
    return cur and tonumber(cur) or 0
end
local v
if tonumber(ARGV[4]) == 1 then
    v = redis.call('INCRBY', KEYS[1], ARGV[2])
else
    if redis.call('EXISTS', KEYS[1]) == 0 then
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
    end
    v = redis.call('DECRBY', KEYS[1], ARGV[2])
end
redis.call('EXPIRE', KEYS[1], ARGV[3])
return v
"""


def _held_verdict() -> dict:
    """A fresh held/not-stopped verdict dict (never share a single mutable
    instance across items — callers may mutate their own copy)."""
    return {"held": True, "stop": False, "stop_reason": None, "stop_scope": None}


class HoldService:
    @staticmethod
    def acquire(owner_id, tenant, items):
        """Atomically reserve an estimated cost for each item — always holds.

        items: [{"estimate_micros": int, "effective_at": datetime|None}]

        effective_at (I9 parity with record_usage_debit): for a POSTPAID
        tenant, an item backdated to a PRIOR calendar month does not move the
        livespend counter (a legitimate backfill must not inflate THIS
        month's spend uncorrectably — the reconcile MAX-merge only ever
        RAISES, so an inflated value could never self-correct). PREPAID is
        untouched: livebal is not month-scoped, so a backfill still
        legitimately reduces the spendable balance.

        Returns one verdict dict per item, in the SAME order as `items`:
        {"held": True, "stop": bool, "stop_reason": str|None,
         "stop_scope": str|None}. One-rule (#37): no item is ever rejected —
        the stop fields are the cooperative customer-wide verdict, and a
        crossing sets the stop flag without rolling back the hold that
        crossed it.

        Disabled (enforcement_mode == "off"): every item is held, unstopped
        — a cheap no-op passthrough, matching every other Tier-2 gate (the
        durable start-gate, e.g. RiskService, remains the real backstop).

        NEVER raises: any error (Redis unreachable, etc.) fails OPEN — every
        item is held, unstopped — identical fail-open contract to
        LiveLedgerService.record_usage_debit.
        """
        if not enforcement_on(tenant):
            return [_held_verdict() for _ in items]

        from django.utils import timezone
        from apps.billing.queries import get_customer_balance

        postpaid = tenant.billing_mode == "postpaid"
        now = timezone.now()
        try:
            if postpaid:
                label, _, _ = _month_label_bounds(now)
                bal_key = _livespend_key(owner_id, label)
                seed = 0
            else:
                bal_key = _livebal_key(owner_id)
                seed = int(get_customer_balance(owner_id))

            client = _client()
            pipe = client.pipeline()
            for it in items:
                skip_balance = postpaid and not _same_month(it.get("effective_at"), now)
                pipe.eval(
                    _ACQUIRE, 1, bal_key,
                    seed, int(it["estimate_micros"]), LEDGER_TTL_SECONDS,
                    1 if postpaid else 0,
                    1 if skip_balance else 0,
                )
            raw_results = pipe.execute()

            # Threshold-crossing bound resolved ONCE per owner for this whole
            # batch (not per item — that would be an ORM query per item; see
            # LiveLedgerService._threshold) and compared in plain Python below.
            mode = "postpaid" if postpaid else "prepaid"
            threshold = LiveLedgerService._threshold(mode, owner_id, tenant)
            out = []
            crossed = False
            crossing_value = 0
            for post in raw_results:
                value = int(post)
                if threshold is not None:
                    over = value >= threshold if mode == "postpaid" else value < threshold
                    if over and not crossed:
                        crossed = True
                        crossing_value = value
                out.append(_held_verdict())

            if crossed:
                from apps.platform.tasks.reasons import CUSTOMER_WIDE_STOP
                LiveLedgerService._set_stop(
                    owner_id, CUSTOMER_WIDE_STOP, tenant=tenant,
                    balance_micros=crossing_value if mode == "prepaid" else 0)
            verdict = LiveLedgerService.read_stop(owner_id, tenant)
            for o in out:
                o.update(verdict)
            return out
        except Exception:
            # A failure THIS late (e.g. in _threshold's ORM lookup, _set_stop,
            # or read_stop) already ran the Redis pipe -- money already moved
            # -- so this fail-open only means a crossing here goes UNDETECTED
            # for one batch; the next acquire()/record_usage_debit call
            # re-evaluates the now-updated counter and catches it then (a
            # one-batch stop-flag delay, not a lost debit).
            logger.warning("hold_service.acquire_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return [_held_verdict() for _ in items]  # fail-open

    @staticmethod
    def settle(owner_id, tenant, delta_micros, *, effective_at=None):
        """delta = estimate − exact. Positive => credit back the over-hold
        (the actual cost came in lower than the estimate); negative =>
        debit further (an underestimate).

        PREPAID: routes the balance-side adjustment through
        LiveLedgerService.credit — the SAME MIN-merge-safe site every other
        credit hook (top-up, refund-reversal, manual credit) uses, so a
        fast-path drop here fails the SAME safe direction (over-restrictive,
        never under-restrictive) as every other credit path.

        POSTPAID: credit() is a deliberate no-op for postpaid ("no spendable
        balance"), so settle applies the delta DIRECTLY to the CURRENT
        month's livespend counter (INCRBY −delta: a positive over-hold delta
        LOWERS the spend, a negative delta raises it further). Without this,
        every over-estimate would permanently inflate the counter — the
        reconcile_postpaid MAX-merge only ever RAISES, so it could never
        self-correct, and budget caps would fire increasingly early for the
        rest of the month.

        Prior-month settle guard (I9 parity): `effective_at` is the settled
        event's effective instant (optional; None == "treat as current
        month", so every pre-existing caller that omits it is unaffected). For
        POSTPAID, when `effective_at` falls in a PRIOR calendar month relative
        to settle wall-clock time, the livespend adjustment is skipped
        entirely — HoldService.acquire already skipped this event's hold-time
        move for the same reason (see its `skip_balance` guard), so applying
        a delta here would adjust a counter this event never touched.
        PREPAID is untouched (livebal is not month-scoped — a backfill still
        legitimately reduces spendable balance).

        Month-rollover window (postpaid, same-month case): a hold acquired in
        month M that settles in month M+1 adjusts M+1's livespend key (acquire
        inflated M's). The exposure is only the few seconds of ingest latency
        straddling the rollover instant, and the MAX-merge reconcile toward
        each month's durable billed total re-corrects both months' counters
        within one reconcile cycle.

        Best-effort everywhere; NEVER raises. Does NOT clear stop flags —
        recovery stays with reconcile/credit(), matching existing semantics.
        """
        delta_micros = int(delta_micros)
        if delta_micros:
            if tenant.billing_mode == "postpaid":
                if enforcement_on(tenant):
                    from django.utils import timezone
                    now = timezone.now()
                    if _same_month(effective_at, now):
                        try:
                            label, _, _ = _month_label_bounds(now)
                            key = _livespend_key(owner_id, label)
                            pipe = _client().pipeline()
                            pipe.incrby(key, -delta_micros)
                            pipe.expire(key, LEDGER_TTL_SECONDS)
                            pipe.execute()
                        except Exception:
                            logger.warning("hold_service.settle_failed",
                                           extra={"data": {"owner_id": str(owner_id)}})
            else:
                LiveLedgerService.credit(owner_id, tenant, delta_micros)

    @staticmethod
    def release(owner_id, tenant, estimate_micros, *, effective_at=None):
        """Full credit-back of a hold — duplicate ingest, failed append, or
        any path that must UNDO an acquire() entirely. Equivalent to
        settle(delta_micros=estimate_micros). `effective_at` forwards to
        settle()'s prior-month guard — see its docstring."""
        HoldService.settle(owner_id, tenant, estimate_micros, effective_at=effective_at)
