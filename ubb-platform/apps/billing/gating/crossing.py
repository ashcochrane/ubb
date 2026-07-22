"""The ONE owner of the Crossing decision (#110).

Every lane that compares a balance/spend value against a configured money
line imports THESE predicates — the fast lane (``record_usage_debit`` /
``HoldService.acquire``), the durable lane (``handlers.py`` drawdown), the
start-gate (``RiskService``), reconcile (``LiveLedgerService``), the upward
repair (``repair.py``), the budget gate (``BudgetService.check``) and the
dispute clawback (Stripe webhooks). Pure module: no ORM, no Redis — the
callers resolve the inputs (floor magnitudes, BudgetConfig rows, counter
values); this module owns only the compare, so the sign conventions live in
exactly one place.

The two orientations:

  WALLET (prepaid / meter_only — the balance FALLS). The configured floor is
  a magnitude, ``min_balance_micros``; the comparable line is its negation
  (``floor_line``). PAST the floor = balance strictly BELOW the line;
  RECOVERED = balance at/above it (the exact negation — recovery on the line
  itself). A None floor (an unconfigured soft floor) has no line: never
  past, never crossed, always recovered.

  BUDGET (postpaid — the spend RISES). The stop line is
  ``cap_micros * hard_stop_pct // 100`` and past = spend AT/OVER it.
  ``budget_stop_threshold`` resolves the line from a BudgetConfig and owns
  the ``enforce_mode`` semantics: an advisory (non-enforcing) budget can
  NEVER cross — it alerts (``BudgetService.emit_threshold_alerts``, which is
  level-based and deliberately not this module's concern) but never stops.
  Pre-#110 the live lanes ignored ``enforce_mode`` (the drift this module
  retires); every lane now shares the ``BudgetService.check`` semantics.

Month math rides along because the postpaid crossing is month-scoped: the
``YYYY-MM`` label/bounds and the effective-month guard were re-derived in
three places with their own tz handling; this is the one copy.

ADR 0002 note: the floor itself stays policy-in-code — this module changes
WHERE the compare lives, never what the policy is.
"""
from datetime import timezone as _utc_tz


# --- wallet floor (prepaid / meter_only; balance FALLS across the line) ----

def floor_line(min_balance_micros):
    """The comparable wallet line: a balance below ``-min_balance`` is past
    the floor. This is the value ``LiveLedgerService._threshold`` pre-resolves
    for the batch/live compare (``crossed_live``)."""
    return -int(min_balance_micros)


def past_floor(balance_micros, min_balance_micros) -> bool:
    """Level form: strictly below the line (start-gate, reconcile basis,
    repair wedge check). None floor (unconfigured soft floor) = never past."""
    if min_balance_micros is None:
        return False
    return balance_micros < -min_balance_micros


def crossed_floor(old_balance_micros, new_balance_micros, min_balance_micros) -> bool:
    """Transition form (the durable drawdown lane): old at/above the line AND
    new below it — fires exactly once per descent, never on a repeat debit
    already past the line. None floor = never crosses."""
    if min_balance_micros is None:
        return False
    return (old_balance_micros >= -min_balance_micros
            and new_balance_micros < -min_balance_micros)


def recovered_floor(balance_micros, min_balance_micros) -> bool:
    """Recovery: at/above the line — the exact negation of ``past_floor``, so
    the stop and resume edges can never gap or overlap. A None floor
    (soft floor unconfigured mid-episode) counts as recovered: there is no
    line left to be past (#40 §F)."""
    if min_balance_micros is None:
        return True
    return balance_micros >= -min_balance_micros


# --- budget stop (postpaid; spend RISES across the stop line) --------------

def budget_stop_threshold(cfg):
    """The postpaid stop line for a resolved BudgetConfig, or None when the
    owner can never cross: no config, cap <= 0, or — the #110 unification —
    ``enforce_mode`` not 'enforcing' (an advisory budget alerts, never
    stops; the ``BudgetService.check`` semantics, now shared by every lane)."""
    if cfg is None or cfg.cap_micros <= 0:
        return None
    if cfg.enforce_mode != "enforcing":
        return None
    return cfg.cap_micros * cfg.hard_stop_pct // 100


def past_budget_stop(spend_micros, stop_threshold_micros) -> bool:
    """Level form: month-to-date spend AT/OVER the stop line. None threshold
    (from ``budget_stop_threshold``) = can never cross."""
    if stop_threshold_micros is None:
        return False
    return spend_micros >= stop_threshold_micros


# --- the live-counter dispatch (fast lane / hold batch / reconcile) --------

def crossed_live(mode, value_micros, threshold_micros) -> bool:
    """The live-counter compare, one orientation per mode, against a
    threshold pre-resolved ONCE per owner (``LiveLedgerService._threshold``
    — so a batch caller pays one ORM lookup, not one per item):

      postpaid -> ``threshold`` is the budget stop line; spend at/over it.
      prepaid  -> ``threshold`` is ``floor_line(min_balance)``; balance
                  strictly below it (same convention as ``past_floor`` —
                  test_crossing cross-pins the two forms).

    None threshold = can never cross."""
    if threshold_micros is None:
        return False
    if mode == "postpaid":
        return past_budget_stop(value_micros, threshold_micros)
    return value_micros < threshold_micros


# --- month scope (the postpaid crossing is month-keyed) --------------------

def month_label_bounds(now):
    """(label 'YYYY-MM', start date, end date exclusive) for now's month."""
    d = now.date()
    start = d.replace(day=1)
    end = (start.replace(year=start.year + 1, month=1, day=1) if start.month == 12
           else start.replace(month=start.month + 1, day=1))
    return f"{start.year:04d}-{start.month:02d}", start, end


def same_month(effective_at, now) -> bool:
    """True when ``effective_at`` falls in the same calendar month as ``now``
    (I9: a prior-month backdated event must not inflate THIS month's live
    counter). None = no effective instant = current month. An aware datetime
    is normalized to UTC first; a naive one compares as-is (legacy payloads,
    byte-for-byte the pre-#110 behavior of every copy)."""
    if effective_at is None:
        return True
    eff = (effective_at.astimezone(_utc_tz.utc)
           if effective_at.tzinfo else effective_at)
    return (eff.year, eff.month) == (now.year, now.month)
