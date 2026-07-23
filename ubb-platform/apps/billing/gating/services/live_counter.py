"""THE live counter (#111) — the one owner of the Tier-2 Redis state.

The SHARED, owner-keyed Redis counters that the fast lane maintains so an
API response can express a real wallet/budget stop verdict, plus the
cooperative customer-wide stop flag and the seat-keyed budget counter. Every
``ubb:livebal:*`` / ``ubb:livespend:*`` / ``ubb:stop:*`` / ``ubb:stopchan:*``
/ ``ubb:budget:*`` key format, every Lua script, and the TTL discipline live
HERE and only here — pinned by ``apps/billing/tests/
test_live_counter_perimeter.py`` (ADR-001 walker style) and frozen once in
this module's own pin test, never by scattered private imports.

Gated by ``enforcing(tenant)`` — when the tenant's ``enforcement_mode`` is
``off`` every operation is a cheap no-op and behavior is byte-for-byte
unchanged. The arrival-signals switch (#46) turns the fast-lane WRITES off as
one unit; the durable-lane legs (verdict reads, signal catch-up, flag
re-alignment) never switch off.

Two parallel live counters, one per billing mode, both keyed on the resolved
billing OWNER (``resolve_billing_owner``) so a pooled business is one counter
across all its seats and an allocated/individual owner is its own:

  PREPAID  ``ubb:livebal:{owner}``        = micros of spendable balance.
           DECRBY on usage, INCRBY on credit. Tracks (credits − recorded
           usage), which is ``durable_balance − undebited_usage`` ≤ durable
           balance, so the live view is the CONSERVATIVE (lower) one.
           Reconcile MIN-merges toward the durable balance (only LOWERS), so
           a credit that the fast path missed cannot be re-raised by
           reconcile — therefore EVERY credit site MUST call ``credit()``
           (the three mandatory hooks in P2.3). A missed credit fails SAFE
           (over-restrictive), a missed debit is absorbed by the MIN-merge.

  POSTPAID ``ubb:livespend:{owner}:{YYYY-MM}`` = micros of month-to-date
           spend. INCRBY on usage. Reconcile MAX-merges toward the durable
           owner-aggregated billed total (only RAISES), catching the
           first-use under-count (the counter is born at the first event,
           not the month-to-date total) within one reconcile cycle.

The BUDGET counter (D3/D3b of the #111 grilling) is the seat-keyed sibling:
``ubb:budget:{customer_id}:{YYYY-MM}`` = micros of the seat's month-to-date
billed spend, INCRBY'd by the drawdown tail and MAX-merged toward the durable
ledger by the hourly rebuild. One client dialect: like every other key here
it lives on the raw client with the module's TTL discipline — the old
two-dialect hack (Django-cache counter ops + a raw-client Lua aimed at the
cache-prefixed physical key) is retired. Budget POLICY — config resolution,
threshold alerts, the fail-open/fail-closed gate — stays in BudgetService;
only the counter mechanics live here.

SEEDING (the one deliberate over-permissive window): the prepaid counter
seeds from the DURABLE wallet balance, which at first-use may still be high
by the usage that is recorded-but-not-yet-async-debited (handlers.py drains
the debit after record_usage commits). The live counter is therefore
over-permissive by at most that one outbox-drain window, bounded and
reconcile-corrected, and backstopped by the durable START-GATE (RiskService
reads the real wallet for a NEW run). This is the reworded I2 contract (a
bounded window, not an absolute bound) — chosen over an anti-join seed
because the latter introduces a concurrency race that the LOWER-only
MIN-merge cannot repair.

KEY/CLIENT (D9): the ubb:* keys are RAW-client only (redis.from_url + Lua
EVAL), never touched via django's ``cache.*`` — so they are immune to
django-redis's ``:1:`` version prefix. ``_client()`` is the single
monkeypatch seam for Redis-down tests (D4).

Tests fabricate counter/flag state ONLY through ``Door`` (the D4 test door,
below) — never by importing key helpers or the raw client.
"""
import logging

from django.conf import settings

from apps.billing.gating.crossing import (budget_stop_threshold, crossed_live,
                                          floor_line, month_label_bounds,
                                          past_floor, recovered_floor,
                                          same_month)
from apps.platform.tenants.flags import arrival_signals_on, enforcing

logger = logging.getLogger("ubb.billing")

COUNTER_TTL_SECONDS = 62 * 24 * 3600  # current month + buffer; refreshed on every write

# Observability (P7): reconcile loud-logs when the live counter has drifted from
# the durable ledger by more than this (a healthy counter tracks within a few
# events). A persistent spike means a missed credit/debit hook or an unhealed
# seed window — the analog of Stage D's drawdown-repair spike alert.
DRIFT_ALERT_MICROS = 50_000_000  # $50

# --- Lua sources -----------------------------------------------------------

