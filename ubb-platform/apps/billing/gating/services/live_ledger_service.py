"""Tier-2 synchronous live-spend/balance ledger (WS1 / P2).

The SHARED, owner-keyed Redis counter that ``record_usage`` decrements
synchronously so the 200 response can express a real wallet/budget stop verdict
(P3 reads it; P2 only maintains it). Gated by ``enforcing(tenant)`` — when
the tenant's ``enforcement_mode`` is ``off`` every method is a cheap no-op and
behavior is byte-for-byte unchanged.

Two parallel counters, one per billing mode, both keyed on the resolved billing
OWNER (``resolve_billing_owner``) so a pooled business is one counter across all
its seats and an allocated/individual owner is its own:

  PREPAID  ``ubb:livebal:{owner}``        = micros of spendable balance.
           DECRBY on usage, INCRBY on credit. Tracks (credits − recorded usage),
           which is ``durable_balance − undebited_usage`` ≤ durable balance, so
           the live view is the CONSERVATIVE (lower) one. Reconcile MIN-merges
           toward the durable balance (only LOWERS), so a credit that the fast
           path missed cannot be re-raised by reconcile — therefore EVERY credit
           site MUST call ``credit()`` (the three mandatory hooks in P2.3). A
           missed credit fails SAFE (over-restrictive), a missed debit is
           absorbed by the MIN-merge.

  POSTPAID ``ubb:livespend:{owner}:{YYYY-MM}`` = micros of month-to-date spend.
           INCRBY on usage. Reconcile MAX-merges toward the durable
           owner-aggregated billed total (only RAISES), catching the first-use
           under-count (the counter is born at the first event, not the
           month-to-date total) within one reconcile cycle.

SEEDING (the one deliberate over-permissive window): the prepaid counter seeds
from the DURABLE wallet balance, which at first-use may still be high by the
usage that is recorded-but-not-yet-async-debited (handlers.py drains the debit
after record_usage commits). The live counter is therefore over-permissive by
at most that one outbox-drain window, bounded and reconcile-corrected, and
backstopped by the durable START-GATE (RiskService reads the real wallet for a
NEW run). This is the reworded I2 contract (a bounded window, not an absolute
bound) — chosen over an anti-join seed because the latter introduces a
concurrency race that the LOWER-only MIN-merge cannot repair.

KEY/CLIENT (D9): the ubb:* keys are RAW-client only (redis.from_url + Lua EVAL),
never touched via django's ``cache.*`` — so they are immune to django-redis's
``:1:`` version prefix. (The existing seat-keyed ``budget:*`` counter stays on
the django cache; the postpaid OWNER counter here is a SEPARATE ubb: key.)
"""
import logging

from django.conf import settings

from apps.billing.gating.crossing import (budget_stop_threshold, crossed_live,
                                          floor_line, month_label_bounds,
                                          past_floor, recovered_floor,
                                          same_month)
from apps.platform.tenants.flags import arrival_signals_on, enforcing

logger = logging.getLogger("ubb.billing")

LEDGER_TTL_SECONDS = 62 * 24 * 3600  # current month + buffer; refreshed on every write

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

