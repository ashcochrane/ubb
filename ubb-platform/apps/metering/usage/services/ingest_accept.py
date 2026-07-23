"""The batch-ingestion accept seam (#113) — the accept half of async ingest,
moved out of the composition layer so it sits beside the settle sweep it
feeds (apps/metering/usage/tasks.py) and its verdicts are testable below
HTTP (apps/metering/usage/tests/test_ingest_accept.py).

Two surfaces:

- ``accept_batch(tenant, items) -> verdicts`` — the async accept pipeline:
  estimate -> atomic hold -> durable raw append. The endpoint keeps HTTP
  shape only (auth/product gates, the envelope counters, and the problem
  mapping for IngestAppendFailed).
- ``record_sync_item(tenant, item, ...)`` — one batch item == one
  independent POST /usage, shared by the sync batch endpoint and this
  pipeline's Unpriceable fallback, plus the request-item adapters over
  UsageService.record_usage (usage_kwargs / usage_error / with_uncosted)
  the single endpoint composes too.

``items`` are request-item SHAPED (the API's RecordUsageRequest field set +
``model_dump``) but duck-typed — this module never imports ``api.*``
(ADR-001: products never import the composition layer). Billing crossings
ride the sanctioned apps.billing.queries read contract only.
"""
import logging
import time

from django.db import transaction
from django.utils import timezone

from apps.metering.pricing.services.pricing_service import PricingError
from apps.metering.usage.services.usage_service import (
    EffectiveAtError, UsageService, validate_effective_at)
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task

logger = logging.getLogger(__name__)


class IngestAppendFailed(Exception):
    """The durable raw append failed. Raised only AFTER compensation ran —
    every hold taken for the batch released, every freshly-SET idem key
    unwound — so the endpoint's problem mapping (503 service_unavailable,
    "retry the whole batch") is a pure translation with no money logic."""


def usage_kwargs(item):
    """The single↔batch pass-through, written ONCE (#112): the field-for-
    field map from a request item (RecordUsageRequest — the batch and ingest
    items share the schema) onto record_usage's keyword surface."""
    return dict(
        request_id=item.request_id,
        idempotency_key=item.idempotency_key,
        provider_cost_micros=item.provider_cost_micros,
        billed_cost_micros=item.billed_cost_micros,
        units=item.units,
        currency=item.currency,
        product_id=item.product_id,
        metadata=item.metadata,
        event_type=item.event_type,
        provider=item.provider,
        tags=item.tags,
        task_id=item.task_id,
        usage_metrics=item.usage_metrics,
        effective_at=item.effective_at,
    )


def usage_error(e):
    """The ONE record_usage error map (#112): exception → (code, detail).
    The specific-before-general order lives HERE and only here —
    PricingError first, then EffectiveAtError (which IS a ValueError, so it
    must be tested before the generic branch), then plain ValueError. The
    single endpoint raises the code as a Problem; the batch wraps the same
    code in a verdict dict."""
    if isinstance(e, PricingError):
        return "pricing_error", str(e)
    if isinstance(e, EffectiveAtError):
        return e.code, str(e)
    return "validation_error", str(e)


def with_uncosted(result):
    """Surface the provenance receipt's uncosted-metrics list on a success
    body — both sync ingestion surfaces return it."""
    provenance = result.get("pricing_provenance") or {}
    result["uncosted_metrics"] = provenance.get("uncosted_metrics", [])
    return result


def _rejected(code, detail):
    """A batch-item rejection verdict: the typed code plus the constant stop
    trio — a rejected item was never recorded, so nothing can have stopped."""
    return {"accepted": False, "code": code, "detail": detail,
            "stop": False, "stop_reason": None, "stop_scope": None}


