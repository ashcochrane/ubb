"""The two spend-control reports (#465, slice 6 §14; #153 §10, #150 §9.3):
Stops and breaches — what was spent past a stop, and why — and Utilisation
and headroom — how much of each ceiling was used, and how often it could not
be evaluated. Two reads at `/api/v1/spend-controls/`, for every tenant.

WHY A PREFIX OF THEIR OWN, AND WHY NO PRODUCT GATES IT. The four spend
controls sit on a shared kernel concept — a unit of work — and are realised
by three owners: the ceiling and admission control are the kernel's, the
pool and the wallet policy are billing's (slice 6 §1). A report that reads
across all of them belongs to none of the product prefixes, and ADR-0011 §1's
reasoning for the lifecycle holds for it whole: a unit of work's stops mean
something for every tenant — a metering-only tenant declares ceilings and
has them fire — so there is no product whose absence makes the question
meaningless, and a family a tenant lacks simply returns no rows. The
capability question is asked of the DATA, never at the door: billing's two
families answer empty for a tenant with no ledger rather than 403. The
per-customer report at `/customers/{id}/past-limit-report` (an untyped
response, metering-gated) is what these replace; it stays until ticket 15
(#466) retires it with its two console renderings.

THE COMPOSITION LAYER IS THE ONE JOINER. Four read contracts and two more
answer here and nowhere else: the kernel's `ceiling_episodes`,
`ceiling_utilisation` and `customer_wide_stops_applied` (`work/queries.py`),
billing's `signal_episodes` and `customer_spend_pool_utilisation`
(`billing/queries.py`), metering's `stop_context_postings` and
`charge_that_reached` (`metering/queries.py`) — plain data every one, joined
below by the stop-context markers exactly as the retired report joined them
(ADR-001: the composition layer may import every product; no product imports
another for this).

BOTH RESPONSES ARE TYPED ROWS. The retired report's `list[dict]` is why a
console reader once coalesced an absent cost to zero money on the one report
that itemises what overran a stop, and an untyped response is invisible to
every enumeration derived from the contract (#330). Three row shapes under
one list, discriminated by `control_family`; the aggregate's every average is
null where nothing contributes, never zero (#153 §10.5).

THE WINDOW IS ALWAYS BOUNDED. Computed reports are cursor-exempt but
parameter-bounded (`docs/conventions/api-contract.md`); a caller that leaves
the window open gets the 366 days ending now, and the response echoes the
window it applied so the bound is never silent.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from ninja import Router

from api.v1.schemas import (
    CeilingEpisodeRow, CeilingUtilisationRow, ControlFamily,
    CustomerSpendPoolEpisodeRow, ItemisedEventRow, ItemisedEventsOut,
    SpendControlFamilyTotalsRow, StopsAndBreachesResponse,
    UtilisationAndHeadroomResponse, WalletPolicyEpisodeRow)
from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.auth import READ, ApiKeyAuth, role_floor
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY, cost_total,
    counts_as_unresolved)
from core.identifiers import UUIDIdentifier
from core.problems import Problem
from core.time_windows import REPORT_WINDOW_MAX_DAYS
from core.vocabulary import (
    CEILING_STATUS_CEILING_REACHED, CEILING_STATUS_INDETERMINATE,
    CEILING_STATUS_NOT_APPLICABLE, CEILING_STATUS_WITHIN_CEILING,
    CONTROL_FAMILY_CEILING, CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    CONTROL_FAMILY_VALUES, CONTROL_FAMILY_WALLET_POLICY)

spend_control_router = Router(auth=ApiKeyAuth())

#: The stop-context words that are taggable and are never an episode: a
#: bare suspension, and a late event on work that ended for a non-stop
#: reason. Excluded by constant identity, never by an allow-list of current
#: words — the context array is immutable with its row and was not migrated
#: (the metering glossary's rule), so an episode is found by SCOPE and ids.
def _not_an_episode():
    from apps.platform.work import reasons
    return frozenset({reasons.SUSPENDED, reasons.TASK_NOT_ACTIVE})


# --- the window and the filters -------------------------------------------

def _aware(instant):
    if instant is not None and timezone.is_naive(instant):
        return timezone.make_aware(instant, dt_timezone.utc)
    return instant


def _window(since, until):
    """The half-open window the report covers, bounded either way: `until`
    defaults to now, `since` to the report ceiling before it; a stated pair
    is refused when it runs backwards or spans more than the ceiling."""
    since, until = _aware(since), _aware(until)
    if until is None:
        until = timezone.now()
    if since is None:
        since = until - timedelta(days=REPORT_WINDOW_MAX_DAYS)
    if until < since:
        raise Problem("validation_error", "until must not precede since")
    if (until - since).days > REPORT_WINDOW_MAX_DAYS:
        raise Problem("validation_error",
                      f"window must not exceed {REPORT_WINDOW_MAX_DAYS} days")
    return since, until


def _family(control_family):
    if control_family is not None and control_family not in CONTROL_FAMILY_VALUES:
        raise Problem("validation_error",
                      f"control_family must be one of {sorted(CONTROL_FAMILY_VALUES)}")
    return control_family


def _customer(tenant, customer_id):
    from apps.platform.customers.models import Customer
    if customer_id is None:
        return None
    return get_object_or_404(Customer, id=customer_id, tenant=tenant)


# --- the itemised events ----------------------------------------------------

def _event_row(posting, *, arrived_after):
    return ItemisedEventRow(
        event_id=posting["event_id"], customer_id=posting["customer_id"],
        effective_at=posting["effective_at"],
        billed_cost_micros=posting["billed_cost_micros"],
        pricing_status=posting["pricing_status"],
        provider_cost_micros=posting["provider_cost_micros"],
        costing_status=posting["costing_status"],
        charge_id=posting["charge_id"], arrived_after=arrived_after)


def _pair_total_of(events, pair):
    """One amount/status pair's total over itemised rows: add what is
    resolved, count what is not (#328, #351) — one function for both pairs,
    because a repair applied to one half of two copies is how the other half
    comes to be missing it."""
    amount = pair.amount_column
    resolved = sum(getattr(e, amount) for e in events if getattr(e, amount) is not None)
    unresolved = sum(1 for e in events
                     if counts_as_unresolved(pair, getattr(e, pair.status_column)))
    return cost_total(pair, key=amount, resolved_micros=resolved,
                      unresolved_events=unresolved)


def _itemised(events):
    price = _pair_total_of(events, CUSTOMER_PRICE)
    supplier = _pair_total_of(events, SUPPLIER_COST)
    return ItemisedEventsOut(
        events=events, event_count=len(events),
        billed_cost_micros=price["billed_cost_micros"],
        unpriced_event_count=price[UNPRICED_EVENT_COUNT_KEY],
        provider_cost_micros=supplier["provider_cost_micros"],
        unresolved_event_count=supplier[UNRESOLVED_EVENT_COUNT_KEY])


def _bucket(postings, stop_lines):
    """The itemised events per episode key, off the stop-context markers.

    A unit-scope entry keys on the unit at its own altitude; a customer-scope
    entry on the owner, the line and the line's episode id. An entry tagged
    before the lines existed carries a word no line has and keys under a
    None line, beside the instant it recorded — the two lines number their
    episodes independently, so a bare id is ambiguous and the instant is
    what tells the lines apart (`_claim_legacy`). Events are kept in
    itemisation order.
    """
    excluded = _not_an_episode()
    buckets = {}
    for posting in postings:
        owner = posting["billing_owner_id"] or posting["customer_id"]
        for ctx in posting["stop_context"]:
            word, scope = ctx.get("limit"), ctx.get("stop_scope")
            if word in excluded:
                continue
            row = _event_row(posting, arrived_after=ctx.get("arrived_after", True))
            if scope == "customer":
                if word in stop_lines:
                    key = ("customer", owner, word, ctx.get("episode_seq"))
                else:
                    key = ("customer", owner, None, ctx.get("episode_seq"))
                    row = (parse_datetime(ctx["tripped_at"])
                           if ctx.get("tripped_at") else None, row)
            elif scope == "subtask":
                key = ("unit", ctx.get("subtask_id"))
            else:
                key = ("unit", ctx.get("task_id"))
            buckets.setdefault(key, []).append(row)
    return buckets


def _claim_legacy(buckets, episodes):
    """Give each entry tagged before the lines existed to ONE episode: among
    the owner's episodes carrying that entry's episode id, the one whose
    opening instant is nearest the instant the entry recorded — an entry
    that recorded none goes to the earliest, the only episode that could
    have existed before the lines did. Returns ``{id(episode): [events]}``.
    """
    claimed = {}
    for key, tagged in buckets.items():
        if key[0] != "customer" or key[2] is not None:
            continue
        owner, seq = key[1], key[3]
        candidates = [ep for ep in episodes
                      if ep["owner_id"] == owner and ep["episode_seq"] == seq
                      and ep["reason_code"] is not None]
        if not candidates:
            continue
        for tripped_at, event in tagged:
            nearest = (min(candidates, key=lambda ep: abs(ep["opened_at"] - tripped_at))
                       if tripped_at is not None
                       else min(candidates, key=lambda ep: ep["opened_at"]))
            claimed.setdefault(id(nearest), []).append(event)
    return claimed


# --- Stops and breaches -----------------------------------------------------

def build_stops_and_breaches(tenant, *, since, until, customer=None,
                             task_type=None, control_family=None):
    from apps.billing.gating.services.stop_signal_service import STOP_LINES
    from apps.billing.queries import signal_episodes
    from apps.metering.queries import stop_context_postings
    from apps.platform.work.queries import (
        ceiling_episodes, customer_wide_stops_applied)

    wanted = (lambda family: control_family is None or control_family == family)
    seat_id = customer.id if customer is not None else None
    owner_id = customer.resolve_billing_owner().id if customer is not None else None

    # An episode's events are the episode's whatever window selected it, and
    # a customer filter reaches the events every seat tagged into its
    # owner's episodes — so the postings are read unwindowed, for the
    # customer and for everything pinning it as billing owner.
    buckets = _bucket(
        stop_context_postings(tenant.id, customer_id=seat_id, billing_owner_id=owner_id),
        STOP_LINES)
    rows = []

    if wanted(CONTROL_FAMILY_CEILING):
        for ep in ceiling_episodes(tenant.id, customer_id=seat_id, task_type=task_type,
                                   since=since, until=until):
            rows.append(CeilingEpisodeRow(
                **ep, itemised=_itemised(buckets.get(("unit", ep["task_id"]), []))))

    # A kind filter is a statement about kinds of work; a customer-wide line
    # has no kind, so the filter narrows those families to nothing.
    if task_type is None and (wanted(CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
                              or wanted(CONTROL_FAMILY_WALLET_POLICY)):
        # A pooled seat's pool line is declared on the SEAT while its floor
        # is its billing owner's, so a customer filter asks for both.
        owners = None if customer is None else {seat_id, owner_id}
        episodes = [ep for ep in signal_episodes(tenant.id, owner_ids=owners,
                                                 since=since, until=until)
                    if wanted(ep["control_family"])]
        legacy = _claim_legacy(buckets, episodes)
        stops = customer_wide_stops_applied(tenant.id, since=since) \
            if any(ep["control_family"] == CONTROL_FAMILY_CUSTOMER_SPEND_POOL
                   for ep in episodes) else []
        for ep in episodes:
            events = list(buckets.get(
                ("customer", ep["owner_id"], ep["reason_code"], ep["episode_seq"]), []))
            events += legacy.get(id(ep), [])
            events.sort(key=lambda e: e.effective_at)
            if ep["control_family"] == CONTROL_FAMILY_CUSTOMER_SPEND_POOL:
                rows.append(_pool_row(tenant, ep, events, stops))
            else:
                rows.append(WalletPolicyEpisodeRow(
                    control_family=ep["control_family"], control_id=ep["control_id"],
                    reason_code=ep["reason_code"], soft_floor=ep["soft_floor"],
                    customer_id=ep["owner_id"], episode_seq=ep["episode_seq"],
                    floor_micros=ep["floor_micros"],
                    balance_at_crossing_micros=ep["balance_at_crossing_micros"],
                    opened_at=ep["opened_at"], closed_at=ep["closed_at"],
                    itemised=_itemised([] if ep["soft_floor"] else events)))

    rows.sort(key=lambda row: row.opened_at)
    return StopsAndBreachesResponse(since=since, until=until, rows=rows,
                                    totals=_totals(rows))


def _pool_row(tenant, ep, events, stops):
    """The pool's row, explained by the Charge that crossed it: the event the
    recording route marked as the tipping one where the live lane detected
    the crossing, else the drawdown replayed up to the opening instant
    (`charge_that_reached`) — never an arbitrary event, and null where
    nothing UBB holds can name it."""
    from apps.metering.queries import charge_that_reached

    crossing = next((e for e in events if not e.arrived_after), None)
    marked = crossing is not None
    if crossing is None and ep["stop_threshold_micros"] is not None:
        found = charge_that_reached(
            tenant.id, ep["owner_id"], stop_threshold_micros=ep["stop_threshold_micros"],
            at=ep["opened_at"])
        if found is not None:
            crossing = _event_row(found, arrived_after=False)
            if all(e.event_id != crossing.event_id for e in events):
                events = [crossing] + events
    after = [e for e in events if e.arrived_after]
    spent_after = _pair_total_of(after, CUSTOMER_PRICE)
    opened, closed = ep["opened_at"], ep["closed_at"]
    swept = sum(1 for s in stops
                if ep["owner_id"] in (s["customer_id"], s["billing_owner_id"])
                and s["control_id"] == ep["control_id"]
                and opened <= s["stopped_at"] and (closed is None or s["stopped_at"] < closed))
    return CustomerSpendPoolEpisodeRow(
        control_family=ep["control_family"], control_id=ep["control_id"],
        reason_code=ep["reason_code"], customer_id=ep["owner_id"],
        episode_seq=ep["episode_seq"], period=ep["period"], cap_micros=ep["cap_micros"],
        opened_at=opened, closed_at=closed,
        crossing_charge_id=crossing.charge_id if crossing else None,
        crossing_posting_id=crossing.event_id if crossing else None,
        crossing_marked=marked,
        spent_after_micros=spent_after["billed_cost_micros"],
        unpriced_after_count=spent_after[UNPRICED_EVENT_COUNT_KEY],
        work_stopped_count=swept, itemised=_itemised(events))


def _totals(rows):
    """Per family, over exactly the itemised events of the rows shown, each
    event once per family — one event in two families counts into each."""
    by_family = {}
    for row in rows:
        seen = by_family.setdefault(row.control_family, {})
        for event in row.itemised.events:
            seen.setdefault(event.event_id, event)
    out = []
    for family in sorted(by_family):
        events = list(by_family[family].values())
        block = _itemised(events)
        out.append(SpendControlFamilyTotalsRow(
            control_family=family, event_count=block.event_count,
            billed_cost_micros=block.billed_cost_micros,
            unpriced_event_count=block.unpriced_event_count,
            provider_cost_micros=block.provider_cost_micros,
            unresolved_event_count=block.unresolved_event_count))
    return out


# --- Utilisation and headroom -----------------------------------------------

def _floor_mean(values):
    """A whole-number mean rounded down — never overstating — or None where
    nothing contributes: a null is never coerced to zero."""
    values = [v for v in values if v is not None]
    return sum(values) // len(values) if values else None


def _share_percentage(count, unit_count):
    """A whole-number share of the work listed, rounded down; None where no
    work is listed — a share of nothing is not a share."""
    return count * 100 // unit_count if unit_count else None


def build_utilisation_and_headroom(tenant, *, since, until, customer=None,
                                   task_type=None):
    from apps.billing.queries import customer_spend_pool_utilisation
    from apps.platform.work.queries import ceiling_utilisation

    seat_id = customer.id if customer is not None else None
    rows = [CeilingUtilisationRow(**row)
            for row in ceiling_utilisation(tenant.id, customer_id=seat_id,
                                           task_type=task_type, since=since, until=until)]
    statuses = [row.ceiling_status for row in rows]
    reached = statuses.count(CEILING_STATUS_CEILING_REACHED)
    indeterminate = statuses.count(CEILING_STATUS_INDETERMINATE)
    not_applicable = statuses.count(CEILING_STATUS_NOT_APPLICABLE)
    pool = None
    if customer is not None:
        answer = customer_spend_pool_utilisation(tenant.id, customer.id)
        if answer["cap_micros"] > 0:
            pool = answer
    return UtilisationAndHeadroomResponse(
        since=since, until=until, rows=rows,
        unit_count=len(rows),
        evaluated_count=len(rows) - not_applicable,
        not_applicable_count=not_applicable,
        ceiling_reached_count=reached,
        ceiling_reached_share_percentage=_share_percentage(reached, len(rows)),
        indeterminate_count=indeterminate,
        indeterminate_share_percentage=_share_percentage(indeterminate, len(rows)),
        within_ceiling_count=statuses.count(CEILING_STATUS_WITHIN_CEILING),
        # PER UNIT, THEN ACROSS EVERY UNIT (#150 §9.3): each row's percentage
        # is its own ceiling's, so one chatty unit weighs exactly one.
        average_final_utilisation_percentage=_floor_mean(
            row.ceiling_used_percentage for row in rows),
        average_unused_headroom_micros=_floor_mean(
            row.ceiling_remaining_micros for row in rows),
        customer_spend_pool=pool)


# --- the routes ---------------------------------------------------------------

@spend_control_router.get("/stops-and-breaches", response=StopsAndBreachesResponse)
@role_floor(READ)
def stops_and_breaches(request, customer_id: UUIDIdentifier = None,
                       task_type: str = None, since: datetime = None,
                       until: datetime = None,
                       control_family: Optional[ControlFamily] = None):
    """What was spent past a stop, and why: every spend control that fired
    and had an enforcement consequence, in the window, as typed rows — a
    Ceiling row per unit stopped on its own ceiling, a Customer spend pool
    row per pool episode (explained by the Charge that crossed it), a Wallet
    policy row per floor episode (a soft-floor row is a marker with no
    events). Tenant-wide; `customer_id` narrows to one customer's work and
    its billing owner's customer-wide episodes, `task_type` to one kind of
    work (customer-wide episodes have no kind and drop out), `since`/`until`
    (ISO datetimes; naive = UTC) to the instant each episode opened, and
    `control_family` to one family — a family this workspace lacks answers
    no rows, never an error. Expiries and admission control appear in
    neither report. A window left open covers the 366 days ending now; the
    response echoes the window applied."""
    tenant = request.auth.tenant
    since, until = _window(since, until)
    return build_stops_and_breaches(
        tenant, since=since, until=until, customer=_customer(tenant, customer_id),
        task_type=task_type, control_family=_family(control_family))


@spend_control_router.get("/utilisation-and-headroom",
                          response=UtilisationAndHeadroomResponse)
@role_floor(READ)
def utilisation_and_headroom(request, customer_id: UUIDIdentifier = None,
                             task_type: str = None, since: datetime = None,
                             until: datetime = None):
    """How much of each ceiling was used, and how often it could not be
    evaluated: one row per unit of work that completed in the window (at
    either altitude) with its ceiling status, utilisation and headroom as
    they stood at completion, and the aggregate — the average utilisation
    computed per unit and then across every unit, the share and count that
    reached their ceiling, the share and count that were indeterminate, the
    average unused headroom. Averages are null where no unit contributes,
    never zero. `customer_spend_pool` is that customer's pool status pair
    when `customer_id` names one and a pool applies, otherwise null. The
    filters and the window are `stops-and-breaches`'s, on the instant each
    unit completed."""
    tenant = request.auth.tenant
    since, until = _window(since, until)
    return build_utilisation_and_headroom(
        tenant, since=since, until=until, customer=_customer(tenant, customer_id),
        task_type=task_type)
