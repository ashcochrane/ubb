"""The past-limit report (#41, spec §I) — "exactly what was spent past the
limit and why", in one call.

Composition-layer module (api may import every product; ADR-001): episodes
are reconstructed from THREE sources and married to the itemized events by
the stop-context tags —

- **Customer-wide floor episodes** from the ``stop.fired`` / ``stop.cleared``
  outbox pair (each carries the signal ledger's ``episode_seq``), backstopped
  by the current ``StopSignalState`` row (an open episode survives outbox
  retention) and by the tags themselves (a tagged event's ``tripped_at``
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
from apps.metering.usage.models import UsageEvent
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks import reasons
from apps.platform.tasks.models import Task

_UNIT_LIMITS = (reasons.TASK_LIMIT, reasons.SUBTASK_LIMIT,
                reasons.CUSTOMER_FLOOR)


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
    qs = UsageEvent.objects.filter(customer=customer, stop_context__isnull=False)
    if since is not None:
        qs = qs.filter(effective_at__gte=since)
    if until is not None:
        qs = qs.filter(effective_at__lt=until)
    buckets = {}
    for e in qs.order_by("effective_at", "created_at"):
        for ctx in e.stop_context or []:
            limit = ctx.get("limit")
            if ctx.get("stop_scope") == "customer":
                if limit != reasons.CUSTOMER_FLOOR:
                    continue  # `suspended` is taggable but not an episode
                key = ("floor", ctx.get("episode_seq"))
            elif limit == reasons.TASK_LIMIT:
                key = ("unit", ctx.get("task_id"))
            elif limit == reasons.SUBTASK_LIMIT:
                key = ("unit", ctx.get("subtask_id"))
            elif limit == reasons.CUSTOMER_FLOOR:
                # Unit-scoped floor snapshot — keyed on the killed unit.
                key = ("unit", ctx.get("subtask_id") or ctx.get("task_id"))
            else:
                continue  # task_not_active — no limit episode to itemize
            b = buckets.setdefault(key, {"events": [], "ctx_tripped_at": None})
            b["events"].append({
                "event_id": str(e.id),
                "effective_at": e.effective_at.isoformat(),
                "billed_cost_micros": e.billed_cost_micros,
                "provider_cost_micros": e.provider_cost_micros,
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


def _episode_row(*, family, limit, stop_scope, episode_seq, task_id,
                 subtask_id, provider_cost_limit_micros, tripped_at,
                 resumed_at, bucket):
    events = bucket["events"] if bucket else []
    return {
        "family": family, "limit": limit, "stop_scope": stop_scope,
        "episode_seq": episode_seq,
        "task_id": task_id, "subtask_id": subtask_id,
        "provider_cost_limit_micros": provider_cost_limit_micros,
        "tripped_at": _iso(tripped_at), "resumed_at": _iso(resumed_at),
        "events": events,
        "event_count": len(events),
        "total_billed_cost_micros": sum(
            e["billed_cost_micros"] for e in events),
        "total_provider_cost_micros": sum(
            e["provider_cost_micros"] for e in events),
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
                "billed_cost_micros": 0, "provider_cost_micros": 0,
                "event_count": 0})
            t["billed_cost_micros"] += ev["billed_cost_micros"]
            t["provider_cost_micros"] += ev["provider_cost_micros"]
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
            family="floor_stop", limit=reasons.CUSTOMER_FLOOR,
            stop_scope="customer", episode_seq=seq,
            task_id=None, subtask_id=None, provider_cost_limit_micros=None,
            tripped_at=tripped_at, resumed_at=ep["resumed_at"],
            bucket=bucket)
        _count(reasons.CUSTOMER_FLOOR, row["events"])
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
    unit_qs = Task.objects.filter(
        customer=customer, status="killed",
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
