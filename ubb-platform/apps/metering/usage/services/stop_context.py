"""The stop-context builder (#41, spec §H) — the past-limit tagging rules.

One function turns what the recording transaction already knows into the
immutable ``UsageEvent.stop_context`` array: the accumulate verdicts (unit
scope), the unit's kill metadata (late events), and the owner's durable
stop-signal state (customer scope, read through the ``apps.billing.queries``
contract — ADR-001). Both ingest paths — sync record and async settle — call
this ONE builder, so the tagging rules cannot drift between them.

The rules:

- A fresh crossing verdict tags the TIPPING event — ``arrived_after=false``,
  ``tripped_at`` = the event's own record time (the trip IS this event).
- A late event on a limit-killed unit carries the same limit with
  ``arrived_after=true`` and the kill time as ``tripped_at``, so an
  episode's itemization shares one context key. A cascade-killed subtask's
  late events point at the PARENT's episode (the cascade was the parent's
  trip). Non-limit terminal states (completed, failed, reaped) tag
  ``task_not_active``.
- Customer scope reads the durable ledger, never the Redis flag: an open
  ``floor_stop`` episode tags ``customer_floor`` carrying the episode id;
  the entry is the tipping one (``arrived_after=false``) only when THIS
  event's live debit won the stop transition (``opened_episode_seq``).
  An owner suspended with NO open episode (admin/fraud) tags ``suspended``
  — with a null ``tripped_at``: suspension carries no durable timestamp,
  and inventing one would be a lie. The soft-floor family never tags (§F —
  work completing past the soft line is permitted, not "past limit").
- Enforcement off ⇒ no customer-scope tagging (there is no signal suite to
  be past); unit-scope tagging follows the unit machinery, which runs for
  any registered task regardless of mode (the #42 modes ticket owns
  collapsing that story).

Timestamps are stored as ISO-8601 strings, ids as strings — the array must
be JSON-storable and byte-stable on replay reads.
"""
from apps.platform.tasks import reasons

# Kill reasons that name a limit episode a late event should point back at.
_EPISODE_KILL_REASONS = (reasons.TASK_LIMIT, reasons.SUBTASK_LIMIT,
                         reasons.CUSTOMER_FLOOR)


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def _entry(*, limit, stop_scope, tripped_at, episode_seq, task_id,
           subtask_id, arrived_after):
    return {
        "limit": limit, "stop_scope": stop_scope,
        "tripped_at": tripped_at, "episode_seq": episode_seq,
        "task_id": str(task_id) if task_id else None,
        "subtask_id": str(subtask_id) if subtask_id else None,
        "arrived_after": arrived_after,
    }


def _unit_contexts(task, verdicts, now):
    is_subtask = task.parent_id is not None
    unit_scope = "subtask" if is_subtask else "task"
    top_id = task.parent_id if is_subtask else task.id
    sub_id = task.id if is_subtask else None
    out = []

    # Fresh crossings — this event is the tipping event for each limit it
    # pushed over while the governing unit was still active.
    tip = dict(tripped_at=_iso(now), episode_seq=None, arrived_after=False)
    if verdicts.get("crossed_task_limit"):
        out.append(_entry(limit=reasons.TASK_LIMIT, stop_scope="task",
                          task_id=top_id, subtask_id=sub_id, **tip))
    if verdicts.get("crossed_subtask_limit"):
        out.append(_entry(limit=reasons.SUBTASK_LIMIT, stop_scope="subtask",
                          task_id=top_id, subtask_id=sub_id, **tip))
    if verdicts.get("crossed_floor_snapshot"):
        out.append(_entry(limit=reasons.CUSTOMER_FLOOR, stop_scope=unit_scope,
                          task_id=top_id, subtask_id=sub_id, **tip))

    # Late arrival on a non-active unit: point back at the episode that
    # ended it, so the episode's itemization shares one context key.
    if verdicts.get("task_not_active"):
        kill_reason = (task.metadata or {}).get("kill_reason") \
            if task.status == "killed" else None
        if kill_reason == reasons.PARENT_KILLED:
            # The cascade was the PARENT's trip — chase one level up. A
            # parent reaped/completed for a non-limit reason falls through
            # to the generic task_not_active entry.
            from apps.platform.tasks.models import Task
            parent = Task.objects.filter(id=task.parent_id).only(
                "id", "status", "metadata", "completed_at").first()
            parent_reason = (parent.metadata or {}).get("kill_reason") \
                if parent is not None and parent.status == "killed" else None
            if parent_reason in _EPISODE_KILL_REASONS:
                out.append(_entry(
                    limit=parent_reason, stop_scope="task",
                    tripped_at=_iso(parent.completed_at), episode_seq=None,
                    task_id=parent.id, subtask_id=task.id,
                    arrived_after=True))
                return out
        if kill_reason in _EPISODE_KILL_REASONS:
            scope = reasons.kill_scope(kill_reason, is_subtask=is_subtask)
            out.append(_entry(limit=kill_reason, stop_scope=scope,
                              tripped_at=_iso(task.completed_at),
                              episode_seq=None, task_id=top_id,
                              subtask_id=sub_id, arrived_after=True))
        else:
            out.append(_entry(limit=reasons.TASK_NOT_ACTIVE,
                              stop_scope=unit_scope,
                              tripped_at=_iso(task.completed_at),
                              episode_seq=None, task_id=top_id,
                              subtask_id=sub_id, arrived_after=True))
    return out


def _customer_contexts(owner, tenant, opened_episode_seq, task_id, subtask_id):
    from apps.platform.tenants.flags import enforcement_on
    if owner is None or not enforcement_on(tenant):
        return []
    from apps.billing.queries import get_stop_signal_state
    state = get_stop_signal_state(owner.id, tenant.id)
    if state is not None and state["state"] == "stopped":
        return [_entry(
            limit=reasons.CUSTOMER_FLOOR, stop_scope="customer",
            tripped_at=_iso(state["transitioned_at"]),
            episode_seq=state["episode_seq"],
            task_id=task_id, subtask_id=subtask_id,
            arrived_after=opened_episode_seq != state["episode_seq"])]
    if owner.status == "suspended":
        # Suspension without an open floor episode — admin/fraud, or a
        # money suspension whose episode already cleared. No durable
        # suspension timestamp exists, so tripped_at is honestly null.
        return [_entry(limit="suspended", stop_scope="customer",
                       tripped_at=None, episode_seq=None,
                       task_id=task_id, subtask_id=subtask_id,
                       arrived_after=True)]
    return []


def build_stop_context(*, task, verdicts, now, owner, tenant,
                       opened_episode_seq=None):
    """Build the stop-context array for one recorded event, or None when the
    event landed past nothing (the overwhelmingly common case — None keeps
    the column null and the partial GIN index tiny).

    ``task``/``verdicts`` are the accumulate primitive's outputs (both None
    for an unattributed event); ``owner`` is the resolved billing owner ROW
    (status already in hand — no extra query); ``opened_episode_seq`` is the
    floor-stop episode THIS event's live debit opened, when the fast lane
    won the transition (sync path only — async settle never tips the
    customer floor, its crossing is detected at accept/drawdown time).
    """
    out = []
    task_id = subtask_id = None
    if task is not None and verdicts is not None:
        out.extend(_unit_contexts(task, verdicts, now))
        is_subtask = task.parent_id is not None
        task_id = task.parent_id if is_subtask else task.id
        subtask_id = task.id if is_subtask else None
    out.extend(_customer_contexts(owner, tenant, opened_episode_seq,
                                  task_id, subtask_id))
    return out or None
