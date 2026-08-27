"""The past-limit report (#41, spec §I) — "exactly what was spent past the
limit and why", in one call.

Composition-layer module (api may import every product; ADR-001): episodes
are reconstructed from THREE sources and married to the itemized events by
the stop-context markers —

- **Customer-wide floor episodes** from the ``stop.fired`` / ``stop.cleared``
  outbox pair (each carries the signal ledger's ``episode_seq``), backstopped
  by the current ``StopSignalState`` row (an open episode survives outbox
  retention) and by the markers themselves (a marked event's ``tripped_at``
  re-dates an episode whose outbox rows were purged).
- **Task/subtask trip episodes** from killed Task rows whose
  ``kill_reason`` names a limit. A kill is terminal — no resume.
- **Soft-floor marker rows** from the ``soft_floor.crossed`` / ``.cleared``
  pair — crossed/cleared timestamps only, NO itemized events: nothing is
  "past limit" under a soft floor (§F).

Itemized events are fetched in ONE query (the customer's tagged events in
the window — the partial GIN index's population) and bucketed per episode in
Python; ``totals_per_limit`` (both denominations) covers exactly the
itemized events of the episodes the report includes, so totals and episodes
can never disagree under a window. Episodes live on the billing OWNER (a
pooled seat reports the owner's episodes with the SEAT's events tagged into
them); the report is per-seat, matching the per-customer usage surfaces.

``since``/``until`` window BOTH episode selection (tripped_at ≥ since,
< until) and itemized events (effective_at, same bounds).
"""
from django.utils.dateparse import parse_datetime

from apps.billing.queries import get_stop_signal_state
from apps.metering.usage.models import Posting
from apps.platform.events.models import OutboxEvent
from apps.platform.work import reasons
from apps.platform.work.models import Task
from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.vocabulary import TASK_STATUS_KILLED
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY, cost_total,
    counts_as_unresolved)

_UNIT_LIMITS = (reasons.TASK_LIMIT, reasons.SUBTASK_LIMIT)


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def _in_window(dt, since, until):
    if dt is None:
        return False
    return (since is None or dt >= since) and (until is None or dt < until)


def _bucket_events(customer, since, until):
    """One pass over the customer's tagged events: bucket the itemized rows
    per episode key. Totals are NOT accumulated here — they are derived from
    the episodes the report actually includes, so a window can never show
    totals with no corresponding episode."""
    qs = Posting.objects.filter(customer=customer, stop_context__isnull=False)
    if since is not None:
        qs = qs.filter(effective_at__gte=since)
    if until is not None:
        qs = qs.filter(effective_at__lt=until)
    buckets = {}
    for e in qs.order_by("effective_at", "created_at"):
        for ctx in e.stop_context or []:
            limit = ctx.get("limit")
            if ctx.get("stop_scope") == "customer":
                if limit == reasons.SUSPENDED:
                    continue  # taggable but not an episode
                key = ("floor", ctx.get("episode_seq"))
            elif limit == reasons.TASK_LIMIT:
                key = ("unit", ctx.get("task_id"))
            elif limit == reasons.SUBTASK_LIMIT:
                key = ("unit", ctx.get("subtask_id"))
            else:
                continue  # task_not_active — no limit episode to itemize
            b = buckets.setdefault(key, {"events": [], "ctx_tripped_at": None})
            b["events"].append({
                "event_id": str(e.id),
                "effective_at": e.effective_at.isoformat(),
                "billed_cost_micros": e.billed_cost_micros,
                # The price above is `None` where UBB could not resolve one
                # (#351), and three statuses produce that null for different
                # reasons — so the itemized row carries the status for exactly
                # the reason the cost half does.
                "pricing_status": e.pricing_status,
                "provider_cost_micros": e.provider_cost_micros,
                # The amount above is `None` both where UBB has not resolved
                # this cost and where the Event Type declares none, and the two
                # are read differently by every total built on them (#328). The
                # itemized row carries the status so a reader of the row — and
                # the sums below — can tell which.
                "costing_status": e.costing_status,
                "arrived_after": ctx.get("arrived_after", True),
            })
            if b["ctx_tripped_at"] is None and ctx.get("tripped_at"):
                b["ctx_tripped_at"] = ctx["tripped_at"]
    return buckets