# Prepaid: atomic seed-if-absent (to the durable balance) then DECRBY. Two
# concurrent first-use debits both pass the same seed; the SET only fires once
# (EXISTS guard), and BOTH DECRBY — so the counter is decremented exactly once
# per event with no double seed. KEYS[1]=livebal; ARGV[1]=seed; ARGV[2]=debit;
# ARGV[3]=ttl. Returns the post-debit balance.
_SEED_AND_DECR = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
end
local v = redis.call('DECRBY', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return v
"""

# INCRBY-if-present: applies ONLY if the key is seeded; an unseeded increment
# is dropped and reported as nil, because first-use seeds/rebuilds from the
# durable ledger. ARGV[1] may be negative. Returns new value or nil.
# KEYS[1]=counter; ARGV[1]=amount; ARGV[2]=ttl. One script, three riders: the
# prepaid credit hook, the upward repair's ``repair_incr`` (D1 — the same
# primitive, different policy around it), and the budget drawdown INCR (D3b —
# a missing budget key rebuilds from Postgres instead).
_INCR_IF_PRESENT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    local v = redis.call('INCRBY', KEYS[1], ARGV[1])
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return v
end
return nil
"""

# Prepaid reconcile MIN-merge: only LOWERS toward the durable balance (never
# raises — credits are applied via _INCR_IF_PRESENT, so reconcile must not
# overwrite an in-flight decrement upward). Absent key -> seed to durable.
# KEYS[1]=livebal; ARGV[1]=durable_balance; ARGV[2]=ttl.
_RECONCILE_MIN = """
local cur = redis.call('GET', KEYS[1])
local target = tonumber(ARGV[1])
if cur == false then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
if target < tonumber(cur) then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return tonumber(cur)
"""

# Postpaid spend INCRBY (creates at amount on first use). KEYS[1]=livespend;
# ARGV[1]=amount (negative at settle: a positive over-hold delta LOWERS the
# spend); ARGV[2]=ttl. Returns the running month-to-date spend.
_SPEND_INCR = """
local v = redis.call('INCRBY', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return v
"""

# Reconcile MAX-merge: only RAISES toward the durable month total (catches
# the first-use under-count / a lost INCR). ONE script for both month-scoped
# counters — the postpaid owner livespend and the seat budget counter (D3b
# retired the budget_service mirror copy). Within a month real spend only
# rises and the durable ledger is the truth, so raising-toward-durable is the
# correct discipline; the only legitimate decrease is at month rollover,
# where the key LABEL changes and this script seeds the fresh key. An atomic
# read+set(max) in one server-side op, so a concurrent INCR is never erased:
# an INCR before the GET is included; one after the SET only raises.
# KEYS[1]=livespend|budget; ARGV[1]=durable_total; ARGV[2]=ttl.
_RECONCILE_MAX = """
local cur = redis.call('GET', KEYS[1])
local target = tonumber(ARGV[1])
if cur == false then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
if target > tonumber(cur) then
    redis.call('SET', KEYS[1], target, 'EX', ARGV[2])
    return target
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return tonumber(cur)
"""

# The batch-hold move (one eval per item, pipelined across the batch).
# KEYS[1] = balance/spend key (livebal for prepaid, livespend for postpaid)
# ARGV[1] = seed (prepaid: durable wallet balance; postpaid: unused, pass 0)
# ARGV[2] = estimate_micros — ALWAYS POSITIVE. ARGV[4] (not the sign of this
#           value) selects the balance-move direction.
# ARGV[3] = ttl seconds — refreshed (EXPIRE) on every key this script touches.
# ARGV[4] = '1' => postpaid (INCRBY the spend counter — _SPEND_INCR's move);
#           '0' => prepaid (seed-if-absent then DECRBY — _SEED_AND_DECR's).
# ARGV[5] = '1' => skip the balance/spend move entirely (I9 parity: a
#           postpaid item backdated to a PRIOR month must not inflate THIS
#           month's live spend counter — mirrors debit()'s same_month guard).
#           Prepaid callers always pass '0' here (livebal is not month-scoped
#           — a backfill still legitimately reduces spendable balance). When
#           skipped, returns the CURRENT (untouched) KEYS[1] value (0 if
#           absent) so the caller's crossing check still sees whatever a
#           SIBLING item in the same batch already moved it to.
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


def _client():
    import redis
    return redis.from_url(settings.REDIS_URL)


def _livebal_key(owner_id) -> str:
    return f"ubb:livebal:{owner_id}"


def _livespend_key(owner_id, label) -> str:
    return f"ubb:livespend:{owner_id}:{label}"


def _stop_key(owner_id) -> str:
    # Customer-wide cooperative stop flag. Owner-keyed (NOT month-scoped), so a
    # pooled business stops all its seats and an allocated seat stops itself.
    return f"ubb:stop:{owner_id}"


def _budget_key(customer_id, label) -> str:
    # SEAT-keyed (customer, not owner) — budgets cap the seat's own spend.
    return f"ubb:budget:{customer_id}:{label}"


def stop_channel(owner_id) -> str:
    """The owner's stop-flag pub/sub channel — the one PUBLIC key-shaped name
    (subscribers are outside the module by definition; Plan 2's future SSE
    endpoint reads it). Everything else about the key space is private."""
    return f"ubb:stopchan:{owner_id}"


def _held_verdict() -> dict:
    """A fresh held/not-stopped verdict dict (never share a single mutable
    instance across items — callers may mutate their own copy)."""
    return {"held": True, "stop": False, "stop_reason": None, "stop_scope": None}


class LiveCounter:
    # ---- synchronous usage hook (called from record_usage) ----
    @staticmethod
    def debit(owner_id, tenant, billed_cost_micros, *, effective_at=None, now=None):
        """Apply this event to the owner's live counter, synchronously, and
        return the customer-wide stop verdict.

        P3: if this event drives the counter across the threshold (prepaid
        wallet floor / postpaid budget cap) the owner-keyed stop flag is SET
        (cooperative — never rolls back this event; I3). The returned dict
        carries {mode, balance_micros|spend_micros, stop, stop_reason,
        stop_scope} (the stop fields reflect the flag AFTER this event, so a
        flag a sibling run set is surfaced too), plus ``stop_episode_opened``
        (the new episode_seq) when THIS debit won the stop transition — the
        #41 tipping-event attribution. Returns None when disabled /
        zero-cost / (postpaid) backdated to a prior month. NEVER raises — a
        Redis failure logs and returns None (fail-open; the durable start-gate
        remains the backstop).

        Arrival signals OFF (#46, §E — enforcing, switch off): no counter
        debit, no crossing check — the fast lane is off as one unit. Returns
        the bare stop verdict READ from the durable-maintained flag so the
        ack carries the identical fields in both postures; detection happens
        at settle (the durable drawdown lane)."""
        if not enforcing(tenant) or billed_cost_micros <= 0:
            return None
        if not arrival_signals_on(tenant):
            return LiveCounter.read(owner_id, tenant)
        try:
            if tenant.billing_mode == "postpaid":
                from django.utils import timezone
                now = now or timezone.now()
                # I9: a prior-month backdated event must not inflate THIS
                # month's live counter (mirrors handlers.py budget tail).
                if not same_month(effective_at, now):
                    return None
                label, _, _ = month_label_bounds(now)
                key = _livespend_key(owner_id, label)
                v = int(_client().eval(_SPEND_INCR, 1, key, int(billed_cost_micros), COUNTER_TTL_SECONDS))
                base = {"mode": "postpaid", "spend_micros": v}
                mode = "postpaid"
            else:
                # prepaid / meter_only: mirror the async wallet drawdown branch.
                from apps.billing.queries import get_customer_balance
                key = _livebal_key(owner_id)
                seed = int(get_customer_balance(owner_id))
                v = int(_client().eval(_SEED_AND_DECR, 1, key, seed, int(billed_cost_micros), COUNTER_TTL_SECONDS))
                base = {"mode": "prepaid", "balance_micros": v}
                mode = "prepaid"
            # Set (never clear) the cooperative stop flag on a crossing; a
            # non-crossing event must not clear a flag a sibling run set — the
            # flag lifts only on recovery (credit / reconcile).
            if LiveCounter._crossed(mode, v, owner_id, tenant):
                from apps.platform.tasks.reasons import CUSTOMER_WIDE_STOP
                opened = LiveCounter._set_stop(
                    owner_id, CUSTOMER_WIDE_STOP, tenant=tenant,
                    balance_micros=v if mode == "prepaid" else 0)
                if opened is not None:
                    # THIS debit won the stop transition — the caller's event
                    # is the episode's tipping event (#41 stop-context).
                    base["stop_episode_opened"] = opened
            base.update(LiveCounter.read(owner_id, tenant))
            return base
        except Exception:
            logger.warning("live_counter.debit_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return None

    # ---- accept-time hold for the async ingest path (estimate-hold-settle) ----
    @staticmethod
    def hold(owner_id, tenant, items):
        """Atomically reserve an estimated cost for each item — always holds.

        The money mirror for async ingestion: the ONLY place an ESTIMATED
        cost is reserved before the async worker records the real usage
        event. Same counters, same stop flag as ``debit`` — there is only ONE
        live counter per owner, so a hold taken here is immediately visible
        to (and races fairly against) the synchronous path, and vice versa.

        items: [{"estimate_micros": int, "effective_at": datetime|None}]

        effective_at (I9 parity with ``debit``): for a POSTPAID tenant, an
        item backdated to a PRIOR calendar month does not move the livespend
        counter (a legitimate backfill must not inflate THIS month's spend
        uncorrectably — the reconcile MAX-merge only ever RAISES, so an
        inflated value could never self-correct). PREPAID is untouched:
        livebal is not month-scoped, so a backfill still legitimately reduces
        the spendable balance.

        One-rule (#37): the acquire ALWAYS holds, against the wallet only —
        task limits are provider-cost denominated and exact provider cost
        exists only at settle, so unit-limit detection lives there
        (UsageService.settle_raw), not here. Nothing on this path ever
        rejects an item.

        Per item, ONE Lua eval (``_ACQUIRE``), pipelined across the whole
        batch so an N-item batch is still N atomic server-side ops. Back in
        Python the owner's crossing threshold is resolved ONCE per call
        (``_threshold`` — not per item, to avoid an ORM query per item) and
        every held item's post-hold value is compared against it in Python.
        A crossing sets the cooperative stop flag; this NEVER rejects or
        rolls back the hold that crossed it (I3 — cooperative, not
        transactional).

        Returns one verdict dict per item, in the SAME order as `items`:
        {"held": bool, "stop": bool, "stop_reason": str|None,
         "stop_scope": str|None}. ``held`` reports whether a hold was
        actually reserved — the caller records it on the RawIngestEvent row
        so settle only ever trues up a hold that was really taken.

        Arrival signals OFF (#46, §E — enforcing, switch off): the whole
        fast lane is off as one unit — NO Redis write of any kind here (no
        hold, no crossing check); every item is ``held: False``. The stop
        fields still carry the verdict READ from the durable-maintained flag
        (``read``), so the ack schema is identical in both postures — only
        the latency profile changes (detection happens at settle).

        Disabled (enforcement_mode == "off"): every item is held, unstopped
        — a cheap no-op passthrough, matching every other Tier-2 gate (the
        durable start-gate, e.g. RiskService, remains the real backstop).

        NEVER raises: any error (Redis unreachable, etc.) fails OPEN — every
        item is held, unstopped — identical fail-open contract to ``debit``.
        """
        if not enforcing(tenant):
            return [_held_verdict() for _ in items]
        if not arrival_signals_on(tenant):
            verdict = LiveCounter.read(owner_id, tenant)
            out = []
            for _ in items:
                o = _held_verdict()
                o["held"] = False
                o.update(verdict)
                out.append(o)
            return out

        from django.utils import timezone
        from apps.billing.queries import get_customer_balance

        postpaid = tenant.billing_mode == "postpaid"
        now = timezone.now()
        try:
            if postpaid:
                label, _, _ = month_label_bounds(now)
                bal_key = _livespend_key(owner_id, label)
                seed = 0
            else:
                bal_key = _livebal_key(owner_id)
                seed = int(get_customer_balance(owner_id))

            client = _client()
            pipe = client.pipeline()
            for it in items:
                skip_balance = postpaid and not same_month(it.get("effective_at"), now)
                pipe.eval(
                    _ACQUIRE, 1, bal_key,
                    seed, int(it["estimate_micros"]), COUNTER_TTL_SECONDS,
                    1 if postpaid else 0,
                    1 if skip_balance else 0,
                )
            raw_results = pipe.execute()

            # Threshold-crossing bound resolved ONCE per owner for this whole
            # batch (not per item — that would be an ORM query per item) and
            # compared in plain Python below.
            mode = "postpaid" if postpaid else "prepaid"
            threshold = LiveCounter._threshold(mode, owner_id, tenant)
            out = []
            crossed = False
            crossing_value = 0
            for post in raw_results:
                value = int(post)
                # The crossing module owns both orientations (#110) — this is
                # the same compare the fast lane's _crossed makes, against the
                # once-per-batch threshold.
                if crossed_live(mode, value, threshold) and not crossed:
                    crossed = True
                    crossing_value = value
                out.append(_held_verdict())

            if crossed:
                from apps.platform.tasks.reasons import CUSTOMER_WIDE_STOP
                LiveCounter._set_stop(
                    owner_id, CUSTOMER_WIDE_STOP, tenant=tenant,
                    balance_micros=crossing_value if mode == "prepaid" else 0)
            verdict = LiveCounter.read(owner_id, tenant)
            for o in out:
                o.update(verdict)
            return out
        except Exception:
            # A failure THIS late (e.g. in _threshold's ORM lookup, _set_stop,
            # or the verdict read) already ran the Redis pipe -- money already
            # moved -- so this fail-open only means a crossing here goes
            # UNDETECTED for one batch; the next hold()/debit() call
            # re-evaluates the now-updated counter and catches it then (a
            # one-batch stop-flag delay, not a lost debit).
            logger.warning("live_counter.hold_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return [_held_verdict() for _ in items]  # fail-open

    @staticmethod
    def settle(owner_id, tenant, delta_micros, *, effective_at=None):
        """delta = estimate − exact. Positive => credit back the over-hold
        (the actual cost came in lower than the estimate); negative =>
        debit further (an underestimate).

        PREPAID: routes the balance-side adjustment through ``credit`` — the
        SAME MIN-merge-safe site every other credit hook (top-up,
        refund-reversal, manual credit) uses, so a fast-path drop here fails
        the SAME safe direction (over-restrictive, never under-restrictive)
        as every other credit path.

        POSTPAID: ``credit`` is a deliberate no-op for postpaid ("no
        spendable balance"), so settle applies the delta DIRECTLY to the
        CURRENT month's livespend counter (INCRBY −delta via the module's
        ``_SPEND_INCR`` — the same script the debit lane runs: a positive
        over-hold delta LOWERS the spend, a negative delta raises it
        further). Without this, every over-estimate would permanently
        inflate the counter — the postpaid reconcile MAX-merge only ever
        RAISES, so it could never self-correct, and budget caps would fire
        increasingly early for the rest of the month.

        Prior-month settle guard (I9 parity): `effective_at` is the settled
        event's effective instant (optional; None == "treat as current
        month", so every pre-existing caller that omits it is unaffected). For
        POSTPAID, when `effective_at` falls in a PRIOR calendar month relative
        to settle wall-clock time, the livespend adjustment is skipped
        entirely — the matching ``hold`` already skipped this event's
        hold-time move for the same reason (see its `skip_balance` guard), so
        applying a delta here would adjust a counter this event never
        touched. PREPAID is untouched (livebal is not month-scoped — a
        backfill still legitimately reduces spendable balance).

        Month-rollover window (postpaid, same-month case): a hold acquired in
        month M that settles in month M+1 adjusts M+1's livespend key (the
        hold inflated M's). The exposure is only the few seconds of ingest
        latency straddling the rollover instant, and the MAX-merge reconcile
        toward each month's durable billed total re-corrects both months'
        counters within one reconcile cycle.

        Best-effort everywhere; NEVER raises. Does NOT clear stop flags —
        recovery stays with reconcile/credit(), matching existing semantics.
        """
        delta_micros = int(delta_micros)
        if delta_micros:
            if tenant.billing_mode == "postpaid":
                if enforcing(tenant):
                    from django.utils import timezone
                    now = timezone.now()
                    if same_month(effective_at, now):
                        try:
                            label, _, _ = month_label_bounds(now)
                            key = _livespend_key(owner_id, label)
                            _client().eval(_SPEND_INCR, 1, key,
                                           -delta_micros, COUNTER_TTL_SECONDS)
                        except Exception:
                            logger.warning("live_counter.settle_failed",
                                           extra={"data": {"owner_id": str(owner_id)}})
            else:
                LiveCounter.credit(owner_id, tenant, delta_micros)

    @staticmethod
    def release(owner_id, tenant, estimate_micros, *, effective_at=None):
        """Full credit-back of a hold — duplicate ingest, failed append, or
        any path that must UNDO a hold() entirely. Equivalent to
        settle(delta_micros=estimate_micros). `effective_at` forwards to
        settle()'s prior-month guard — see its docstring."""
        LiveCounter.settle(owner_id, tenant, estimate_micros, effective_at=effective_at)

    # ---- customer-wide stop flag (P3) ----
    @staticmethod
    def _threshold(mode, owner_id, tenant):
        """Resolve the ONE comparable crossing bound for this (mode, owner):
        postpaid -> ``crossing.budget_stop_threshold`` over the resolved
        BudgetConfig (None = can never cross: no config, cap <= 0, or an
        advisory ``enforce_mode`` — #110 unified every lane on the
        BudgetService.check semantics); prepaid -> ``crossing.floor_line``
        (the wallet floor). Exactly ONE ORM lookup (BudgetConfig via
        BudgetService.resolve_config_for, or CustomerBillingProfile/
        BillingTenantConfig via get_customer_min_balance).

        Kept separate from ``_crossed`` so the batch lane (``hold``)
        resolves this ONCE per call and compares every item's post-hold
        value against it in plain Python, instead of re-querying per item."""
        if mode == "postpaid":
            from apps.billing.gating.services.budget_service import BudgetService
            return budget_stop_threshold(
                BudgetService.resolve_config_for(tenant.id, owner_id))
        from apps.billing.queries import get_customer_min_balance
        return floor_line(get_customer_min_balance(owner_id, tenant.id))

    @staticmethod
    def _crossed(mode, value, owner_id, tenant) -> bool:
        """True if the live counter has crossed the owner's threshold:
        prepaid balance below the wallet floor (-min_balance), or postpaid
        month-to-date spend at/over the budget stop line. Resolves the
        threshold via ``_threshold`` (ONE ORM query per call) and compares
        via ``crossing.crossed_live`` — the one owner of both orientations.
        A caller evaluating many items per owner in one batch should instead
        call ``_threshold`` once and compare each item in Python (see
        ``hold``)."""
        return crossed_live(
            mode, value, LiveCounter._threshold(mode, owner_id, tenant))

    @staticmethod
    def _set_stop(owner_id, reason, tenant=None, balance_micros=0):
        """Set the customer-wide cooperative stop flag, and on the unset->set
        TRANSITION only (SET ... NX on the flag key itself is the transition
        detector — no companion key needed) fan out two best-effort side
        effects: a ``stop_channel(owner_id)`` Redis pub/sub publish (Plan 2's
        future SSE endpoint) and the ``StopSignalService.drive_stop``
        transition — the #39 signal ledger, which on its WINNING transition
        emits ``stop.fired`` (atomically with the ledger row) and performs the
        folded durable suspension. A crossing the durable lane already
        signaled loses the ledger transition here and emits nothing, so the
        two lanes together fire exactly one stop per episode.

        A repeat crossing while the flag is already set (was_new falsy) only
        refreshes the TTL — no re-publish/re-drive (no spam). ``_clear_stop``
        deletes the key outright, so the NEXT ``_set_stop`` naturally re-arms
        the fast lane's transition detector; the ledger guard, not the flag,
        is what dedups emission (a re-set after a Redis flush or blind window
        drives the ledger again and simply loses).

        NEVER raises into the caller — this runs on the accept-time money
        path (debit / hold). The pub/sub publish is guarded by try/except
        (not a DB statement, so that suffices). drive_stop opens its own
        ``transaction.atomic`` — a SAVEPOINT inside the sync path's ambient
        transaction (the budget_service.check_thresholds pattern): a DB-level
        failure inside it (deadlock, timeout) rolls back to the savepoint
        cleanly, so the ambient Postgres transaction stays usable and the
        caller's money-path statements are never collaterally rolled back by
        stop-signal bookkeeping. (The savepoint cannot survive a DEAD
        CONNECTION — but then the whole outer transaction is doomed
        regardless; that is not a gap specific to this call.) A transition
        lost to the rollback is re-driven by the durable lane / reconcile —
        late, never lost.

        tenant is optional: a call site without tenant context (there is
        none today, but keeping this defensive) degrades to pub/sub-only
        rather than crashing. balance_micros is the crossing balance the
        detecting lane saw (prepaid live value; postpaid passes 0) — it rides
        the folded suspension's CustomerSuspended event.

        Returns the episode_seq drive_stop opened when THIS call won the
        ledger transition (#41 tipping-event attribution), else None.
        """
        client = _client()
        was_new = client.set(_stop_key(owner_id), reason, ex=COUNTER_TTL_SECONDS, nx=True)
        if not was_new:
            client.expire(_stop_key(owner_id), COUNTER_TTL_SECONDS)
            return None
        try:
            client.publish(stop_channel(owner_id), reason)
        except Exception:
            logger.warning("live_counter.stop_publish_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
        if tenant is not None:
            try:
                from apps.billing.gating.services.stop_signal_service import StopSignalService
                # Returns the opened episode_seq when THIS call won the
                # ledger transition (#41: the caller's event is the tipping
                # event), else None — a crossing the durable lane already
                # signaled loses silently.
                return StopSignalService.drive_stop(owner_id, tenant, reason=reason,
                                                    balance_micros=balance_micros)
            except Exception:
                logger.warning("live_counter.stop_event_failed",
                               extra={"data": {"owner_id": str(owner_id)}})
        return None

    @staticmethod
    def ensure_stop_flag(owner_id, reason):
        """Best-effort: make the fast-lane flag reflect a stop the DURABLE
        lane (drawdown handler / reconcile) signaled, so ack verdicts show it
        without waiting for the next fast-lane crossing. NX detects only
        whether the flag was ABSENT (the #44 re-alignment counter) — never
        emission semantics, which the ledger guard owns; an existing flag
        keeps its reason and gets a TTL refresh (every path writes the same
        customer-wide constant, so this is byte-equivalent to the old plain
        SET). Returns True when a missing flag was re-set — the patrol's
        flag-realignment outcome; a Redis failure only delays flag
        visibility, never the signal."""
        try:
            client = _client()
            was_absent = client.set(_stop_key(owner_id), reason,
                                    ex=COUNTER_TTL_SECONDS, nx=True)
            if not was_absent:
                client.expire(_stop_key(owner_id), COUNTER_TTL_SECONDS)
            return bool(was_absent)
        except Exception:
            logger.warning("live_counter.ensure_stop_flag_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return False

    @staticmethod
    def _clear_stop(owner_id):
        """Delete the fast-lane stop flag. Best-effort: a Redis failure must
        not abort the caller's clearing sequence (the ledger clear already
        committed durably); the stale flag is re-deleted by the next
        clearing path or reconcile cycle. Returns True when a flag actually
        existed and was deleted — an orphaned flag re-aligned to durable
        truth (the #44 patrol counter)."""
        try:
            return bool(_client().delete(_stop_key(owner_id)))
        except Exception:
            logger.warning("live_counter.clear_stop_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return False

    # Monetary suspension reasons that may be auto-cleared on recovery (D15).
    _MONEY_SUSPEND_REASONS = ("min_balance_exceeded", "budget_exceeded")

    @staticmethod
    def _maybe_unsuspend(owner_id):
        """Durably reactivate an owner that was suspended for a MONETARY reason,
        once the balance/spend has recovered (D15). Serializes on the owner
        Customer row (the same row the suspend paths lock), and the winning
        suspended->active transition guard prevents flip-flop. NEVER un-suspends
        an admin/fraud suspension (suspension_reason not monetary)."""
        from django.db import transaction
        from apps.platform.customers.models import Customer
        try:
            with transaction.atomic():
                owner = Customer.objects.select_for_update().get(id=owner_id)
                if (owner.status == "suspended"
                        and owner.suspension_reason in LiveCounter._MONEY_SUSPEND_REASONS):
                    owner.status = "active"
                    owner.suspension_reason = ""
                    owner.save(update_fields=["status", "suspension_reason", "updated_at"])
        except Exception:
            logger.warning("live_counter.unsuspend_failed",
                           extra={"data": {"owner_id": str(owner_id)}})

    @staticmethod
    def resume(owner_id, tenant, *, reason, balance_micros=0) -> bool:
        """Lift a stop: the clearing trio as ONE op (D2 of the #111 grilling)
        — drive the signal-ledger clearing transition (the winner emits
        ``stop.cleared`` with the episode it closes), delete the fast-lane
        flag, and durably un-suspend behind the D15 gate. The module owns HOW
        lifting works (this order, the durable gate); callers own WHEN — the
        credit hook on a balance re-cross (``balance_recovered``), the hourly
        reconcile bottom line (``reconciled``), the upward repair on a lifted
        wedge (``balance_repaired``).

        The durable gate (D15): un-suspension is decided on the DURABLE
        wallet, never the live view — a dispute/refund debit is not mirrored
        to the live counter, so a live value can over-state and would
        otherwise flip status active while the true balance is still below
        the floor. Postpaid has no wallet floor: the reason guard inside
        ``_maybe_unsuspend`` (monetary suspensions only) is the whole gate.

        drive_clear opens its own atomic block and is NOT swallowed here —
        money-path callers wrap this call (a signal-bookkeeping failure must
        never poison a recorded event; the reconcile bottom line re-drives).
        Returns True when the fast flag actually existed and was deleted —
        the #44 flag-realignment outcome."""
        from apps.billing.gating.services.stop_signal_service import StopSignalService
        StopSignalService.drive_clear(owner_id, tenant, reason=reason,
                                      balance_micros=balance_micros)
        realigned = LiveCounter._clear_stop(owner_id)
        if tenant.billing_mode == "postpaid":
            LiveCounter._maybe_unsuspend(owner_id)
        else:
            from apps.billing.queries import (get_customer_balance,
                                              get_customer_min_balance)
            floor = get_customer_min_balance(owner_id, tenant.id)
            if recovered_floor(int(get_customer_balance(owner_id)), floor):
                LiveCounter._maybe_unsuspend(owner_id)
        return realigned

    @staticmethod
    def read(owner_id, tenant, *, counter=False, now=None) -> dict:
        """The owner's live position. Default: the customer-wide stop verdict
        {stop, stop_reason, stop_scope} — fail-open (a Redis failure reads as
        not-stopped) and short-circuiting to not-stopped when enforcement is
        off, BEFORE touching Redis (D17). This is the money-path read (ack
        verdicts, the start-gate, the queries.py port).

        counter=True additionally reads the mode's raw counter:
        ``counter_micros`` (int; None = unseeded/absent) and
        ``counter_blind`` (True when Redis could not answer — distinct from
        absent, because an absent key means "seeds from durable at first
        use, nothing to measure" while blind means "cannot measure at all").
        The upward repair keys its candidate lifecycle on that distinction.
        ``now`` scopes the postpaid month (defaults to wall clock)."""
        verdict = {"stop": False, "stop_reason": None, "stop_scope": None}
        if not enforcing(tenant):
            if counter:
                verdict.update({"counter_micros": None, "counter_blind": False})
            return verdict
        try:
            v = _client().get(_stop_key(owner_id))
        except Exception:
            v = None
        else:
            if v is not None:
                reason = v.decode() if isinstance(v, bytes) else str(v)
                verdict = {"stop": True, "stop_reason": reason,
                           "stop_scope": "customer"}
        if counter:
            try:
                if tenant.billing_mode == "postpaid":
                    from django.utils import timezone
                    label, _, _ = month_label_bounds(now or timezone.now())
                    c = _client().get(_livespend_key(owner_id, label))
                else:
                    c = _client().get(_livebal_key(owner_id))
            except Exception:
                verdict.update({"counter_micros": None, "counter_blind": True})
            else:
                verdict.update({"counter_micros": int(c) if c is not None else None,
                                "counter_blind": False})
        return verdict

    # ---- prepaid credit hook (top-up / refund-reversal / manual credit) ----
    @staticmethod
    def credit(owner_id, tenant, amount_micros):
        """INCRBY the prepaid live balance by amount_micros (may be negative).
        No-op for postpaid (no spendable balance) and when disabled. Best-effort
        — but note a DROPPED credit fails over-restrictive (MIN-merge cannot
        re-raise it), so this is called from EVERY credit site.

        Recovery (P3 + #39 §E): a positive credit that lifts the balance back
        to/above the floor is the RESUME fast lane — it runs ``resume``
        (reason ``balance_recovered``). The live counter decides the re-cross
        when Redis answered; when the fast INCRBY failed or found no seeded
        key, the DURABLE balance decides instead — every durable credit site
        calls this hook, so a top-up that re-crosses the floor during a Redis
        blind window still resumes now, not an hour later at reconcile. (A
        negative credit / grant-expiry never clears.)"""
        if not enforcing(tenant) or tenant.billing_mode == "postpaid" or amount_micros == 0:
            return
        v = None
        try:
            v = _client().eval(_INCR_IF_PRESENT, 1, _livebal_key(owner_id),
                               int(amount_micros), COUNTER_TTL_SECONDS)
        except Exception:
            logger.warning("live_counter.credit_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
        if amount_micros <= 0:
            return
        try:
            from apps.billing.queries import get_customer_min_balance, get_customer_balance
            from apps.billing.gating.services.stop_signal_service import (
                CLEAR_BALANCE_RECOVERED)
            floor = get_customer_min_balance(owner_id, tenant.id)
            if v is not None:
                clearance_balance = int(v)
            else:
                # Redis blind or unseeded counter: the durable balance is the
                # guaranteed lane's view of the re-cross.
                clearance_balance = int(get_customer_balance(owner_id))
            if recovered_floor(clearance_balance, floor):
                LiveCounter.resume(owner_id, tenant,
                                   reason=CLEAR_BALANCE_RECOVERED,
                                   balance_micros=clearance_balance)
            # #40 §F — the soft floor's credit-side clearing, independent of
            # the hard pair (an owner can be past the soft line without ever
            # having stopped).
            LiveCounter._drive_soft_clear_if_recovered(
                owner_id, tenant, clearance_balance, CLEAR_BALANCE_RECOVERED)
        except Exception:
            logger.warning("live_counter.credit_recovery_failed",
                           extra={"data": {"owner_id": str(owner_id)}})

    @staticmethod
    def _drive_soft_clear_if_recovered(owner_id, tenant, balance_micros, reason):
        """#40 §F — drive the soft_floor clearing transition when the given
        balance sits at/above the resolved soft line, or the soft floor was
        UNCONFIGURED mid-episode (no line left to be past). Only the winning
        transition emits soft_floor.cleared. A below-line balance is a no-op
        both ways: the CREDIT path (this helper's only caller) deliberately
        has no SET power for the soft family — crossings are detected by the
        durable drawdown lane, backstopped by the hourly patrol's soft-SET
        leg in the prepaid reconcile (#44 §C.1)."""
        from apps.billing.queries import get_customer_soft_min_balance
        from apps.billing.gating.services.stop_signal_service import StopSignalService
        soft = get_customer_soft_min_balance(owner_id, tenant.id)
        if recovered_floor(balance_micros, soft):
            StopSignalService.drive_soft_cleared(
                owner_id, tenant, reason=reason,
                balance_micros=balance_micros, soft_min_balance_micros=soft)

    # ---- the upward repair's primitive (D1) ----
    @staticmethod
    def repair_incr(owner_id, amount_micros):
        """The policy-free repair primitive (D1 of the #111 grilling): add N
        to the prepaid live counter ONLY if the counter exists, and return
        the new value (None when the key is absent — creating one here would
        plant a stale absolute value that first-use seeding owns). Nothing
        more: the two-pass grace, the de-minimis, the min(first, second)
        discipline, the audit row, and the wedge-lifted resume all stay with
        ``repair.py`` — forcing them through ``credit()`` would thread
        repair's policy into the credit hook as flags, exactly the semantic
        drift the pin suites exist to catch. Rides the same INCRBY-if-present
        script every credit site uses, so the upward move is
        relative-always, never an absolute SET. Redis errors propagate — the
        caller owns failure policy too."""
        v = _client().eval(_INCR_IF_PRESENT, 1, _livebal_key(owner_id),
                           int(amount_micros), COUNTER_TTL_SECONDS)
        return None if v is None else int(v)

    # ---- reconcile (hourly beat) ----
    @staticmethod
    def _reconcile_transitions(owner_id, tenant, crossed, basis_micros):
        """The bottom-line catch-up both reconcile paths share (#39 §D/§E):
        drive the signal-ledger transition the reconciled position demands —
        at most one net stop/resume per owner per run, and only a WINNING
        transition emits (a position the lanes already signaled is a silent
        no-op). SET power: a crossing the fast lane missed (Redis blind
        window, dropped savepoint) is signaled here — late, never lost. The
        fast-lane flag is re-aligned best-effort either way (patrol job
        §C.2: durable truth owns the verdict cache); returns True when the
        flag actually changed — the #44 flag-realignment outcome."""
        from apps.platform.tasks.reasons import CUSTOMER_WIDE_STOP
        from apps.billing.gating.services.stop_signal_service import (
            CLEAR_RECONCILED, StopSignalService)
        if crossed:
            StopSignalService.drive_stop(owner_id, tenant, reason=CUSTOMER_WIDE_STOP,
                                         balance_micros=basis_micros)
            return LiveCounter.ensure_stop_flag(owner_id, CUSTOMER_WIDE_STOP)
        return LiveCounter.resume(owner_id, tenant, reason=CLEAR_RECONCILED,
                                  balance_micros=basis_micros)

    @staticmethod
    def reconcile(owner_id, tenant, *, now=None):
        """MIN/MAX-merge the owner's live counter toward the durable ledger
        and drive the bottom-line signal catch-up — ONE op, dispatching on
        the tenant's billing mode (prepaid wallet MIN-merge / postpaid month
        MAX-merge). Returns ``{"flag_realigned": bool}`` (the #44 §C.2 patrol
        outcome) on a completed pass, None on failure. ``now`` scopes the
        postpaid month (beat callers omit it)."""
        if tenant.billing_mode == "postpaid":
            return LiveCounter._reconcile_postpaid(owner_id, tenant, now=now)
        return LiveCounter._reconcile_prepaid(owner_id, tenant)

    @staticmethod
    def _reconcile_prepaid(owner_id, tenant):
        """MIN-merge the prepaid live balance toward the durable wallet balance.
        Holds lock_for_billing(owner) so a concurrent credit() cannot be erased
        by the read→merge (D8): the durable balance is read under the lock the
        credit/drawdown paths also take.

        Signal catch-up (#39): the reconciled position drives the ledger both
        ways — a missed stop is SET, a stale stop is cleared. The decision
        basis is the merged live value when Redis answered (the conservative
        view, matching the fast lane) and the DURABLE balance when Redis is
        blind, so the bottom-line signal never depends on Redis health. The
        transitions run inside the billing lock, serializing against the
        credit/drawdown paths so a concurrent re-cross cannot interleave a
        stale transition.

        #44 (delivery spec §C.1): the soft family gets the SAME bottom-line
        power, both directions — a soft crossing whose detection was torn
        down (crashed drawdown handler, dropped savepoint) is re-driven here
        from the reconciled position, and a stale one is cleared.

        Arrival signals OFF (#46, §E): the COUNTER jobs (drift read,
        MIN-merge/seed) are part of the fast lane and skip; the signal
        catch-up + flag re-alignment below are the durable lane — they never
        switch off, and run on the durable balance as their basis."""
        if not enforcing(tenant):
            return None
        lane_on = arrival_signals_on(tenant)
        from django.db import transaction
        from apps.billing.locking import lock_for_billing
        from apps.billing.queries import (get_customer_balance,
                                          get_customer_soft_min_balance)
        try:
            before = None
            if lane_on:
                try:
                    before = LiveCounter._read_livebal(owner_id)
                except Exception:
                    pass  # Redis blind — the durable bottom line below still runs
            with transaction.atomic():
                lock_for_billing(owner_id)  # serialize vs credit/drawdown
                durable = int(get_customer_balance(owner_id))
                if before is not None and abs(before - durable) > DRIFT_ALERT_MICROS:
                    logger.error("live_counter.drift_spike", extra={"data": {
                        "owner_id": str(owner_id), "mode": "prepaid",
                        "live_micros": before, "durable_micros": durable}})
                v = None
                if lane_on:
                    try:
                        v = int(_client().eval(_RECONCILE_MIN, 1, _livebal_key(owner_id),
                                               durable, COUNTER_TTL_SECONDS))
                    except Exception:
                        logger.warning("live_counter.reconcile_redis_blind",
                                       extra={"data": {"owner_id": str(owner_id),
                                                       "mode": "prepaid"}})
                basis = v if v is not None else durable
                realigned = LiveCounter._reconcile_transitions(
                    owner_id, tenant,
                    LiveCounter._crossed("prepaid", basis, owner_id, tenant),
                    basis)
                from apps.billing.gating.services.stop_signal_service import (
                    CLEAR_RECONCILED, StopSignalService)
                soft = get_customer_soft_min_balance(owner_id, tenant.id)
                if past_floor(basis, soft):
                    StopSignalService.drive_soft_crossed(
                        owner_id, tenant, balance_micros=basis,
                        soft_min_balance_micros=soft)
                else:
                    StopSignalService.drive_soft_cleared(
                        owner_id, tenant, reason=CLEAR_RECONCILED,
                        balance_micros=basis, soft_min_balance_micros=soft)
                return {"flag_realigned": realigned}
        except Exception:
            logger.warning("live_counter.reconcile_prepaid_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return None

    @staticmethod
    def _reconcile_postpaid(owner_id, tenant, now=None):
        """MAX-merge the postpaid live spend toward the durable owner-aggregated
        month-to-date billed total.

        Signal catch-up (#39): mirrors the prepaid pass — the merged spend
        (or the durable month total when Redis is blind) drives the ledger
        both ways, so a budget-cap stop missed by the fast lane is SET here
        and a stale one (incl. MONTH ROLLOVER: the new month's livespend is
        low, and the stop flag is NOT month-scoped) is cleared within one
        cycle. No soft-family leg: the soft floor is a wallet line,
        prepaid-only.

        Arrival signals OFF (#46, §E): the counter jobs (drift read,
        MAX-merge) skip with the fast lane; the durable-basis signal
        catch-up + flag re-alignment below never switch off."""
        if not enforcing(tenant):
            return None
        lane_on = arrival_signals_on(tenant)
        from django.utils import timezone
        from apps.metering.queries import get_billing_owner_billed_total
        now = now or timezone.now()
        label, start, end = month_label_bounds(now)
        try:
            durable = int(get_billing_owner_billed_total(tenant.id, owner_id, start, end))
            before = None
            if lane_on:
                try:
                    before = LiveCounter._read_livespend(owner_id, label)
                except Exception:
                    pass  # Redis blind — the durable bottom line below still runs
            if before is not None and abs(before - durable) > DRIFT_ALERT_MICROS:
                logger.error("live_counter.drift_spike", extra={"data": {
                    "owner_id": str(owner_id), "mode": "postpaid",
                    "live_micros": before, "durable_micros": durable}})
            v = None
            if lane_on:
                try:
                    v = int(_client().eval(_RECONCILE_MAX, 1, _livespend_key(owner_id, label),
                                           durable, COUNTER_TTL_SECONDS))
                except Exception:
                    logger.warning("live_counter.reconcile_redis_blind",
                                   extra={"data": {"owner_id": str(owner_id),
                                                   "mode": "postpaid"}})
            basis = v if v is not None else durable
            realigned = LiveCounter._reconcile_transitions(
                owner_id, tenant,
                LiveCounter._crossed("postpaid", basis, owner_id, tenant),
                0)  # postpaid has no balance; spend never rides balance fields
            return {"flag_realigned": realigned}
        except Exception:
            logger.warning("live_counter.reconcile_postpaid_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return None

    # ---- raw counter reads (module-internal; outsiders use read()) ----
    @staticmethod
    def _read_livebal(owner_id):
        v = _client().get(_livebal_key(owner_id))
        return int(v) if v is not None else None

    @staticmethod
    def _read_livespend(owner_id, label):
        v = _client().get(_livespend_key(owner_id, label))
        return int(v) if v is not None else None

    # ---- budget counter mechanics (D3/D3b) ----
    @staticmethod
    def budget_read(tenant_id, customer_id, *, now=None):
        """The seat's month-to-date budget counter, rebuilding from the
        durable ledger on a missing key (and best-effort seeding it — a
        Redis write failure still returns the authoritative Postgres total).
        A Redis READ failure raises: the caller (BudgetService.check) owns
        the fail-open/fail-closed policy."""
        from django.utils import timezone
        label, start, end = month_label_bounds(now or timezone.now())
        key = _budget_key(customer_id, label)
        val = _client().get(key)
        if val is not None:
            return int(val)
        from apps.metering.queries import get_customer_cost_totals
        total = get_customer_cost_totals(tenant_id, customer_id, start, end)["billed_cost_micros"]
        try:
            _client().set(key, int(total), ex=COUNTER_TTL_SECONDS)
        except Exception:
            pass
        return total

    @staticmethod
    def budget_incr(tenant_id, customer_id, amount_micros, *, now=None):
        """INCRBY the seat's period counter; returns (old, new, label).
        Missing key: in the production drawdown path this runs AFTER the
        UsageEvent is committed, so the durable total already INCLUDES this
        event — rebuild to that total (do NOT add amount again, or we
        double-count). Redis errors propagate: the caller
        (BudgetService.record_usage_spend) is fully fail-open."""
        from django.utils import timezone
        label, start, end = month_label_bounds(now or timezone.now())
        key = _budget_key(customer_id, label)
        v = _client().eval(_INCR_IF_PRESENT, 1, key, int(amount_micros),
                           COUNTER_TTL_SECONDS)
        if v is not None:
            new = int(v)
            return new - amount_micros, new, label
        from apps.metering.queries import get_customer_cost_totals
        new = get_customer_cost_totals(tenant_id, customer_id, start, end)["billed_cost_micros"]
        _client().set(key, int(new), ex=COUNTER_TTL_SECONDS)
        return max(0, new - amount_micros), new, label

    @staticmethod
    def budget_reconcile(tenant_id, customer_id, *, now=None):
        """MAX-merge the seat's budget counter toward the durable in-month
        billed total (P1, D8/I7: the monotonic merge — an absolute SET could
        erase an in-flight INCR mid-burst, transiently re-allowing over-cap
        spend; MAX never lowers, and the month-rollover label change is the
        only legitimate decrease).

        NOTE on locking: unlike the prepaid reconcile, this does NOT take
        lock_for_billing(owner) — the concurrent writer (``budget_incr`` via
        the drawdown tail) runs outside that lock and is keyed on the SEAT,
        so the lock would not serialize it. The atomic MAX-merge is what
        makes this race-free. Returns (durable_total, label) for the
        caller's alert pass; Redis errors propagate (the caller logs and
        skips its alerts)."""
        from django.utils import timezone
        from apps.metering.queries import get_customer_cost_totals
        label, start, end = month_label_bounds(now or timezone.now())
        total = int(get_customer_cost_totals(
            tenant_id, customer_id, start, end)["billed_cost_micros"] or 0)
        _client().eval(_RECONCILE_MAX, 1, _budget_key(customer_id, label),
                       total, COUNTER_TTL_SECONDS)
        return total, label

    # ---- enforcement-mode transition cleanup (D17) ----
    @staticmethod
    def cleanup(tenant):
        """Delete the non-month-scoped Tier-2 Redis keys (livebal + stop flag)
        for every owner of a tenant (D17). Call on an enforcement_mode
        TRANSITION so a re-enable / mode change never reads a STALE stop flag
        (which could wrongly durably-suspend) or a stale prepaid balance
        (62-day TTL). The month-scoped counters (livespend, budget)
        self-reset monthly, are reconcile-corrected, and are short-circuited
        while mode==off, so they need no explicit cleanup. Best-effort.

        The durable signal ledger must not carry a stale OPEN episode across
        the transition either (#39) — that ORM write belongs to
        StopSignalService (its silent bulk close, D5), called here."""
        from apps.platform.customers.models import Customer
        try:
            client = _client()
            for oid in Customer.all_objects.filter(tenant_id=tenant.id).values_list("id", flat=True):
                client.delete(_livebal_key(oid), _stop_key(oid))
        except Exception:
            logger.warning("live_counter.cleanup_failed",
                           extra={"data": {"tenant_id": str(tenant.id)}})
        try:
            from apps.billing.gating.services.stop_signal_service import (
                CLEAR_ENFORCEMENT_MODE_TRANSITION, StopSignalService)
            StopSignalService.close_all_silently(
                tenant, reason=CLEAR_ENFORCEMENT_MODE_TRANSITION)
        except Exception:
            logger.warning("live_counter.cleanup_ledger_failed",
                           extra={"data": {"tenant_id": str(tenant.id)}})


class Door:
    """The D4 TEST DOOR — the deliberate, TEST-ONLY entry for fabricating
    live-counter state (lane divergence, orphan flags, drifted counters)
    without leaking key formats into ~30 scattered import sites.

    TEST-ONLY: production code must never touch this class — pinned by
    ``apps/billing/tests/test_live_counter_perimeter.py``. Pins keep running
    against REAL Redis (same DB the module writes) + real Lua: a faithful
    fake would be a second Redis implementation — the twin-maintenance
    disease #111 cures. For Redis-down tests, monkeypatch ``_client`` (the
    single seam, D4). Key formats themselves are frozen once, in the
    module's own pin test — not here, not anywhere else."""

    # -- prepaid live balance --
    @staticmethod
    def set_balance(owner_id, micros):
        _client().set(_livebal_key(owner_id), int(micros), ex=COUNTER_TTL_SECONDS)

    @staticmethod
    def incr_balance(owner_id, delta_micros):
        """Relative drain/inflate — models honest concurrent traffic moving
        the counter between two observations (negative = drain)."""
        _client().incrby(_livebal_key(owner_id), int(delta_micros))

    @staticmethod
    def balance(owner_id):
        return LiveCounter._read_livebal(owner_id)

    # -- postpaid month-to-date live spend --
    @staticmethod
    def set_spend(owner_id, micros, *, now=None):
        from django.utils import timezone
        label, _, _ = month_label_bounds(now or timezone.now())
        _client().set(_livespend_key(owner_id, label), int(micros),
                      ex=COUNTER_TTL_SECONDS)

    @staticmethod
    def spend(owner_id, *, now=None):
        from django.utils import timezone
        label, _, _ = month_label_bounds(now or timezone.now())
        return LiveCounter._read_livespend(owner_id, label)

    # -- customer-wide stop flag --
    @staticmethod
    def plant_stop(owner_id, reason, *, ttl=True):
        """Plant the cooperative stop flag directly — an orphan (ambient
        rollback survivor, Redis-flush leftover) when ttl=False, or a
        normally-planted flag when ttl=True."""
        if ttl:
            _client().set(_stop_key(owner_id), reason, ex=COUNTER_TTL_SECONDS)
        else:
            _client().set(_stop_key(owner_id), reason)

    @staticmethod
    def stop_reason(owner_id):
        """The raw flag value (None = no flag) — presence/absence checks
        without the verdict dressing of ``LiveCounter.read``."""
        v = _client().get(_stop_key(owner_id))
        if v is None:
            return None
        return v.decode() if isinstance(v, bytes) else str(v)

    @staticmethod
    def delete_stop(owner_id):
        """A BARE flag delete — models a Redis flush / blind window tearing
        the flag down WITHOUT closing the ledger episode (unlike every real
        clearing path, which goes through ``resume``)."""
        _client().delete(_stop_key(owner_id))

    # -- seat budget counter --
    @staticmethod
    def set_budget(customer_id, micros, *, now=None):
        from django.utils import timezone
        label, _, _ = month_label_bounds(now or timezone.now())
        _client().set(_budget_key(customer_id, label), int(micros),
                      ex=COUNTER_TTL_SECONDS)

    @staticmethod
    def budget(customer_id, *, now=None):
        from django.utils import timezone
        label, _, _ = month_label_bounds(now or timezone.now())
        v = _client().get(_budget_key(customer_id, label))
        return int(v) if v is not None else None
