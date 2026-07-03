"""Accept-time atomic gate for the async ingest path (estimate-hold-settle).

Task 4: HoldService is the money gate for the async ingestion feature — the
ONLY place an ESTIMATED cost is atomically checked-and-reserved before the
async worker actually appends/records the real usage event (Tasks 5/6).

It reuses the Tier-2 live-ledger keys/semantics wholesale
(live_ledger_service.py): the SAME owner-keyed prepaid balance
(``ubb:livebal:{owner}``) / postpaid month-to-date spend
(``ubb:livespend:{owner}:{YYYY-MM}``) counter and cooperative customer-wide
stop flag (``ubb:stop:{owner}``) that ``record_usage_debit`` maintains
synchronously on the accept-time path. There is only ONE live counter per
owner — a hold taken here is immediately visible to (and races fairly
against) the synchronous path, and vice versa.

Per item, ONE Lua eval (``_ACQUIRE``), pipelined across the whole batch so an
N-item batch is still N atomic server-side ops:

  1. run-cap check-then-increment FIRST. A rejection returns immediately
     WITHOUT touching the balance/spend key at all (no partial hold).
  2. prepaid: seed-if-absent (from the durable wallet balance) then DECRBY
     the estimate — mirrors ``_SEED_AND_DECR``.
     postpaid: INCRBY the estimate onto the live spend counter — mirrors
     ``_SPEND_INCR``.
  3. Back in Python: ``LiveLedgerService._crossed`` threshold-crossing
     detection sets the cooperative stop flag. This NEVER rejects or rolls
     back the hold that crossed it (I3 — cooperative, not transactional);
     the item is still held.

``settle``/``release`` credit back (or further debit) through
``LiveLedgerService.credit`` — the same MIN-merge-safe site every other
credit hook (top-up, refund-reversal, manual credit) uses — and adjust the
per-run cost counter (``ubb:runcost:{run_id}``) by the inverse delta.

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
    _client,
)

logger = logging.getLogger("ubb.billing")

# Sentinel KEYS[2] for an item that carries no run_id. The script never
# touches KEYS[2] unless ARGV[4] (cap) >= 0, and the caller only ever passes
# a non-negative cap when a real run_id accompanies it (see `has_cap` below)
# — so this key name is never actually read or written. It exists purely to
# satisfy EVAL's declared numkeys=2 contract.
_NO_RUN_SENTINEL = "ubb:runcost:_none"

# KEYS[1] = balance/spend key (livebal for prepaid, livespend for postpaid)
# KEYS[2] = per-run cost-cap counter (ubb:runcost:{run_id}), or the sentinel
#           above when there is no run_id for this item.
# ARGV[1] = seed (prepaid: durable wallet balance; postpaid: unused, pass 0)
# ARGV[2] = estimate_micros — ALWAYS POSITIVE. Used for BOTH the run-cap
#           increment and the balance move; ARGV[6] (not the sign of this
#           value) selects the balance-move direction. This is the fix for
#           the sign-handling trap called out in the task brief: an earlier
#           draft modeled the postpaid INCR as "DECRBY of a negative
#           estimate" and reused that SAME signed value for the run-cap
#           increment — which would have silently DECREMENTED the run-cost
#           counter for postpaid runs instead of incrementing it. Keeping
#           the estimate unsigned and branching explicitly on ARGV[6] avoids
#           that trap entirely (do not "simplify" this back).
# ARGV[3] = ttl seconds — refreshed (EXPIRE) on every key this script touches.
# ARGV[4] = run_cap_micros, or -1 when there is no run-level cap to enforce.
# ARGV[5] = run_seed_micros (seed for a brand-new runcost key).
# ARGV[6] = '1' => postpaid (INCRBY the spend counter, mirrors _SPEND_INCR);
#           '0' => prepaid (seed-if-absent then DECRBY, mirrors _SEED_AND_DECR).
# Returns {held(0/1), rejected(0/1), post_value}. A rejection returns
# {0, 1, 0} and is guaranteed to have touched NOTHING on KEYS[1].
_ACQUIRE = """
local cap = tonumber(ARGV[4])
if cap >= 0 then
    if redis.call('EXISTS', KEYS[2]) == 0 then
        redis.call('SET', KEYS[2], ARGV[5], 'EX', ARGV[3])
    end
    local newrun = tonumber(redis.call('GET', KEYS[2])) + tonumber(ARGV[2])
    if newrun > cap then
        redis.call('EXPIRE', KEYS[2], ARGV[3])
        return {0, 1, 0}
    end
    redis.call('SET', KEYS[2], newrun, 'EX', ARGV[3])
end
local v
if tonumber(ARGV[6]) == 1 then
    v = redis.call('INCRBY', KEYS[1], ARGV[2])
else
    if redis.call('EXISTS', KEYS[1]) == 0 then
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
    end
    v = redis.call('DECRBY', KEYS[1], ARGV[2])
end
redis.call('EXPIRE', KEYS[1], ARGV[3])
return {1, 0, v}
"""

# settle()/release() credit-back (or further debit) of the per-run cost
# counter: applies ONLY if the counter already exists — i.e. the run HAD a
# cap at acquire time, so _ACQUIRE actually created it. Mirrors
# _CREDIT_IF_PRESENT so a run that never had a cap never gets a stray,
# TTL-less counter created here on settle. ARGV[1] may be negative (a
# further debit — the actual cost exceeded the estimate). Refreshes TTL.
# KEYS[1]=runcost key; ARGV[1]=delta (negated by the caller); ARGV[2]=ttl.
_RUNCOST_CREDIT_IF_PRESENT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    local v = redis.call('INCRBY', KEYS[1], ARGV[1])
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return v
end
return nil
"""