def _signal_episodes(tenant, owner, opened_type, closed_type, family):
    """episode_seq → {tripped_at, resumed_at} from the outbox pair, merged
    with the current ledger row (the durable backstop for an episode whose
    outbox rows aged out of retention)."""
    eps = {}
    rows = (OutboxEvent.objects
            .filter(tenant_id=tenant.id,
                    event_type__in=(opened_type, closed_type),
                    payload__owner_id=str(owner.id))
            .order_by("created_at")
            .values("event_type", "payload", "created_at"))
    for r in rows:
        seq = r["payload"].get("episode_seq")
        ep = eps.setdefault(seq, {"tripped_at": None, "resumed_at": None})
        if r["event_type"] == opened_type:
            if ep["tripped_at"] is None:
                ep["tripped_at"] = r["created_at"]
        else:
            ep["resumed_at"] = r["created_at"]
    state = get_stop_signal_state(owner.id, tenant.id, family=family)
    if state is not None:
        seq = state["episode_seq"]
        if state["state"] == "stopped":
            ep = eps.setdefault(seq, {"tripped_at": None, "resumed_at": None})
            if ep["tripped_at"] is None:
                ep["tripped_at"] = state["transitioned_at"]
        elif seq in eps and eps[seq]["resumed_at"] is None:
            eps[seq]["resumed_at"] = state["transitioned_at"]
    return eps


def _pair_total_of(events, pair):
    """One amount/status pair's total over itemized rows: what can be added up,
    and what cannot.

    ⚠ THE SUPPLIER HALF OF THIS USED TO RAISE (#328), AND THE PRICE HALF WAS THE
    NEXT ONE TO (#351). ``sum(e[column] …)`` over a posting whose amount UBB has
    not resolved is ``int + None`` — a 500 on a report about money already
    spent. The cost side became reachable the moment #317 made its column
    nullable; the price side the moment #351 made its own, and #153 §17.6
    predicted that one in advance. This is also the surface a contract-derived
    enumeration has already missed once, because the response is untyped and no
    schema names its rows.

    **ONE FUNCTION FOR BOTH PAIRS, and that is the point.** It was two, differing
    only in which column and which key — which is how a repair applied to one
    half comes to be missing from the other, twice over. What differs between
    the pairs is entirely inside the pair: its columns, and the single status
    that means *not learned*.

    An unresolved amount is skipped and COUNTED, so the total is a floor that
    says how far it falls short. Every OTHER absent amount is skipped and not
    counted — a cost the Event Type declares does not exist, a price that was
    waived, a subject with no customer revenue at this level — because each
    contributes a genuine zero and nothing about it is missing. They are
    indistinguishable on the row, all carrying `None`, which is why the status
    tells them apart and why the predicate is asked of the PAIR rather than
    spelled here.
    """
    column = pair.amount_column
    resolved = sum(e[column] for e in events if e[column] is not None)
    unresolved = sum(1 for e in events
                     if counts_as_unresolved(pair, e[pair.status_column]))
    return cost_total(pair, key=column, resolved_micros=resolved,
                      unresolved_events=unresolved)


def _episode_row(*, family, limit, stop_scope, episode_seq, task_id,
                 subtask_id, provider_cost_limit_micros, tripped_at,
                 resumed_at, bucket):
    events = bucket["events"] if bucket else []
    supplier = _pair_total_of(events, SUPPLIER_COST)
    price = _pair_total_of(events, CUSTOMER_PRICE)
    return {
        "family": family, "limit": limit, "stop_scope": stop_scope,
        "episode_seq": episode_seq,
        "task_id": task_id, "subtask_id": subtask_id,
        "provider_cost_limit_micros": provider_cost_limit_micros,
        "tripped_at": _iso(tripped_at), "resumed_at": _iso(resumed_at),
        "events": events,
        "event_count": len(events),
        "total_billed_cost_micros": price["billed_cost_micros"],
        UNPRICED_EVENT_COUNT_KEY: price[UNPRICED_EVENT_COUNT_KEY],
        "total_provider_cost_micros": supplier["provider_cost_micros"],
        UNRESOLVED_EVENT_COUNT_KEY: supplier[UNRESOLVED_EVENT_COUNT_KEY],
    }