def record_sync_item(tenant, item, customers, task_exists):
    """One batch item == one independent POST /usage, error mapping included.

    Mirrors the single endpoint's contract byte-for-byte as per-item VERDICT
    dicts (#78: one verdict field set with async ingest): a success mirrors
    the single-call success body (stop-verdict fields included) plus
    {"accepted": true}. 404s become per-item {"code": "not_found"}; the
    generic ValueError branch becomes {"code": "validation_error"} - every
    code from the registry. One-rule parity: a crossing verdict runs
    the same kill flow and the batch CONTINUES — later items on the killed
    task still land, bill, and carry the task_not_active stop verdict,
    identical to firing the same items as sequential singles.
    """
    cid = str(item.customer_id)
    if cid not in customers:
        customers[cid] = Customer.objects.filter(id=item.customer_id, tenant=tenant).first()
    customer = customers[cid]
    if customer is None:
        return _rejected("not_found", "Customer not found")
    if item.task_id is not None:
        task_key = (cid, str(item.task_id))
        if task_key not in task_exists:
            task_exists[task_key] = Task.objects.filter(
                id=item.task_id, tenant=tenant, customer=customer).exists()
        if not task_exists[task_key]:
            return _rejected("not_found", "Task not found")
    try:
        result = UsageService.record_usage(
            tenant=tenant, customer=customer, **usage_kwargs(item))
    except (PricingError, ValueError) as e:
        return _rejected(*usage_error(e))
    return {"accepted": True, **with_uncosted(result)}


# --- Async accept (estimate -> atomic hold -> durable append) ---

# 30s L1 cache: {task_id: (customer_id_str_or_None, expires_monotonic)} — ONE
# batched Task.objects.values() read per ingest call for any task_ids not
# already cached/fresh, instead of a query per event. Existence/ownership
# ONLY (one-rule #37): a task's STATUS never gates acceptance — events for a
# non-active task are accepted, held, and get their task_not_active verdict
# at settle. customer_id None = no such task (sentinel for retry storms).
# Clear-on-full bound mirrors CardCache._l1 (not an LRU).
_TASK_META_CACHE: dict = {}
_TASK_META_TTL_SECONDS = 30
_TASK_META_MAX = 4096


def reset_task_meta_cache():
    """The cache's OWNED reset surface (#113): test fixtures (and any future
    ops hook) call this instead of clearing the private dict."""
    _TASK_META_CACHE.clear()


def _task_meta_for(tenant, task_ids):
    if not task_ids:
        return {}
    now_mono = time.monotonic()
    # The return dict is built from LOCAL captures only — never by re-reading
    # the module cache at the end. The clear-on-full below wipes entries that
    # are fresh for THIS call, so a final read-back would KeyError whenever a
    # batch mixes a cached task with an uncached one at the size bound.
    out = {}
    missing = []
    for tid in task_ids:
        hit = _TASK_META_CACHE.get(tid)
        if hit is not None and hit[1] > now_mono:
            out[tid] = hit  # captured before any clear-on-full can wipe it
        else:
            missing.append(tid)
    if missing:
        rows = Task.objects.filter(tenant=tenant, id__in=missing).values(
            "id", "customer_id")
        if len(_TASK_META_CACHE) >= _TASK_META_MAX:
            _TASK_META_CACHE.clear()  # crude bound; `out` already holds this call's hits
        for row in rows:
            tid = str(row["id"])
            entry = (str(row["customer_id"]), now_mono + _TASK_META_TTL_SECONDS)
            _TASK_META_CACHE[tid] = entry
            out[tid] = entry
        for tid in missing:
            if tid not in out:
                # No such task (wrong tenant / never existed) — cache a
                # sentinel so a hot retry-storm of a bad task_id still costs
                # one query per TTL window, not one per event.
                entry = (None, now_mono + _TASK_META_TTL_SECONDS)
                _TASK_META_CACHE[tid] = entry
                out[tid] = entry
    return out


def _idem_key(tenant_id, customer_id, idempotency_key):
    return f"ubb:idem:{tenant_id}:{customer_id}:{idempotency_key}"


def _ingest_redis():
    from django.conf import settings
    import redis
    return redis.from_url(settings.REDIS_URL)


def _ingest_idem_prefilter(tenant_id, keys):
    """Pipelined SETNX pre-filter for a whole batch, one Redis round trip.

    keys: full ubb:idem:* key strings (see _idem_key). Returns list[bool]
    positionally aligned: True = idem-HIT (the key already existed — a
    duplicate suspect), False = first time seen (the key is now SET, 7-day
    TTL). Fails OPEN (every key reads as "first time") on any Redis error,
    mirroring every other Tier-2 gate's fail-open contract — the durable
    RawIngestEvent log (NO unique constraint, by design) and UsageEvent's
    real idempotency constraint at settle time remain the backstop against a
    double-hold false negative here.
    """
    if not keys:
        return []
    try:
        pipe = _ingest_redis().pipeline()
        for k in keys:
            pipe.set(k, 1, nx=True, ex=604800)
        raw = pipe.execute()
        return [not bool(r) for r in raw]
    except Exception:
        logger.warning("ingest.idem_prefilter_failed", extra={"data": {"tenant_id": str(tenant_id)}})
        return [False] * len(keys)


