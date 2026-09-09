"""The ONE owner of the Crossing decision (#110), in the kernel's shared
package since #452 so a product and the kernel import the same compare.

Every path that compares a balance/spend value against a configured money
line imports THESE predicates — the real-time counter write
(``LiveCounter.debit``), the durable lane (``handlers.py`` drawdown), the
start-gate (``RiskService``), reconcile (``LiveCounter``), the upward
repair (``repair.py``), the budget gate (``BudgetService.check``), the
dispute clawback (Stripe webhooks) — and, for a unit of work's ceiling, the
recording path's live compare (``TaskService.accumulate_cost``), the patrol's
sweep, the analytics reached-count and the row's own assessment
(``Task.ceiling_assessment``). Pure module: no model, no query evaluated, no
Redis — the callers resolve the inputs (floor magnitudes, BudgetConfig rows,
counter values, a row's columns); this module owns only the compare, so the
sign conventions live in exactly one place. The one Django import it makes
(``ceiling_reached_q``) builds a filter expression and evaluates nothing.

It lived in billing until #452, which is exactly why the kernel's live path
grew an inline compare of its own that disagreed with it (slice 6 §1, §3):
a product cannot be imported by the kernel (ADR-001), so the one owner has
to sit where both can reach it.

The three orientations:

  WALLET (prepaid / meter_only — the balance FALLS). The configured floor is
  a magnitude, ``min_balance_micros``; the comparable line is its negation
  (``floor_line``). PAST the floor = balance strictly BELOW the line;
  RECOVERED = balance at/above it (the exact negation — recovery on the line
  itself). A None floor (an unconfigured soft floor) has no line: never
  past, never crossed, always recovered.

  BUDGET (postpaid — the spend RISES). The stop line is
  ``cap_micros * hard_stop_pct // 100`` and past = spend AT/OVER it.
  ``budget_stop_threshold`` resolves the line from a BudgetConfig and owns
  the ``enforce_mode`` semantics: an ``alert_only`` (non-blocking) budget can
  NEVER cross — it alerts (``BudgetService.emit_threshold_alerts``, which is
  level-based and deliberately not this module's concern) but never stops.
  Pre-#110 the live lanes ignored ``enforce_mode`` (the drift this module
  retires); every lane now shares the ``BudgetService.check`` semantics.

  CEILING (a unit of work's COGS bound — the known total RISES). Reached =
  known total AT/OVER the pinned ceiling, and the four-way assessment
  (``ceiling_status``) is the registry's own decision rule. See the section
  at the foot of the module for why the boundary is the whole subject.

Month math rides along because the postpaid crossing is month-scoped: the
``YYYY-MM`` label/bounds and the effective-month guard were re-derived in
three places with their own tz handling; this is the one copy.

ADR 0002 note: the floor itself stays policy-in-code — this module changes
WHERE the compare lives, never what the policy is.
"""
from datetime import timezone as _utc_tz
from typing import NamedTuple


# --- wallet floor (prepaid / meter_only; balance FALLS across the line) ----