def build_past_limit_report(tenant, customer, since=None, until=None):
    owner = customer.resolve_billing_owner()
    buckets = _bucket_events(customer, since, until)
    episodes = []
    totals, counted = {}, set()

    def _count(limit, events):
        # Per-limit totals over exactly the itemized events the report
        # shows, deduped per (limit, event) — one event crossing two limits
        # counts once into each.
        for ev in events:
            if (limit, ev["event_id"]) in counted:
                continue
            counted.add((limit, ev["event_id"]))
            t = totals.setdefault(limit, {
                "billed_cost_micros": 0, UNPRICED_EVENT_COUNT_KEY: 0,
                "provider_cost_micros": 0,
                UNRESOLVED_EVENT_COUNT_KEY: 0, "event_count": 0})
            # Both pairs on the same terms as the episode rows: add what is
            # resolved, count what is not (#328, #351). A per-limit total that
            # read complete while its own episodes read partial would be two
            # answers about one set of events.
            #
            # ⚠ The billed line was a bare `+=` until #351 and is the second of
            # this module's two `TypeError`s: `int += None` the first time a
            # posting past a limit carried a price UBB could not resolve.
            if ev["billed_cost_micros"] is not None:
                t["billed_cost_micros"] += ev["billed_cost_micros"]
            elif counts_as_unresolved(CUSTOMER_PRICE, ev["pricing_status"]):
                t[UNPRICED_EVENT_COUNT_KEY] += 1
            if ev["provider_cost_micros"] is not None:
                t["provider_cost_micros"] += ev["provider_cost_micros"]
            elif counts_as_unresolved(SUPPLIER_COST, ev["costing_status"]):
                t[UNRESOLVED_EVENT_COUNT_KEY] += 1
            t["event_count"] += 1

    # Customer-wide floor episodes: signal history ∪ tagged-event episodes.
    floor_eps = _signal_episodes(tenant, owner, "stop.fired", "stop.cleared",
                                 "floor_stop")
    tagged_seqs = {k[1] for k in buckets if k[0] == "floor"}
    for seq in set(floor_eps) | tagged_seqs:
        ep = floor_eps.get(seq, {"tripped_at": None, "resumed_at": None})
        bucket = buckets.get(("floor", seq))
        tripped_at = ep["tripped_at"]
        if tripped_at is None and bucket and bucket["ctx_tripped_at"]:
            tripped_at = parse_datetime(bucket["ctx_tripped_at"])
        if not _in_window(tripped_at, since, until):
            continue
        row = _episode_row(
            family="floor_stop", limit=reasons.CUSTOMER_WIDE_STOP,
            stop_scope="customer", episode_seq=seq,
            task_id=None, subtask_id=None, provider_cost_limit_micros=None,
            tripped_at=tripped_at, resumed_at=ep["resumed_at"],
            bucket=bucket)
        _count(reasons.CUSTOMER_WIDE_STOP, row["events"])
        episodes.append(row)

    # Soft-floor marker rows — crossed/cleared only, never itemized (§F).
    for seq, ep in _signal_episodes(tenant, owner, "soft_floor.crossed",
                                    "soft_floor.cleared",
                                    "soft_floor").items():
        if not _in_window(ep["tripped_at"], since, until):
            continue
        episodes.append(_episode_row(
            family="soft_floor", limit=None, stop_scope="customer",
            episode_seq=seq, task_id=None, subtask_id=None,
            provider_cost_limit_micros=None,
            tripped_at=ep["tripped_at"], resumed_at=ep["resumed_at"],
            bucket=None))

    # Task/subtask trips: a killed unit whose kill_reason names a limit is
    # an episode; the kill is terminal, so there is never a resume.
    #
    # ⚠ THE STATE FILTER IS NOW LOAD-BEARING ON ITS OWN (#408). `killed` means
    # UBB stopped the work on a spend signal and nothing else — the sweepers
    # write `expired` — so this report can no longer be handed a silence to
    # itemize. The reason filter beside it was already carrying that weight
    # (no sweeper ever wrote a `_UNIT_LIMITS` reason), and the two now agree
    # rather than one covering for the other.
    unit_qs = Task.objects.filter(
        customer=customer, status=TASK_STATUS_KILLED,
        metadata__kill_reason__in=_UNIT_LIMITS)
    if since is not None:
        unit_qs = unit_qs.filter(completed_at__gte=since)
    if until is not None:
        unit_qs = unit_qs.filter(completed_at__lt=until)
    for unit in unit_qs:
        limit = unit.metadata["kill_reason"]
        is_subtask = unit.parent_id is not None
        scope = reasons.kill_scope(limit, is_subtask=is_subtask)
        row = _episode_row(
            family="task", limit=limit, stop_scope=scope,
            episode_seq=None,
            task_id=str(unit.parent_id) if is_subtask else str(unit.id),
            subtask_id=str(unit.id) if is_subtask else None,
            provider_cost_limit_micros=unit.provider_cost_limit_micros,
            tripped_at=unit.completed_at, resumed_at=None,
            bucket=buckets.get(("unit", str(unit.id))))
        _count(limit, row["events"])
        episodes.append(row)

    # Chronological narrative; UTC ISO strings sort correctly as text, and
    # an undatable episode (nothing survived to date it) sorts last.
    episodes.sort(key=lambda ep: (ep["tripped_at"] is None,
                                  ep["tripped_at"] or ""))
    return {
        "customer_id": str(customer.id),
        "billing_owner_id": str(owner.id),
        "since": _iso(since), "until": _iso(until),
        "episodes": episodes,
        "totals_per_limit": totals,
    }