def _ingest_idem_present(tenant_id, keys):
    """Read-only presence probe (pipelined EXISTS — never writes) for the
    replay-wins path: an effective_at-rejected item is treated as an
    idempotent REPLAY (accepted, duplicate_suspect, no hold) if its key is
    already present, mirroring the sync path's replay-before-validation
    contract in UsageService.record_usage. Fails CLOSED to "absent" — the
    caller then rejects with the validation code rather than accepting
    unheld spend on an unverifiable replay claim.
    """
    if not keys:
        return []
    try:
        pipe = _ingest_redis().pipeline()
        for k in keys:
            pipe.exists(k)
        return [bool(r) for r in pipe.execute()]
    except Exception:
        logger.warning("ingest.idem_probe_failed", extra={"data": {"tenant_id": str(tenant_id)}})
        return [False] * len(keys)


def _ingest_idem_unwind(tenant_id, keys):
    """Best-effort pipelined DELETE of the idem keys THIS request freshly SET
    — the append-failure unwind. Must run BEFORE IngestAppendFailed is raised
    so the client's retry of the same batch re-enters the full estimate+hold
    gate instead of misreading as all idem-hits (which would append
    held=False rows with no hold ever taken — a money-gate bypass on the
    DESIGNED recovery path). A key stranded by a failure HERE is exactly that
    known bypass for one event, so the failure is logged at ERROR, loudly.
    """
    if not keys:
        return
    try:
        pipe = _ingest_redis().pipeline()
        for k in keys:
            pipe.delete(k)
        pipe.execute()
    except Exception:
        logger.error("ingest.idem_unwind_failed", extra={"data": {
            "tenant_id": str(tenant_id), "stranded_keys": len(keys)}})


def _ingest_verdict(*, accepted, mode, estimated_cost_micros=None,
                    code=None, detail=None, stop=False, stop_reason=None,
                    stop_scope=None, duplicate_suspect=False):
    return {
        "accepted": accepted, "code": code, "detail": detail,
        "estimated_cost_micros": estimated_cost_micros,
        "stop": stop, "stop_reason": stop_reason, "stop_scope": stop_scope,
        "mode": mode, "duplicate_suspect": duplicate_suspect,
    }


def _sync_fallback_verdict(sync_result):
    """Translate a `record_sync_item` result (Unpriceable route) into the
    ingest per-item verdict shape, mode='sync_fallback'."""
    if sync_result.get("accepted"):
        return {
            "accepted": True, "code": None, "detail": None,
            "estimated_cost_micros": sync_result.get("billed_cost_micros"),
            "stop": sync_result.get("stop", False), "stop_reason": sync_result.get("stop_reason"),
            "stop_scope": sync_result.get("stop_scope"),
            "mode": "sync_fallback", "duplicate_suspect": False,
            "event_id": sync_result.get("event_id"),
        }
    return {
        "accepted": False, "code": sync_result.get("code"),
        "detail": sync_result.get("detail"), "estimated_cost_micros": None,
        "stop": False, "stop_reason": None, "stop_scope": None,
        "mode": "sync_fallback", "duplicate_suspect": False,
    }


def _kick_settle(tenant_id):
    """Post-commit settle doorbell — broker errors are swallowed + logged
    (delivery spec §A, #43). The durable raw rows are the queue and the 10s
    beat sweep re-dispatches them; a dead broker at accept costs seconds of
    settle latency, never a 5xx for money that durably landed."""
    from apps.metering.usage.tasks import settle_raw_events

    try:
        settle_raw_events.delay()
    except Exception:
        logger.warning("ingest.settle_dispatch_failed",
                       extra={"data": {"tenant_id": tenant_id}})