def floor_line(min_balance_micros):
    """The comparable wallet line: a balance below ``-min_balance`` is past
    the floor. This is the value the live counter's ``_threshold``
    pre-resolves for the batch/live compare (``crossed_live``)."""
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
    ``enforce_mode`` not 'blocking' (an alert_only budget alerts, never
    stops; the ``BudgetService.check`` semantics, now shared by every lane)."""
    if cfg is None or cfg.cap_micros <= 0:
        return None
    if cfg.enforce_mode != "blocking":
        return None
    return cfg.cap_micros * cfg.hard_stop_pct // 100


def past_budget_stop(spend_micros, stop_threshold_micros) -> bool:
    """Level form: month-to-date spend AT/OVER the stop line. None threshold
    (from ``budget_stop_threshold``) = can never cross."""
    if stop_threshold_micros is None:
        return False
    return spend_micros >= stop_threshold_micros


# --- the live-counter dispatch (fast lane / reconcile) ---------------------

def crossed_live(mode, value_micros, threshold_micros) -> bool:
    """The live-counter compare, one orientation per mode, against a
    threshold pre-resolved ONCE per owner (the live counter's ``_threshold``
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


# --- the Ceiling (a unit of work's COGS bound; the known total RISES) -------
#
# AT OR ABOVE THE LINE STOPS, EVERYWHERE (#150 §10, slice 6 §3). Before #452
# this compare was spelled three times and two of them disagreed: the live
# ingest lane stopped a unit strictly ABOVE its ceiling while the patrol's
# sweep, the analytics reached-count and the registry's own decision rule all
# said at-or-above. A unit landing exactly on its ceiling therefore survived
# the event that landed it and was killed by the patrol within the hour, with
# no tipping event to attribute the stop to. `>=` is the comparison, so a
# ceiling is REACHED rather than exceeded — the registry's word.
#
# The known total is a FLOOR wherever the unit has unresolved costs, and the
# compare is against that floor deliberately: firing on the floor plus the
# unresolved count would kill work on a number nobody has stated, so the
# ceiling under-fires rather than over-fires and nothing is stopped for spend
# UBB cannot demonstrate. The four-way assessment below is what makes that
# silence readable — a ceiling that has not fired is visibly not the same as
# one shown to be safe.

def ceiling_reached(known_micros, ceiling_micros) -> bool:
    """Level form: the known total AT/OVER the ceiling. A None ceiling means
    no ceiling applies — never reached."""
    if ceiling_micros is None:
        return False
    return known_micros >= ceiling_micros


def ceiling_reached_q(known_column, ceiling_column):
    """The same compare as a queryset filter, for the callers that select
    ROWS rather than hold one — the patrol's sweep and the analytics
    reached-count. Spelled here so a query cannot say `>` where the row says
    `>=`; the work app's `TheRowAssessesItsOwnCeilingTest` pins the two forms
    to each other on real rows over every boundary shape.

    Django's expression classes are imported on call rather than at module
    top so the rest of this module stays importable without Django — it is
    still the compare and nothing else: no model, no row, nothing evaluated."""
    from django.db.models import F, Q
    return Q(**{f"{ceiling_column}__isnull": False,
                f"{known_column}__gte": F(ceiling_column)})


def ceiling_status(*, ceiling_micros, known_micros, unresolved_count) -> str:
    """The four-way assessment, exactly the registry's decision rule
    (`spend-controls.yaml`, `ceiling_status.value_semantics`; #158 §12.3):

      no ceiling applies                       -> not_applicable
      known at/over the ceiling, whatever
        remains unresolved                     -> ceiling_reached
      known below, something still unresolved  -> indeterminate
      known below, everything resolved         -> within_ceiling

    Known-over always fires (#150 §4.2): an unresolved cost can only ADD to
    a total that has already reached the line, so no later resolution can
    soften `ceiling_reached`. `indeterminate` is UBB having tried and been
    unable to tell — never that there was nothing to try (#158 §12.4) —
    which is why a missing ceiling answers first and answers the same
    whatever the cost."""
    from core.vocabulary import (
        CEILING_STATUS_CEILING_REACHED, CEILING_STATUS_INDETERMINATE,
        CEILING_STATUS_NOT_APPLICABLE, CEILING_STATUS_WITHIN_CEILING)
    if ceiling_micros is None:
        return CEILING_STATUS_NOT_APPLICABLE
    if ceiling_reached(known_micros, ceiling_micros):
        return CEILING_STATUS_CEILING_REACHED
    if unresolved_count > 0:
        return CEILING_STATUS_INDETERMINATE
    return CEILING_STATUS_WITHIN_CEILING


def ceiling_used_percentage(known_micros, ceiling_micros):
    """Whole percent of the ceiling the KNOWN total has used, rounded down so
    it never overstates; past the line it runs over 100. None where no
    ceiling applies, and None for a ceiling of zero — a share of nothing is
    not a share (the compare still says such a ceiling is reached).

    It is computed over the known total in EVERY evaluated state (#150 §9),
    so under `indeterminate` a reader must treat it as a floor: the status
    beside it is what says so, and this number never pretends otherwise."""
    if ceiling_micros is None or ceiling_micros <= 0:
        return None
    return known_micros * 100 // ceiling_micros


def ceiling_remaining_micros(known_micros, ceiling_micros):
    """The headroom left under the ceiling for the KNOWN total, never below
    zero: past the line there is none, and the percentage beside it is what
    says by how much. None where no ceiling applies."""
    if ceiling_micros is None:
        return None
    return max(ceiling_micros - known_micros, 0)


class CeilingAssessment(NamedTuple):
    """The three answers a unit's ceiling gives, travelling together: the
    status is what tells a reader how to read the two figures beside it
    (under `indeterminate` the percentage is a floor and the headroom a
    ceiling), so they are one value rather than three a caller could take
    half of."""
    status: str
    used_percentage: int | None
    remaining_micros: int | None


def ceiling_assessment(*, ceiling_micros, known_micros, unresolved_count):
    """The whole assessment for one row's three columns — what the row, the
    acknowledgement and the unit read all publish, composed once."""
    return CeilingAssessment(
        status=ceiling_status(ceiling_micros=ceiling_micros,
                              known_micros=known_micros,
                              unresolved_count=unresolved_count),
        used_percentage=ceiling_used_percentage(known_micros, ceiling_micros),
        remaining_micros=ceiling_remaining_micros(known_micros, ceiling_micros))


#: The wire names the assessment travels under, spelled once (the
#: `core.cost_totals` precedent for a key two products and the composition
#: layer all publish): the recording acknowledgement and both unit reads
#: render exactly these three, and a product may not import the API layer
#: to learn them.
CEILING_STATUS_KEY = "ceiling_status"
CEILING_USED_PERCENTAGE_KEY = "ceiling_used_percentage"
CEILING_REMAINING_MICROS_KEY = "ceiling_remaining_micros"


def ceiling_fields(assessment):
    """The three wire fields a `CeilingAssessment` becomes; `None` — no unit
    to assess — is three nulls."""
    if assessment is None:
        return {CEILING_STATUS_KEY: None, CEILING_USED_PERCENTAGE_KEY: None,
                CEILING_REMAINING_MICROS_KEY: None}
    return {CEILING_STATUS_KEY: assessment.status,
            CEILING_USED_PERCENTAGE_KEY: assessment.used_percentage,
            CEILING_REMAINING_MICROS_KEY: assessment.remaining_micros}
