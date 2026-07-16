import logging
import re
from datetime import date, datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Sum, Count, Q
from django.db.models.fields.json import KeyTextTransform
from django.shortcuts import get_object_or_404
from ninja import NinjaAPI, Query

from core.auth import ApiKeyAuth, ProductAccess
from core.time_windows import utc_day_start, utc_next_day_start
from django.utils import timezone

from api.v1.schemas import (
    RecordUsageRequest, RecordUsageResponse,
    UsageBatchRequest, UsageBatchResponse,
    IngestBatchRequest, IngestBatchResponse,
    PaginatedUsageResponse,
    UsageEventDetailOut,
    TenantMarkupIn, TenantMarkupOut,
    CloseTaskResponse,
    UsageAnalyticsResponse,
    UsageTimeseriesResponse,
    RateIn, RateOut, BookIn, BookOut, RateChangeIn, PublishIn, AssignIn,
)
from apps.metering.pricing.models import (
    Rate, RateCard, RateCardAssignment,
    CARD_TYPE_CHOICES, PRICING_MODEL_CHOICES,
)
from api.v1.pagination import encode_cursor, apply_cursor_filter
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent

logger = logging.getLogger(__name__)

metering_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_metering_v1")

_product_check = ProductAccess("metering")


def _apply_task_kill(tenant, customer, task_id, result):
    """One-rule (#37): a task-scoped crossing verdict on the result drives the
    idempotent kill flow (active->killed flip + task.limit_exceeded on the
    winning transition). The event is ALREADY recorded and billed — the kill
    is a signal, never a wall, so this runs after record_usage returned, in
    its own transaction, and never raises (a kill failure must not turn a
    recorded event into a non-200)."""
    from apps.platform.tasks import reasons
    from apps.platform.tasks.services import TaskService
    if (task_id is not None and result.get("stop_scope") == "task"
            and result.get("stop_reason") in (reasons.TASK_LIMIT,
                                              reasons.CUSTOMER_FLOOR)):
        TaskService.kill_and_announce(
            task_id, result["stop_reason"],
            tenant_id=tenant.id, customer_id=customer.id)


@metering_api.post("/usage", response={200: RecordUsageResponse})
def record_usage(request, payload: RecordUsageRequest):
    """Record one usage event. One-rule contract: every event that reaches
    UBB is priced, recorded, and billed with an HTTP 200 — including the
    tipping event that crosses a limit and everything arriving after a kill.
    The stop instruction rides the response fields (stop / stop_reason /
    stop_scope); a non-200 always means "this was not recorded" (auth,
    malformed payload, unknown customer/task, pricing/validation errors)."""
    _product_check(request)

    from apps.metering.pricing.services.pricing_service import PricingError
    from apps.metering.usage.services.usage_service import EffectiveAtError

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    if payload.task_id is not None:
        get_object_or_404(Task, id=payload.task_id, tenant=request.auth.tenant, customer=customer)
    try:
        result = UsageService.record_usage(
            tenant=request.auth.tenant,
            customer=customer,
            request_id=payload.request_id,
            idempotency_key=payload.idempotency_key,
            provider_cost_micros=payload.provider_cost_micros,
            billed_cost_micros=payload.billed_cost_micros,
            units=payload.units,
            currency=payload.currency,
            product_id=payload.product_id,
            metadata=payload.metadata,
            event_type=payload.event_type,
            provider=payload.provider,
            tags=payload.tags,
            task_id=payload.task_id,
            usage_metrics=payload.usage_metrics,
            effective_at=payload.effective_at,
        )
    except PricingError as e:
        return metering_api.create_response(
            request, {"error": "pricing_error", "detail": str(e)}, status=422)
    except EffectiveAtError as e:
        # MUST precede the ValueError branch below (EffectiveAtError IS a
        # ValueError) so the typed code survives to the response body.
        return metering_api.create_response(
            request, {"error": e.code, "detail": str(e)}, status=422)
    except ValueError as e:
        from ninja.errors import HttpError
        raise HttpError(422, str(e))
    _apply_task_kill(request.auth.tenant, customer, payload.task_id, result)
    provenance = result.get("pricing_provenance") or {}
    result["uncosted_metrics"] = provenance.get("uncosted_metrics", [])
    return result