def accept_batch(tenant, items):
    """The async accept pipeline: estimate -> atomic hold -> durable raw
    append -> positionally-aligned 202-style verdict dicts. Exact pricing
    settles in workers (estimate-hold-settle; see
    docs/plans/2026-07-03-async-ingestion-hard-stop-design.md). Settlement is
    claimed by the settle_raw_events task — this pipeline's only durability
    contract is that every held/duplicate-suspect item lands in
    RawIngestEvent before the verdicts are returned; the append failing
    raises IngestAppendFailed after full compensation (holds released, fresh
    idem keys unwound).

    No ambient transaction required: the raw append is its own durability
    boundary, and the settle doorbell rides transaction.on_commit (which
    fires immediately when no atomic block is open).
    """
    from apps.metering.pricing.services.card_cache import CardCache
    from apps.metering.pricing.services.markup_cache import MarkupCache
    from apps.metering.pricing.services.pricing_service import PricingService, Unpriceable
    from apps.billing.queries import acquire_ingest_holds, release_ingest_hold, read_live_stop
    from apps.metering.usage.models import RawIngestEvent

    n = len(items)
    results: list = [None] * n
    customers: dict = {}
    owners: dict = {}
    task_exists: dict = {}  # threaded into record_sync_item for the sync-fallback route
    item_customer: list = [None] * n
    eff_rejected: dict = {}   # i -> EffectiveAtError code, pending the replay probe
    forced_replay: set = set()  # replay-wins winners (probed idem key present)

    now = timezone.now()
    tenant_currency = (tenant.default_currency or "usd").lower()
    CardCache.begin_request(tenant.id)
    MarkupCache.begin_request(tenant.id)

    # ---- resolve customers + owners once per customer; validate currency +
    # effective_at. validate_effective_at is the sanctioned per-event ORM
    # exception (closed-period guard queries the owner's invoice) and runs
    # ONLY for effective_at-bearing items — the common path stays query-free.
    # Estimation deliberately stays on the current-month tier mirror even for
    # backdated items (conservative enough; settle prices as_of exactly). ----
    for i, item in enumerate(items):
        cid = str(item.customer_id)
        if cid not in customers:
            customers[cid] = Customer.objects.filter(id=item.customer_id, tenant=tenant).first()
        customer = customers[cid]
        if customer is None:
            results[i] = _ingest_verdict(accepted=False, code="not_found",
                                         mode="async")
            continue
        if cid not in owners:
            owners[cid] = customer.resolve_billing_owner().id
        if item.currency and str(item.currency).strip().lower() != tenant_currency:
            results[i] = _ingest_verdict(accepted=False, code="validation_error",
                                         mode="async")
            continue
        if item.effective_at is not None:
            try:
                validate_effective_at(tenant, owners[cid], item.effective_at, now)
            except EffectiveAtError as e:
                # Not rejected yet: replay-wins first (probe below). The
                # customer is valid, so keep it resolvable for the replay
                # append path.
                eff_rejected[i] = e.code
                item_customer[i] = customer
                continue
        item_customer[i] = customer

    # ---- replay-wins for effective_at-rejected items (mirrors the sync
    # path's replay-before-validation contract in record_usage): a replayed
    # key whose FIRST accept already passed
    # validation must be accepted as a duplicate suspect (held=False append,
    # no hold) even if the backfill window has since aged past the timestamp
    # or the billing period closed — a whole-batch retry must not flip an
    # already-accepted item into a rejection. Read-only EXISTS probe — never
    # SETNX; absent => genuinely new spend, rejected with the validation code
    # WITHOUT writing the key (the probe fails CLOSED to "absent"). ----
    if eff_rejected:
        eff_idx = list(eff_rejected)
        probe_keys = [_idem_key(tenant.id, items[i].customer_id, items[i].idempotency_key)
                      for i in eff_idx]
        for i, present in zip(eff_idx, _ingest_idem_present(tenant.id, probe_keys)):
            if present:
                forced_replay.add(i)
            else:
                results[i] = _ingest_verdict(accepted=False, code=eff_rejected[i],
                                             mode="async")

    # ---- task existence/ownership check (30s L1 cache). One-rule (#37): a
    # task's STATUS never gates acceptance — the accept-time dead-unit reject
    # is retired, and events for a non-active task are accepted, held, and
    # get their task_not_active verdict at settle (accept now matches
    # settle). Only a task that does not exist for this tenant+customer is
    # rejected — like an unknown customer, that request genuinely cannot be
    # recorded. Runs BEFORE the idempotency SETNX: a locally-rejected item
    # must NOT burn its idem key, or the client's legitimate retry (after
    # fixing the bogus task_id) would misread as an idem-hit and be appended
    # held=False — accepted spend with NO hold ever taken. A task is never
    # hard-deleted, so an unknown task can never be a replay of an
    # already-accepted item — no replay-wins probe needed here. ----
    task_ids_needed = {str(items[i].task_id) for i in range(n)
                       if results[i] is None and i not in forced_replay
                       and items[i].task_id is not None}
    task_meta = _task_meta_for(tenant, task_ids_needed)
    for i in range(n):
        # forced_replay items (effective_at replay-wins above) are already
        # known replays of accepted items — their task passed this check at
        # first accept.
        if results[i] is not None or i in forced_replay:
            continue
        item = items[i]
        if item.task_id is not None:
            meta = task_meta.get(str(item.task_id))
            if meta is None or meta[0] != str(item_customer[i].id):
                results[i] = _ingest_verdict(accepted=False, code="not_found",
                                             mode="async")

    # ---- idempotency pre-filter: one pipelined redis round trip for the
    # whole batch, only for items still viable after EVERY local rejection
    # above (customer/currency/effective_at validation, unknown task).
    # forced_replay items are already known replays — no SETNX needed. ----
    pending_idx = [i for i in range(n) if results[i] is None and i not in forced_replay]
    idem_keys = [_idem_key(tenant.id, items[i].customer_id, items[i].idempotency_key)
                 for i in pending_idx]
    idem_hits = dict(zip(pending_idx, _ingest_idem_prefilter(tenant.id, idem_keys)))
    # Keys THIS request freshly SET — deleted again if the raw append fails,
    # so the retry re-enters the estimate+hold gate (see _ingest_idem_unwind).
    fresh_idem_keys = [k for i, k in zip(pending_idx, idem_keys) if not idem_hits[i]]

    # ---- per item: idem routing, estimate (Unpriceable -> sync fallback).
    # Estimation deliberately stays AFTER the idem check: an idem-hit takes no
    # hold so it needs no estimate, and skipping the estimate for an
    # Unpriceable replay is safe because the sync_fallback route is already
    # idempotent through record_usage's own (tenant, customer,
    # idempotency_key) replay path. ----
    hold_candidates: list = []   # (i, item, customer, owner_id, Estimate)
    append_only: list = []       # (i, item, customer, owner_id) idem-hit rows
    owner_stop_cache: dict = {}
    for i in range(n):
        if results[i] is not None:  # forced_replay items are still None here
            continue
        item = items[i]
        customer = item_customer[i]
        owner_id = owners[str(item.customer_id)]
        if i in forced_replay or idem_hits[i]:
            if owner_id not in owner_stop_cache:
                owner_stop_cache[owner_id] = read_live_stop(owner_id, tenant)
            results[i] = _ingest_verdict(accepted=True, duplicate_suspect=True,
                                         estimated_cost_micros=0, mode="async",
                                         **owner_stop_cache[owner_id])
            append_only.append((i, item, customer, owner_id))
            continue
        try:
            est = PricingService.estimate(
                tenant, customer, event_type=item.event_type or "",
                provider=item.provider or "", usage_metrics=item.usage_metrics,
                tags=item.tags, currency=tenant_currency,
                caller_billed=item.billed_cost_micros,
                caller_provider_cost=item.provider_cost_micros,
                units=item.units)
        except Unpriceable:
            sync_result = record_sync_item(tenant, item, customers, task_exists)
            results[i] = _sync_fallback_verdict(sync_result)
            if not sync_result.get("accepted"):
                # This item's idem key was already SET by the prefilter above
                # (it was a pending_idx miss, not a forced_replay/idem-hit),
                # but the inline sync fallback REJECTED it (e.g. a strict-
                # coverage PricingError) — no RawIngestEvent/UsageEvent was
                # ever created for it. Left burned, a retry would misread as
                # an idem-hit: accepted, held=False append, no hold ever
                # taken (a money-gate bypass), and settle would then re-raise
                # the SAME poison payload -> poisons to "failed" -> a false
                # incident alert. Unwind just this one key so the retry is a
                # genuine first attempt (mirrors the append-failure unwind
                # below, scoped per-item instead of whole-batch).
                _ingest_idem_unwind(
                    tenant.id,
                    [_idem_key(tenant.id, item.customer_id, item.idempotency_key)])
            continue
        hold_candidates.append((i, item, customer, owner_id, est))

    acquire_by_owner: dict = {}
    for i, item, customer, owner_id, est in hold_candidates:
        acquire_by_owner.setdefault(owner_id, []).append((i, item, customer, est))

    # ---- acquire holds (one pipelined redis round trip per owner). One-rule
    # (#37): the acquire ALWAYS holds, against the wallet only — the
    # accept-time unit-cap lane is retired unreplaced (task limits are
    # COGS-denominated and exact provider cost exists only at settle; an
    # accept-time compare of a billed estimate against a COGS limit would be
    # denominationally dishonest). No item is ever rejected for limit
    # reasons; the wallet-floor crossing detection stays cooperative. ----
    raw_objs: list = []
    # (owner_id, estimate_micros, effective_at) for held rows -- effective_at
    # threads the I9 prior-month guard through release (see
    # LiveCounter.settle) so undoing a hold here mirrors exactly what
    # the hold did (a skipped-livespend hold must be released as a skipped-
    # livespend release, not a full current-month credit-back).
    release_list: list = []

    for i, item, customer, owner_id in append_only:
        raw_objs.append(RawIngestEvent(
            tenant=tenant, customer=customer, billing_owner_id=owner_id,
            task_id=item.task_id, idempotency_key=item.idempotency_key,
            payload=item.model_dump(mode="json"), estimate_micros=0,
            estimate_exact=False, held=False))

    for owner_id, entries in acquire_by_owner.items():
        acquire_payload = [{"estimate_micros": est.micros,
                            "effective_at": item.effective_at}
                           for (_, item, _, est) in entries]
        verdicts = acquire_ingest_holds(owner_id, tenant, acquire_payload)
        for (i, item, customer, est), v in zip(entries, verdicts):
            results[i] = _ingest_verdict(accepted=True, estimated_cost_micros=est.micros,
                                         mode="async", stop=v["stop"],
                                         stop_reason=v["stop_reason"], stop_scope=v["stop_scope"])
            # v["held"] is the hold service's own answer to "was money
            # actually reserved" — False with arrival signals off (#46, §E:
            # accept does no live-counter Redis work), so settle trues up
            # only holds that were really taken and the append-failure
            # unwind below releases nothing that was never reserved.
            raw_objs.append(RawIngestEvent(
                tenant=tenant, customer=customer, billing_owner_id=owner_id,
                task_id=item.task_id, idempotency_key=item.idempotency_key,
                payload=item.model_dump(mode="json"), estimate_micros=est.micros,
                estimate_exact=est.exact, held=v["held"]))
            if v["held"]:
                release_list.append((owner_id, est.micros, item.effective_at))

    # ---- durability boundary: the raw append. On failure, undo every hold
    # taken above (never leave money reserved for a batch that never landed)
    # AND delete the idem keys this request freshly set (or the client's
    # retry of this same batch would read as all idem-hits and bypass the
    # estimate+hold gate entirely), then raise the typed failure so the
    # caller surfaces a 5xx and the client retries the whole batch. ----
    if raw_objs:
        try:
            RawIngestEvent.objects.bulk_create(raw_objs)
        except Exception:
            logger.exception("ingest.append_failed", extra={"data": {
                "tenant_id": str(tenant.id), "count": len(raw_objs)}})
            for owner_id, estimate_micros, effective_at in release_list:
                release_ingest_hold(owner_id, tenant, estimate_micros,
                                    effective_at=effective_at)
            _ingest_idem_unwind(tenant.id, fresh_idem_keys)
            raise IngestAppendFailed("raw ingest append failed")
        # Kick the settle workers once the raws are durably committed — the
        # 10s beat sweep (settle-raw-events) is the backstop for a lost
        # dispatch, so this on_commit hook is a fast-path nicety, not a
        # durability requirement. Broker errors are swallowed + logged
        # (delivery spec §A, #43): the raws are durably accepted, and a
        # post-commit raise would 5xx a response whose money already landed.
        transaction.on_commit(lambda: _kick_settle(str(tenant.id)))

    # One-rule (#37): no accept-time kill parity remains — task-limit
    # detection (and the kill flow + task.limit_exceeded) moved to settle,
    # where exact provider costs exist (see UsageService.settle_raw).

    return results