# Prepaid credit (top-up / refund-reversal / manual). Applies ONLY if the key
# is seeded; an unseeded credit is dropped because first-use will seed from the
# already-credited durable balance. ARGV[1] may be negative. Returns new value
# or nil. KEYS[1]=livebal; ARGV[1]=amount; ARGV[2]=ttl.
_CREDIT_IF_PRESENT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    local v = redis.call('INCRBY', KEYS[1], ARGV[1])
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return v
end
return nil
"""

# Prepaid reconcile MIN-merge: only LOWERS toward the durable balance (never
# raises — credits are applied via _CREDIT_IF_PRESENT, so reconcile must not
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
# ARGV[1]=amount; ARGV[2]=ttl. Returns the running month-to-date spend.
_SPEND_INCR = """
local v = redis.call('INCRBY', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return v
"""

# Postpaid reconcile MAX-merge: only RAISES toward the durable owner-aggregated
# month total (catches the first-use under-count). Mirror of the budget
# reconcile in budget_service. KEYS[1]=livespend; ARGV[1]=durable_total; ARGV[2]=ttl.
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


class LiveLedgerService:
    # ---- synchronous usage hook (called from record_usage) ----
    @staticmethod
    def record_usage_debit(owner_id, tenant, billed_cost_micros, *, effective_at=None, now=None):
        """Apply this event to the owner's live counter, synchronously, and
        return the customer-wide stop verdict.

        P3: if this event drives the counter across the threshold (prepaid
        wallet floor / postpaid budget cap) the owner-keyed stop flag is SET
        (cooperative — never rolls back this event; I3). The returned dict
        carries {mode, balance_micros|spend_micros, key, stop, stop_reason,
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
            return LiveLedgerService.read_stop(owner_id, tenant)
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
                v = int(_client().eval(_SPEND_INCR, 1, key, int(billed_cost_micros), LEDGER_TTL_SECONDS))
                base = {"mode": "postpaid", "spend_micros": v, "key": key}
                mode = "postpaid"
            else:
                # prepaid / meter_only: mirror the async wallet drawdown branch.
                from apps.billing.queries import get_customer_balance
                key = _livebal_key(owner_id)
                seed = int(get_customer_balance(owner_id))
                v = int(_client().eval(_SEED_AND_DECR, 1, key, seed, int(billed_cost_micros), LEDGER_TTL_SECONDS))
                base = {"mode": "prepaid", "balance_micros": v, "key": key}
                mode = "prepaid"
            # Set (never clear) the cooperative stop flag on a crossing; a
            # non-crossing event must not clear a flag a sibling run set — the
            # flag lifts only on recovery (credit / reconcile).
            if LiveLedgerService._crossed(mode, v, owner_id, tenant):
                from apps.platform.tasks.reasons import CUSTOMER_WIDE_STOP
                opened = LiveLedgerService._set_stop(
                    owner_id, CUSTOMER_WIDE_STOP, tenant=tenant,
                    balance_micros=v if mode == "prepaid" else 0)
                if opened is not None:
                    # THIS debit won the stop transition — the caller's event
                    # is the episode's tipping event (#41 stop-context).
                    base["stop_episode_opened"] = opened
            base.update(LiveLedgerService.read_stop(owner_id, tenant))
            return base
        except Exception:
            logger.warning("live_ledger.debit_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return None

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

        Extracted out of ``_crossed`` so a caller processing MANY items for the
        SAME owner in one call (HoldService.acquire) can resolve this ONCE per
        call and compare every item's post-hold value against it in plain
        Python, instead of re-querying per item."""
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
        HoldService.acquire)."""
        return crossed_live(
            mode, value, LiveLedgerService._threshold(mode, owner_id, tenant))

    @staticmethod
    def _set_stop(owner_id, reason, tenant=None, balance_micros=0):
        """Set the customer-wide cooperative stop flag, and on the unset->set
        TRANSITION only (SET ... NX on the flag key itself is the transition
        detector — no companion key needed) fan out two best-effort side
        effects: a ``ubb:stopchan:{owner_id}`` Redis pub/sub publish (Plan 2's
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
        path (record_usage_debit / HoldService.acquire). The pub/sub publish
        is guarded by try/except (not a DB statement, so that suffices).
        drive_stop opens its own ``transaction.atomic`` — a SAVEPOINT inside
        the sync path's ambient transaction (the budget_service
        .check_thresholds pattern): a DB-level failure inside it (deadlock,
        timeout) rolls back to the savepoint cleanly, so the ambient Postgres
        transaction stays usable and the caller's money-path statements are
        never collaterally rolled back by stop-signal bookkeeping. (The
        savepoint cannot survive a DEAD CONNECTION — but then the whole outer
        transaction is doomed regardless; that is not a gap specific to this
        call.) A transition lost to the rollback is re-driven by the durable
        lane / reconcile — late, never lost.

        tenant is optional: a call site without tenant context (there is
        none today, but keeping this defensive) degrades to pub/sub-only
        rather than crashing. balance_micros is the crossing balance the
        detecting lane saw (prepaid live value; postpaid passes 0) — it rides
        the folded suspension's CustomerSuspended event.

        Returns the episode_seq drive_stop opened when THIS call won the
        ledger transition (#41 tipping-event attribution), else None.
        """
        client = _client()
        was_new = client.set(_stop_key(owner_id), reason, ex=LEDGER_TTL_SECONDS, nx=True)
        if not was_new:
            client.expire(_stop_key(owner_id), LEDGER_TTL_SECONDS)
            return None
        try:
            client.publish(f"ubb:stopchan:{owner_id}", reason)
        except Exception:
            logger.warning("live_ledger.stop_publish_failed",
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
                logger.warning("live_ledger.stop_event_failed",
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
                                    ex=LEDGER_TTL_SECONDS, nx=True)
            if not was_absent:
                client.expire(_stop_key(owner_id), LEDGER_TTL_SECONDS)
            return bool(was_absent)
        except Exception:
            logger.warning("live_ledger.ensure_stop_flag_failed",
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
            logger.warning("live_ledger.clear_stop_failed",
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
                        and owner.suspension_reason in LiveLedgerService._MONEY_SUSPEND_REASONS):
                    owner.status = "active"
                    owner.suspension_reason = ""
                    owner.save(update_fields=["status", "suspension_reason", "updated_at"])
        except Exception:
            logger.warning("live_ledger.unsuspend_failed",
                           extra={"data": {"owner_id": str(owner_id)}})

    @staticmethod
    def read_stop(owner_id, tenant) -> dict:
        """Current customer-wide stop verdict. Short-circuits to not-stopped
        when enforcement is off — BEFORE touching Redis (D17)."""
        off = {"stop": False, "stop_reason": None, "stop_scope": None}
        if not enforcing(tenant):
            return off
        try:
            v = _client().get(_stop_key(owner_id))
        except Exception:
            return off
        if v is None:
            return off
        reason = v.decode() if isinstance(v, bytes) else str(v)
        return {"stop": True, "stop_reason": reason, "stop_scope": "customer"}

    # ---- prepaid credit hook (top-up / refund-reversal / manual credit) ----
    @staticmethod
    def credit(owner_id, tenant, amount_micros):
        """INCRBY the prepaid live balance by amount_micros (may be negative).
        No-op for postpaid (no spendable balance) and when disabled. Best-effort
        — but note a DROPPED credit fails over-restrictive (MIN-merge cannot
        re-raise it), so this is called from EVERY credit site.

        Recovery (P3 + #39 §E): a positive credit that lifts the balance back
        to/above the floor is the RESUME fast lane — it drives the clearing
        transition on the signal ledger (the winner emits ``stop.cleared``
        with the episode it closes) and deletes the cooperative stop flag.
        The live counter decides the re-cross when Redis answered; when the
        fast INCRBY failed or found no seeded key, the DURABLE balance decides
        instead — every durable credit site calls this hook, so a top-up that
        re-crosses the floor during a Redis blind window still resumes now,
        not an hour later at reconcile. (A negative credit / grant-expiry
        never clears.)"""
        if not enforcing(tenant) or tenant.billing_mode == "postpaid" or amount_micros == 0:
            return
        v = None
        try:
            v = _client().eval(_CREDIT_IF_PRESENT, 1, _livebal_key(owner_id),
                               int(amount_micros), LEDGER_TTL_SECONDS)
        except Exception:
            logger.warning("live_ledger.credit_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
        if amount_micros <= 0:
            return
        try:
            from apps.billing.queries import get_customer_min_balance, get_customer_balance
            from apps.billing.gating.services.stop_signal_service import (
                CLEAR_BALANCE_RECOVERED, StopSignalService)
            floor = get_customer_min_balance(owner_id, tenant.id)
            if v is not None:
                clearance_balance = int(v)
            else:
                # Redis blind or unseeded counter: the durable balance is the
                # guaranteed lane's view of the re-cross.
                clearance_balance = int(get_customer_balance(owner_id))
            if recovered_floor(clearance_balance, floor):
                StopSignalService.drive_clear(owner_id, tenant,
                                              reason=CLEAR_BALANCE_RECOVERED,
                                              balance_micros=clearance_balance)
                LiveLedgerService._clear_stop(owner_id)
                # P6b/D15: un-suspend on the DURABLE wallet, NOT the live
                # counter — a dispute/refund debit is not mirrored to the
                # live counter, so v can over-state and would otherwise flip
                # status active while the true balance is still below floor.
                if recovered_floor(get_customer_balance(owner_id), floor):
                    LiveLedgerService._maybe_unsuspend(owner_id)
            # #40 §F — the soft floor's credit-side clearing, independent of
            # the hard pair (an owner can be past the soft line without ever
            # having stopped).
            LiveLedgerService._drive_soft_clear_if_recovered(
                owner_id, tenant, clearance_balance, CLEAR_BALANCE_RECOVERED)
        except Exception:
            logger.warning("live_ledger.credit_recovery_failed",
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
        leg in ``reconcile_prepaid`` (#44 §C.1)."""
        from apps.billing.queries import get_customer_soft_min_balance
        from apps.billing.gating.services.stop_signal_service import StopSignalService
        soft = get_customer_soft_min_balance(owner_id, tenant.id)
        if recovered_floor(balance_micros, soft):
            StopSignalService.drive_soft_cleared(
                owner_id, tenant, reason=reason,
                balance_micros=balance_micros, soft_min_balance_micros=soft)

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
            return LiveLedgerService.ensure_stop_flag(owner_id, CUSTOMER_WIDE_STOP)
        StopSignalService.drive_clear(owner_id, tenant, reason=CLEAR_RECONCILED,
                                      balance_micros=basis_micros)
        realigned = LiveLedgerService._clear_stop(owner_id)
        LiveLedgerService._maybe_unsuspend(owner_id)  # P6b/D15 backstop
        return realigned

    @staticmethod
    def reconcile_prepaid(owner_id, tenant):
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
        from the reconciled position, and a stale one is cleared. Returns
        ``{"flag_realigned": bool}`` (the §C.2 patrol outcome) on a completed
        pass, None on failure.

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
                    before = LiveLedgerService.read_prepaid(owner_id)
                except Exception:
                    pass  # Redis blind — the durable bottom line below still runs
            with transaction.atomic():
                lock_for_billing(owner_id)  # serialize vs credit/drawdown
                durable = int(get_customer_balance(owner_id))
                if before is not None and abs(before - durable) > DRIFT_ALERT_MICROS:
                    logger.error("live_ledger.drift_spike", extra={"data": {
                        "owner_id": str(owner_id), "mode": "prepaid",
                        "live_micros": before, "durable_micros": durable}})
                v = None
                if lane_on:
                    try:
                        v = int(_client().eval(_RECONCILE_MIN, 1, _livebal_key(owner_id),
                                               durable, LEDGER_TTL_SECONDS))
                    except Exception:
                        logger.warning("live_ledger.reconcile_redis_blind",
                                       extra={"data": {"owner_id": str(owner_id),
                                                       "mode": "prepaid"}})
                basis = v if v is not None else durable
                realigned = LiveLedgerService._reconcile_transitions(
                    owner_id, tenant,
                    LiveLedgerService._crossed("prepaid", basis, owner_id, tenant),
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
            logger.warning("live_ledger.reconcile_prepaid_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return None

    @staticmethod
    def reconcile_postpaid(owner_id, tenant, now=None):
        """MAX-merge the postpaid live spend toward the durable owner-aggregated
        month-to-date billed total.

        Signal catch-up (#39): mirrors reconcile_prepaid — the merged spend
        (or the durable month total when Redis is blind) drives the ledger
        both ways, so a budget-cap stop missed by the fast lane is SET here
        and a stale one (incl. MONTH ROLLOVER: the new month's livespend is
        low, and the stop flag is NOT month-scoped) is cleared within one
        cycle. Returns ``{"flag_realigned": bool}`` on a completed pass
        (#44 §C.2), None on failure. No soft-family leg: the soft floor is a
        wallet line, prepaid-only.

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
                    before = LiveLedgerService.read_postpaid(owner_id, now=now)
                except Exception:
                    pass  # Redis blind — the durable bottom line below still runs
            if before is not None and abs(before - durable) > DRIFT_ALERT_MICROS:
                logger.error("live_ledger.drift_spike", extra={"data": {
                    "owner_id": str(owner_id), "mode": "postpaid",
                    "live_micros": before, "durable_micros": durable}})
            v = None
            if lane_on:
                try:
                    v = int(_client().eval(_RECONCILE_MAX, 1, _livespend_key(owner_id, label),
                                           durable, LEDGER_TTL_SECONDS))
                except Exception:
                    logger.warning("live_ledger.reconcile_redis_blind",
                                   extra={"data": {"owner_id": str(owner_id),
                                                   "mode": "postpaid"}})
            basis = v if v is not None else durable
            realigned = LiveLedgerService._reconcile_transitions(
                owner_id, tenant,
                LiveLedgerService._crossed("postpaid", basis, owner_id, tenant),
                0)  # postpaid has no balance; spend never rides balance fields
            return {"flag_realigned": realigned}
        except Exception:
            logger.warning("live_ledger.reconcile_postpaid_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return None

    # ---- read helpers (used by P3 / tests) ----
    @staticmethod
    def read_prepaid(owner_id):
        v = _client().get(_livebal_key(owner_id))
        return int(v) if v is not None else None

    @staticmethod
    def read_postpaid(owner_id, now=None):
        from django.utils import timezone
        label, _, _ = month_label_bounds(now or timezone.now())
        v = _client().get(_livespend_key(owner_id, label))
        return int(v) if v is not None else None

    @staticmethod
    def cleanup_keys(tenant):
        """Delete the non-month-scoped Tier-2 Redis keys (livebal + stop flag)
        for every owner of a tenant (D17). Call on an enforcement_mode
        TRANSITION so a re-enable / mode change never reads a STALE stop flag
        (which could wrongly durably-suspend) or a stale prepaid balance (62-day
        TTL). The month-scoped livespend counter self-resets monthly, is
        reconcile-corrected, and is short-circuited while mode==off, so it
        needs no explicit cleanup. Best-effort."""
        from apps.platform.customers.models import Customer
        try:
            client = _client()
            for oid in Customer.all_objects.filter(tenant_id=tenant.id).values_list("id", flat=True):
                client.delete(_livebal_key(oid), _stop_key(oid))
        except Exception:
            logger.warning("live_ledger.cleanup_failed",
                           extra={"data": {"tenant_id": str(tenant.id)}})
        # #39: the durable signal ledger must not carry a stale OPEN episode
        # across an enforcement_mode transition — a stale 'stopped' row would
        # swallow the first real crossing's emission after re-enable. Silent
        # bulk close (no stop.cleared: the flip is config, not a re-cross);
        # episode_seq is preserved so episode ids never restart or collide.
        try:
            from django.utils import timezone
            from apps.billing.gating.models import StopSignalState
            from apps.billing.gating.services.stop_signal_service import (
                CLEAR_ENFORCEMENT_MODE_TRANSITION, STATE_CLEARED, STATE_STOPPED)
            now = timezone.now()
            StopSignalState.objects.filter(tenant_id=tenant.id, state=STATE_STOPPED).update(
                state=STATE_CLEARED, reason=CLEAR_ENFORCEMENT_MODE_TRANSITION,
                transitioned_at=now, updated_at=now)
        except Exception:
            logger.warning("live_ledger.cleanup_ledger_failed",
                           extra={"data": {"tenant_id": str(tenant.id)}})