def _record_batch_item(request, tenant, item, customers, task_exists):
    """One batch item == one independent POST /usage, error mapping included.

    Mirrors the single endpoint's contract byte-for-byte as per-item result
    dicts: a success mirrors the single-call success body (stop-verdict
    fields included) plus {"ok": true}. 404s become per-item
    {"error": "not_found"}; the generic ValueError branch becomes
    {"error": "validation_error"}. One-rule parity: a crossing verdict runs
    the same kill flow and the batch CONTINUES — later items on the killed
    task still land, bill, and carry the task_not_active stop verdict,
    identical to firing the same items as sequential singles.
    """
    from apps.metering.pricing.services.pricing_service import PricingError
    from apps.metering.usage.services.usage_service import EffectiveAtError

    cid = str(item.customer_id)
    if cid not in customers:
        customers[cid] = Customer.objects.filter(id=item.customer_id, tenant=tenant).first()
    customer = customers[cid]
    if customer is None:
        return {"ok": False, "error": "not_found", "detail": "Customer not found"}
    if item.task_id is not None:
        task_key = (cid, str(item.task_id))
        if task_key not in task_exists:
            task_exists[task_key] = Task.objects.filter(
                id=item.task_id, tenant=tenant, customer=customer).exists()
        if not task_exists[task_key]:
            return {"ok": False, "error": "not_found", "detail": "Task not found"}
    try:
        result = UsageService.record_usage(
            tenant=tenant,
            customer=customer,
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
    except PricingError as e:
        return {"ok": False, "error": "pricing_error", "detail": str(e)}
    except EffectiveAtError as e:
        return {"ok": False, "error": e.code, "detail": str(e)}
    except ValueError as e:
        return {"ok": False, "error": "validation_error", "detail": str(e)}
    _apply_task_kill(tenant, customer, item.task_id, result)
    provenance = result.get("pricing_provenance") or {}
    result["uncosted_metrics"] = provenance.get("uncosted_metrics", [])
    return {"ok": True, **result}


@metering_api.post("/usage/batch", response={200: UsageBatchResponse})
def record_usage_batch(request, payload: UsageBatchRequest):
    """Batch ingestion: 1..100 INDEPENDENT items (>100 or 0 → 422).

    Each item runs the same per-item record_usage in its own atomic commit —
    deliberately NOT one mega-transaction, which would hold Task/counter locks
    for the whole batch, delay outbox dispatch, and diverge from the semantics
    of N sequential singles. Always HTTP 200 with positionally-aligned
    results[] + succeeded/failed counts; per-item idempotency makes a
    whole-batch replay return the original event ids with zero new rows, and
    a duplicate idempotency_key WITHIN one batch resolves to the first item's
    event id (the first item commits before the second runs).
    """
    _product_check(request)
    tenant = request.auth.tenant
    customers: dict = {}
    task_exists: dict = {}
    results = [_record_batch_item(request, tenant, item, customers, task_exists)
               for item in payload.events]
    succeeded = sum(1 for r in results if r.get("ok"))
    return {"results": results, "succeeded": succeeded,
            "failed": len(results) - succeeded}


# --- Async ingest (estimate -> atomic hold -> durable append) ---

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


def _task_meta_for(tenant, task_ids):
    import time
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
    — the append-failure unwind. Must run BEFORE the 503 is raised so the
    client's retry of the same batch re-enters the full estimate+hold gate
    instead of misreading as all idem-hits (which would append held=False
    rows with no hold ever taken — a money-gate bypass on the DESIGNED
    recovery path). A key stranded by a failure HERE is exactly that known
    bypass for one event, so the failure is logged at ERROR, loudly.
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


def _ingest_verdict(*, accepted, mode, estimated_cost_micros=None, rejected=False,
                    reason=None, stop=False, stop_reason=None, stop_scope=None,
                    duplicate_suspect=False):
    return {
        "accepted": accepted, "estimated_cost_micros": estimated_cost_micros,
        "stop": stop, "stop_reason": stop_reason, "stop_scope": stop_scope,
        "rejected": rejected, "reason": reason, "mode": mode,
        "duplicate_suspect": duplicate_suspect,
    }


def _sync_fallback_verdict(sync_result):
    """Translate a `_record_batch_item` result (Unpriceable route) into the
    ingest per-item verdict shape, mode='sync_fallback'."""
    if sync_result.get("ok"):
        return {
            "accepted": True, "estimated_cost_micros": sync_result.get("billed_cost_micros"),
            "stop": sync_result.get("stop", False), "stop_reason": sync_result.get("stop_reason"),
            "stop_scope": sync_result.get("stop_scope"), "rejected": False, "reason": None,
            "mode": "sync_fallback", "duplicate_suspect": False,
            "event_id": sync_result.get("event_id"),
        }
    return {
        "accepted": False, "estimated_cost_micros": None, "stop": False,
        "stop_reason": None, "stop_scope": None, "rejected": True,
        "reason": sync_result.get("error"), "mode": "sync_fallback",
        "duplicate_suspect": False,
    }


@metering_api.post("/usage/ingest", response={200: IngestBatchResponse})
def ingest_usage_batch(request, payload: IngestBatchRequest):
    """Async accept path: estimate -> atomic hold -> durable raw append -> 202-style
    verdicts. Exact pricing settles in workers (estimate-hold-settle; see
    docs/plans/2026-07-03-async-ingestion-hard-stop-design.md). Settlement is
    claimed by the settle_raw_events task (wired in the settlement change) —
    this endpoint's only durability contract is that every held/duplicate-
    suspect item lands in RawIngestEvent before the response is returned.
    """
    _product_check(request)
    tenant = request.auth.tenant
    if "metering_async" not in (tenant.products or []):
        return metering_api.create_response(
            request, {"error": "feature_not_enabled"}, status=403)

    from ninja.errors import HttpError
    from apps.metering.pricing.services.card_cache import CardCache
    from apps.metering.pricing.services.markup_cache import MarkupCache
    from apps.metering.pricing.services.estimation_service import EstimationService, Unpriceable
    from apps.metering.usage.services.usage_service import EffectiveAtError, validate_effective_at
    from apps.billing.queries import acquire_ingest_holds, release_ingest_hold, read_live_stop
    from apps.metering.usage.models import RawIngestEvent

    items = payload.events
    n = len(items)
    results: list = [None] * n
    customers: dict = {}
    owners: dict = {}
    task_exists: dict = {}  # threaded into _record_batch_item for the sync-fallback route
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
            results[i] = _ingest_verdict(accepted=False, rejected=True,
                                         reason="not_found", mode="async")
            continue
        if cid not in owners:
            owners[cid] = customer.resolve_billing_owner().id
        if item.currency and str(item.currency).strip().lower() != tenant_currency:
            results[i] = _ingest_verdict(accepted=False, rejected=True,
                                         reason="validation_error", mode="async")
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
                results[i] = _ingest_verdict(accepted=False, rejected=True,
                                             reason=eff_rejected[i], mode="async")

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
                results[i] = _ingest_verdict(accepted=False, rejected=True,
                                             reason="not_found", mode="async")

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
            est = EstimationService.estimate(
                tenant=tenant, customer=customer, event_type=item.event_type or "",
                provider=item.provider or "", usage_metrics=item.usage_metrics,
                tags=item.tags, currency=tenant_currency,
                caller_billed=item.billed_cost_micros,
                caller_provider_cost=item.provider_cost_micros,
                units=item.units)
        except Unpriceable:
            sync_result = _record_batch_item(request, tenant, item, customers, task_exists)
            results[i] = _sync_fallback_verdict(sync_result)
            if not sync_result.get("ok"):
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
    # HoldService.settle) so undoing a hold here mirrors exactly what
    # acquire() did (a skipped-livespend hold must be released as a skipped-
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
            raw_objs.append(RawIngestEvent(
                tenant=tenant, customer=customer, billing_owner_id=owner_id,
                task_id=item.task_id, idempotency_key=item.idempotency_key,
                payload=item.model_dump(mode="json"), estimate_micros=est.micros,
                estimate_exact=est.exact, held=True))
            release_list.append((owner_id, est.micros, item.effective_at))

    # ---- durability boundary: the raw append. On failure, undo every hold
    # taken above (never leave money reserved for a batch that never landed)
    # AND delete the idem keys this request freshly set (or the client's
    # retry of this same batch would read as all idem-hits and bypass the
    # estimate+hold gate entirely), then surface a 5xx so the caller retries
    # the whole batch. ----
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
            raise HttpError(503, "raw ingest append failed")
        # Kick the settle workers once the raws are durably committed — the
        # 10s beat sweep (settle-raw-events) is the backstop for a lost
        # dispatch, so this on_commit hook is a fast-path nicety, not a
        # durability requirement.
        from apps.metering.usage.tasks import settle_raw_events
        transaction.on_commit(lambda: settle_raw_events.delay())

    # One-rule (#37): no accept-time kill parity remains — task-limit
    # detection (and the kill flow + task.limit_exceeded) moved to settle,
    # where exact provider costs exist (see UsageService.settle_raw).

    accepted = sum(1 for r in results if r["accepted"])
    return {"results": results, "accepted": accepted, "rejected": n - accepted}


@metering_api.get("/ops/ingest-health", auth=None, include_in_schema=False)
def ops_ingest_health(request, tenant_id: str = None):
    """Operator-facing pipeline health (spec §3) — deliberately NOT behind
    ApiKeyAuth: tenant keys must not grant ops visibility. Gated on the
    deployment-level UBB_OPS_TOKEN via constant-time compare; when the
    setting is unset the endpoint 404s (fail closed, invisible).
    Excluded from the OpenAPI schema/docs (include_in_schema=False) — the
    schema is public and unauthenticated, so listing this route there would
    fingerprint it regardless of the token gate below."""
    import hmac
    from django.conf import settings as dj_settings
    from django.views.defaults import page_not_found
    token = getattr(dj_settings, "UBB_OPS_TOKEN", "")
    if not token:
        # Same handler Django uses for an unmatched route in production —
        # NOT ninja's JSON 404 — so this response is byte-for-byte
        # indistinguishable from a path that was never registered at all.
        return page_not_found(request, exception=None)
    supplied = request.headers.get("X-Ops-Token", "")
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        return metering_api.create_response(
            request, {"error": "unauthorized"}, status=401)
    # Manual parse, AFTER both token gates: keeping the param typed as `str`
    # (not `UUID`) means ninja never 422s a malformed tenant_id before the
    # token check runs — that would let an unauthenticated caller distinguish
    # "wrong shape" from "not found" and re-open the fingerprinting hole.
    parsed_tenant_id = None
    if tenant_id:
        try:
            parsed_tenant_id = UUID(tenant_id)
        except ValueError:
            return metering_api.create_response(
                request, {"error": "invalid_tenant_id"}, status=422)
    from apps.metering.usage.services.ingest_health import ingest_health
    return ingest_health(tenant_id=parsed_tenant_id)


@metering_api.get("/customers/{customer_id}/usage", response=PaginatedUsageResponse)
def get_usage(request, customer_id: str, cursor: str = None, limit: int = 50,
              tag_key: str = None, tag_value: str = None):
    _product_check(request)

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    limit = min(max(limit, 1), 100)  # Clamp between 1 and 100

    qs = customer.usage_events.all().order_by("-effective_at", "-id")

    if tag_key and tag_value:
        qs = qs.filter(tags__contains={tag_key: tag_value})

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor)
        except ValueError:
            from ninja.errors import HttpError
            raise HttpError(400, "Invalid cursor")

    events = list(qs[:limit + 1])  # Fetch one extra to check has_more
    has_more = len(events) > limit
    events = events[:limit]

    next_cursor = None
    if has_more and events:
        last = events[-1]
        next_cursor = encode_cursor(last.effective_at, last.id)

    return {
        "data": [
            {
                "id": e.id,
                "request_id": e.request_id,
                "event_type": e.event_type,
                "provider": e.provider,
                "provider_cost_micros": e.provider_cost_micros,
                "billed_cost_micros": e.billed_cost_micros,
                "units": e.units,
                "metadata": e.metadata,
                "effective_at": e.effective_at.isoformat(),
            }
            for e in events
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@metering_api.get("/usage/{event_id}", response={200: UsageEventDetailOut, 404: dict})
def get_usage_event(request, event_id: UUID):
    """Fetch one usage event's full pricing receipt (audit / dispute lookup).

    Returns every priced field plus pricing_provenance — the recorded
    "why this amount" (engine version, price source, per-metric card, and
    tier-by-tier breakdown). The usage list omits provenance to stay lean;
    this is where it is read back. Tenant-scoped; 404 for an unknown or
    foreign event id."""
    _product_check(request)
    from apps.metering.usage.models import UsageEvent

    e = get_object_or_404(UsageEvent, id=event_id, tenant=request.auth.tenant)
    return 200, {
        "id": e.id,
        "request_id": e.request_id,
        "idempotency_key": e.idempotency_key,
        "event_type": e.event_type,
        "provider": e.provider,
        "product_id": e.product_id,
        "service_id": e.service_id,
        "agent_id": e.agent_id,
        "units": e.units,
        "currency": e.currency,
        "provider_cost_micros": e.provider_cost_micros,
        "billed_cost_micros": e.billed_cost_micros,
        "usage_metrics": e.usage_metrics or {},
        "pricing_provenance": e.pricing_provenance or {},
        "tags": e.tags,
        "metadata": e.metadata,
        "task_id": str(e.task_id) if e.task_id else None,
        "effective_at": e.effective_at.isoformat(),
        "created_at": e.created_at.isoformat(),
    }


# --- Task lifecycle ---


@metering_api.post("/tasks/{task_id}/close", response=CloseTaskResponse)
def close_task(request, task_id: UUID):
    _product_check(request)
    from apps.platform.tasks.services import TaskService

    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    completed = TaskService.complete_task(task.id)
    return {
        "task_id": str(completed.id),
        "status": completed.status,
        "total_billed_cost_micros": completed.total_billed_cost_micros,
        "total_provider_cost_micros": completed.total_provider_cost_micros,
        "event_count": completed.event_count,
    }


# --- Pricing Markup ---


@metering_api.get("/pricing/markup", response=TenantMarkupOut)
def get_tenant_markup(request):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markup = TenantMarkup.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if markup is None:
        return {"markup_percentage_micros": 0, "fixed_uplift_micros": 0}
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_api.put("/pricing/markup", response=TenantMarkupOut)
def upsert_tenant_markup(request, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markup, _ = TenantMarkup.objects.update_or_create(
        tenant=request.auth.tenant,
        customer=None,
        defaults={
            "markup_percentage_micros": payload.markup_percentage_micros,
            "fixed_uplift_micros": payload.fixed_uplift_micros,
        },
    )
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_api.get("/pricing/customers/{customer_id}/markup", response=TenantMarkupOut)
def get_customer_markup(request, customer_id: UUID):
    _product_check(request)
    from apps.metering.pricing.services.markup_service import MarkupService

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    markup = MarkupService.resolve(tenant=request.auth.tenant, customer=customer)
    if markup is None:
        return {"markup_percentage_micros": 0, "fixed_uplift_micros": 0}
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_api.put("/pricing/customers/{customer_id}/markup", response=TenantMarkupOut)
def upsert_customer_markup(request, customer_id: UUID, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    markup, _ = TenantMarkup.objects.update_or_create(
        tenant=request.auth.tenant,
        customer=customer,
        defaults={
            "markup_percentage_micros": payload.markup_percentage_micros,
            "fixed_uplift_micros": payload.fixed_uplift_micros,
        },
    )
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_api.delete("/pricing/customers/{customer_id}/markup")
def delete_customer_markup(request, customer_id: UUID):
    """Remove a customer's markup override so they revert to inheriting the
    tenant default. This is NOT the same as PUT-ing 0/0 — a 0/0 row still
    resolves as the customer's markup and SHADOWS the tenant default, pinning
    the customer at cost. Idempotent: 'no_override' when none existed; a bad
    customer id is a 404."""
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    markup = TenantMarkup.objects.filter(tenant=request.auth.tenant, customer=customer).first()
    if markup is None:
        return {"status": "no_override"}
    markup.delete()  # instance delete — the model layer bumps MarkupCache's version
    return {"status": "deleted"}


# --- Analytics ---


_ANALYTICS_ALLOWED_COLS = {"provider", "event_type", "product_id", "customer", "service_id", "agent_id"}


@metering_api.get("/analytics/usage", response={200: UsageAnalyticsResponse, 422: dict})
def usage_analytics(request, start_date: date = None, end_date: date = None,
                    customer_id: str = None, tag_key: str = None,
                    dimensions: list[str] = Query(None)):
    """Usage analytics with markup margin and customer/product/tag breakdowns."""
    _product_check(request)
    tenant = request.auth.tenant
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))
    if customer_id:
        qs = qs.filter(customer_id=customer_id)

    totals = qs.aggregate(
        total_events=Count("id"),
        total_billed_cost_micros=Sum("billed_cost_micros"),
        total_provider_cost_micros=Sum("provider_cost_micros"),
    )
    total_billed = totals["total_billed_cost_micros"] or 0
    total_provider = totals["total_provider_cost_micros"] or 0

    by_provider = list(
        qs.exclude(provider="").values("provider").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )
    by_event_type = list(
        qs.exclude(event_type="").values("event_type").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )
    by_customer = list(
        qs.values("customer__external_id").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )
    by_product = list(
        qs.exclude(product_id="").values("product_id").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )

    by_tag = []
    if tag_key:
        by_tag = list(
            qs.filter(tags__has_key=tag_key)
            .annotate(tag_value=KeyTextTransform(tag_key, "tags"))
            .values("tag_value")
            .annotate(
                event_count=Count("id"),
                total_cost_micros=Sum("billed_cost_micros"),
                total_provider_cost_micros=Sum("provider_cost_micros"),
            )
            .order_by("-total_cost_micros")
        )

    breakdowns: dict = {}
    if dimensions:
        if len(dimensions) > 6:
            return 422, {"error": "at most 6 dimensions"}
        for dim in dimensions:
            if dim.startswith("tag:"):
                key = dim[4:]
                if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key):
                    return 422, {"error": f"invalid tag dimension {dim}"}
                # Events that have the key (non-NULL dimension value).
                rows_with_key = list(
                    qs.filter(tags__has_key=key)
                    .annotate(dimension=KeyTextTransform(key, "tags"))
                    .values("dimension")
                    .annotate(
                        event_count=Count("id"),
                        total_provider_cost_micros=Sum("provider_cost_micros"),
                        total_billed_cost_micros=Sum("billed_cost_micros"),
                    )
                    .order_by("-total_billed_cost_micros")
                )
                # Events that are MISSING the key -> bucket as "(unattributed)".
                unattr_qs = qs.exclude(tags__has_key=key)
                unattr_agg = unattr_qs.aggregate(
                    event_count=Count("id"),
                    total_provider_cost_micros=Sum("provider_cost_micros"),
                    total_billed_cost_micros=Sum("billed_cost_micros"),
                )
                if (unattr_agg["event_count"] or 0) > 0:
                    rows_with_key.append({
                        "dimension": "(unattributed)",
                        "event_count": unattr_agg["event_count"] or 0,
                        "total_provider_cost_micros": unattr_agg["total_provider_cost_micros"] or 0,
                        "total_billed_cost_micros": unattr_agg["total_billed_cost_micros"] or 0,
                    })
                rows = sorted(rows_with_key, key=lambda r: -(r["total_billed_cost_micros"] or 0))
            elif dim in _ANALYTICS_ALLOWED_COLS:
                col = "customer__external_id" if dim == "customer" else dim
                # Run over the FULL qs (no exclusion) so every event is counted.
                # customer always has an external_id so no "(unattributed)" needed there.
                rows = list(
                    qs.values(col)
                    .annotate(
                        event_count=Count("id"),
                        total_provider_cost_micros=Sum("provider_cost_micros"),
                        total_billed_cost_micros=Sum("billed_cost_micros"),
                    )
                    .order_by("-total_billed_cost_micros")
                )
                for r in rows:
                    raw_val = r.pop(col)
                    # Map empty string or None to the sentinel for non-customer cols
                    if dim != "customer" and not raw_val:
                        raw_val = "(unattributed)"
                    r["dimension"] = raw_val
            else:
                return 422, {"error": f"unknown dimension {dim}"}
            breakdowns[dim] = rows

    return 200, {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": total_billed,
        "total_provider_cost_micros": total_provider,
        "usage_markup_margin_micros": total_billed - total_provider,
        "by_provider": by_provider,
        "by_event_type": by_event_type,
        "by_customer": by_customer,
        "by_product": by_product,
        "by_tag": by_tag,
        "breakdowns": breakdowns,
    }


@metering_api.get("/analytics/usage/timeseries", response={200: UsageTimeseriesResponse, 422: dict})
def usage_timeseries(request, granularity: str = "day", start_date: date = None, end_date: date = None,
                     customer_id: str = None, group_by: str = None):
    """Time-series spend rollup: daily or hourly COGS per tenant/customer.

    start_date and end_date are both INCLUSIVE calendar dates, matching the
    /analytics/usage rollup so the same inputs cover the same window on both.
    """
    _product_check(request)
    if granularity not in ("hour", "day"):
        return 422, {"error": "granularity must be hour or day"}
    if group_by is not None and group_by not in ("provider", "event_type", "product_id", "service_id", "agent_id"):
        return 422, {"error": "invalid group_by"}
    # guardrail: cap hourly windows to ~92 days
    if granularity == "hour" and start_date and end_date and (end_date - start_date).days > 92:
        return 422, {"error": "hourly window too large (max 92 days)"}
    from apps.metering.queries import get_usage_timeseries
    series = get_usage_timeseries(request.auth.tenant.id, granularity=granularity,
        customer_id=customer_id, group_by=group_by, start_date=start_date, end_date=end_date)
    return 200, {"granularity": granularity, "group_by": group_by or "", "series": series}


# --- Rate Cards ---

_billing_check = ProductAccess("billing")


def _book_to_out(b):
    return {
        "id": str(b.id),
        "card_type": b.card_type,
        "provider_key": b.provider_key,
        "key": b.key,
        "name": b.name,
        "currency": b.currency,
        "version": b.version,
        "is_default": b.is_default,
    }


def _rate_to_out(r):
    return {
        "id": str(r.id),
        "rate_card_id": str(r.rate_card_id) if r.rate_card_id else None,
        "lineage_id": str(r.lineage_id),
        "card_type": r.card_type,
        "metric_name": r.metric_name,
        "provider": r.provider,
        "event_type": r.event_type,
        "dimensions": r.dimensions,
        "pricing_model": r.pricing_model,
        "rate_per_unit_micros": r.rate_per_unit_micros,
        "unit_quantity": r.unit_quantity,
        "fixed_micros": r.fixed_micros,
        "currency": r.currency,
        "product_id": r.product_id,
        "valid_from": r.valid_from.isoformat(),
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
    }


def _gate_card_type(request, card_type):
    _product_check(request)
    if card_type == "price":
        _billing_check(request)


def _resolve_card_currency(tenant, raw_currency):
    """CUR-1 rate-card currency pin: cards live in the tenant's currency.

    Omitted/empty currency defaults to the tenant's default_currency; an
    explicit value must match it case-insensitively. Returns the normalized
    lowercase currency, or raises ValueError (mapped to 422 by callers).
    """
    tenant_currency = (tenant.default_currency or "usd").lower()
    if not raw_currency:
        return tenant_currency
    card_currency = str(raw_currency).strip().lower()
    if card_currency != tenant_currency:
        raise ValueError(
            f"rate-card currency {card_currency!r} does not match tenant "
            f"currency {tenant_currency!r} (per-tenant single currency; "
            "multi-currency/FX is not supported)")
    return card_currency


@metering_api.get("/pricing/rate-cards", response=list[BookOut])
def list_books(request, card_type: str = None):
    """List the tenant's rate-card BOOKS (containers). Rates live under a book
    and are read via GET /pricing/rate-cards/{book_id}/rates."""
    _product_check(request)
    qs = RateCard.objects.filter(tenant=request.auth.tenant)
    if card_type:
        qs = qs.filter(card_type=card_type)
    return [_book_to_out(b) for b in qs.order_by(
        "card_type", "provider_key", "key", "id")]


@metering_api.post("/pricing/rate-cards", response={200: BookOut, 422: dict})
def create_book(request, payload: BookIn):
    """Create a rate-card BOOK. Rates are added under it (so every API-created
    rate is book-scoped and therefore resolvable)."""
    _gate_card_type(request, payload.card_type)
    valid_types = {c[0] for c in CARD_TYPE_CHOICES}
    if payload.card_type not in valid_types:
        return 422, {"error": f"card_type must be one of {sorted(valid_types)}"}
    try:
        currency = _resolve_card_currency(request.auth.tenant, payload.currency)
    except ValueError as e:
        return 422, {"error": str(e)}
    try:
        book = RateCard.objects.create(
            tenant=request.auth.tenant, card_type=payload.card_type,
            provider_key=payload.provider_key, key=payload.key, name=payload.name,
            currency=currency, is_default=payload.is_default)
    except IntegrityError as e:
        return 422, {"error": f"rate-card book conflict: {e}"}
    return 200, _book_to_out(book)


@metering_api.get("/pricing/rate-cards/{book_id}/rates", response={200: list[RateOut], 404: dict})
def list_book_rates(request, book_id: UUID, include_history: bool = False,
                    as_of: datetime = None):
    """List the rates in a book. Active-only by default; ``include_history``
    returns every version (superseded rows carry a ``valid_to``), and ``as_of``
    returns the version active at that instant (point-in-time)."""
    _product_check(request)
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    qs = Rate.objects.filter(tenant=request.auth.tenant, rate_card=book)
    if as_of is not None:
        qs = qs.filter(valid_from__lte=as_of).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
    elif not include_history:
        qs = qs.filter(valid_to__isnull=True)
    return 200, [_rate_to_out(r) for r in qs.order_by(
        "provider", "event_type", "metric_name", "-valid_from", "id")]


@metering_api.post("/pricing/rate-cards/{book_id}/rates", response={200: RateOut, 422: dict})
def add_rate(request, book_id: UUID, payload: RateIn):
    """Add a rate to a book. card_type and currency are inherited from the book
    (single source of truth); tier/enum validation mirrors the old flat create."""
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    if book.is_default and payload.provider != book.provider_key:
        return 422, {"error": (f"rate provider {payload.provider!r} must match the "
                               f"default book's provider {book.provider_key!r}")}
    valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
    if payload.pricing_model not in valid_models:
        return 422, {"error": f"pricing_model must be one of {sorted(valid_models)}"}
    try:
        rate = Rate.objects.create(
            tenant=request.auth.tenant, rate_card=book, card_type=book.card_type,
            metric_name=payload.metric_name, provider=payload.provider,
            event_type=payload.event_type, dimensions=payload.dimensions,
            pricing_model=payload.pricing_model,
            rate_per_unit_micros=payload.rate_per_unit_micros,
            unit_quantity=payload.unit_quantity, fixed_micros=payload.fixed_micros,
            currency=book.currency, product_id=payload.product_id,
            book_version_from=book.version)
    except IntegrityError as e:
        return 422, {"error": f"rate conflict: {e}"}
    return 200, _rate_to_out(rate)


@metering_api.post("/pricing/rate-cards/{book_id}/publish", response={200: BookOut, 422: dict})
def publish_book(request, book_id: UUID, payload: PublishIn):
    """Atomically reprice a set of the book's rates: each change supersedes the
    matching active rate (same lineage, valid_to stamped) and opens a new
    version; the book version bumps once. All-or-nothing."""
    from apps.metering.pricing.services.book_service import BookService

    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    try:
        BookService.publish(book, [c.dict(exclude_none=True) for c in payload.changes])
    except ValueError as e:
        return 422, {"error": str(e)}
    book.refresh_from_db()
    return 200, _book_to_out(book)


@metering_api.post("/pricing/customers/{customer_id}/rate-card", response={200: dict, 422: dict})
def assign_book(request, customer_id: UUID, payload: AssignIn):
    """Assign a PRICE book to a customer (one per customer per currency).
    Resolution consults the assigned book before the per-provider default."""
    _billing_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    book = get_object_or_404(RateCard, id=payload.rate_card_id,
                             tenant=request.auth.tenant, card_type="price")
    RateCardAssignment.objects.update_or_create(
        tenant=request.auth.tenant, customer=customer, currency=book.currency,
        defaults={"rate_card": book})
    return 200, {"assigned": str(book.id)}


@metering_api.delete("/pricing/rate-cards/{card_id}")
def delete_rate_card(request, card_id: UUID):
    _product_check(request)
    card = get_object_or_404(Rate, id=card_id, tenant=request.auth.tenant, valid_to__isnull=True)
    card.valid_to = timezone.now()
    card.save(update_fields=["valid_to", "updated_at"])
    return {"status": "deleted"}