def _runcost_key(run_id) -> str:
    return f"ubb:runcost:{run_id}"


def _noop_hold() -> dict:
    """A fresh held/not-stopped verdict dict (never share a single mutable
    instance across items — callers may mutate their own copy)."""
    return {"held": True, "rejected": False, "reason": None,
            "stop": False, "stop_reason": None, "stop_scope": None}


def _reject_hold() -> dict:
    return {"held": False, "rejected": True, "reason": "cost_limit_exceeded",
            "stop": False, "stop_reason": None, "stop_scope": None}


class HoldService:
    @staticmethod
    def acquire(owner_id, tenant, items):
        """Atomically check-and-reserve an estimated cost for each item.

        items: [{"estimate_micros": int, "run_id": str|None,
                 "run_cap_micros": int|None, "run_seed_micros": int}]

        Returns one verdict dict per item, in the SAME order as `items`:
        {"held": bool, "rejected": bool, "reason": str|None, "stop": bool,
         "stop_reason": str|None, "stop_scope": str|None}.

        Disabled (enforcement_mode == "off"): every item is held, unstopped
        — a cheap no-op passthrough, matching every other Tier-2 gate (the
        durable start-gate, e.g. RiskService, remains the real backstop).

        NEVER raises: any error (Redis unreachable, etc.) fails OPEN — every
        item is held, unstopped — identical fail-open contract to
        LiveLedgerService.record_usage_debit.
        """
        if not enforcement_on(tenant):
            return [_noop_hold() for _ in items]

        from django.utils import timezone
        from apps.billing.queries import get_customer_balance

        postpaid = tenant.billing_mode == "postpaid"
        try:
            if postpaid:
                label, _, _ = _month_label_bounds(timezone.now())
                bal_key = _livespend_key(owner_id, label)
                seed = 0
            else:
                bal_key = _livebal_key(owner_id)
                seed = int(get_customer_balance(owner_id))

            client = _client()
            pipe = client.pipeline()
            for it in items:
                run_id = it.get("run_id")
                cap = it.get("run_cap_micros")
                has_cap = bool(run_id) and cap is not None
                pipe.eval(
                    _ACQUIRE, 2,
                    bal_key, _runcost_key(run_id) if run_id else _NO_RUN_SENTINEL,
                    seed, int(it["estimate_micros"]), LEDGER_TTL_SECONDS,
                    int(cap) if has_cap else -1,
                    int(it.get("run_seed_micros") or 0),
                    1 if postpaid else 0,
                )
            raw_results = pipe.execute()

            mode = "postpaid" if postpaid else "prepaid"
            out = []
            crossed = False
            for held, rejected, post in raw_results:
                if rejected:
                    out.append(_reject_hold())
                    continue
                value = int(post)
                if LiveLedgerService._crossed(mode, value, owner_id, tenant):
                    crossed = True
                out.append(_noop_hold())

            if crossed:
                from apps.platform.runs.reasons import CUSTOMER_WIDE_STOP
                LiveLedgerService._set_stop(owner_id, CUSTOMER_WIDE_STOP)
            verdict = LiveLedgerService.read_stop(owner_id, tenant)
            for o in out:
                if o["held"]:
                    o.update(verdict)
            return out
        except Exception:
            logger.warning("hold_service.acquire_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return [_noop_hold() for _ in items]  # fail-open

    @staticmethod
    def settle(owner_id, tenant, run_id, delta_micros):
        """delta = estimate − exact. Positive => credit back the over-hold
        (the actual cost came in lower than the estimate); negative =>
        debit further (an underestimate).

        Routes the balance-side adjustment through LiveLedgerService.credit
        — the SAME MIN-merge-safe site every other credit hook (top-up,
        refund-reversal, manual credit) uses, so a fast-path drop here fails
        the SAME safe direction (over-restrictive, never under-restrictive)
        as every other credit path. Best-effort on the per-run counter;
        NEVER raises.

        KNOWN LIMITATION (postpaid): LiveLedgerService.credit() is
        documented as a deliberate no-op for postpaid tenants ("no
        spendable balance"), so a positive delta (over-estimate) on a
        postpaid hold does NOT lower the live month-to-date spend counter
        — it stays inflated by the over-hold until month rollover, since
        reconcile_postpaid() only ever MAX-merges (raises, never lowers).
        Net effect: a postpaid owner whose estimates run high could see the
        live spend counter (and therefore the budget-cap crossing check)
        read higher than the true durable spend for the rest of the month.
        Flagging for Task 5/6 — no postpaid-specific counter-lowering path
        exists yet; the brief's specified design routes settle exclusively
        through credit().
        """
        delta_micros = int(delta_micros)
        if delta_micros:
            LiveLedgerService.credit(owner_id, tenant, delta_micros)
        if run_id and delta_micros and enforcement_on(tenant):
            try:
                _client().eval(_RUNCOST_CREDIT_IF_PRESENT, 1,
                               _runcost_key(run_id), -delta_micros, LEDGER_TTL_SECONDS)
            except Exception:
                logger.warning("hold_service.run_settle_failed",
                               extra={"data": {"run_id": str(run_id)}})

    @staticmethod
    def release(owner_id, tenant, run_id, estimate_micros):
        """Full credit-back of a hold — duplicate ingest, failed append, or
        any path that must UNDO an acquire() entirely. Equivalent to
        settle(delta_micros=estimate_micros)."""
        HoldService.settle(owner_id, tenant, run_id, estimate_micros)
