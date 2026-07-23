import logging
import re
from datetime import date, datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Sum, Count, Q
from django.db.models.fields.json import KeyTextTransform
from django.shortcuts import get_object_or_404
from ninja import Query, Router

from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, WRITE, role_floor
from core.identifiers import UUIDIdentifier
from core.problems import Problem, ProblemOut
from core.responses import StatusResponse
from core.time_windows import (
    REPORT_WINDOW_MAX_DAYS, utc_day_start, utc_next_day_start)
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
    PaginatedBooks, PaginatedRates,
)
from apps.metering.pricing.models import (
    Rate, RateCard, RateCardAssignment,
    CARD_TYPE_CHOICES, PRICING_MODEL_CHOICES,
)
from api.v1.pagination import paginate
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.metering.pricing.services.pricing_service import PricingError
from apps.metering.usage.services.ingest_accept import (
    IngestAppendFailed, accept_batch, record_sync_item, usage_error,
    usage_kwargs, with_uncosted)
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent

logger = logging.getLogger(__name__)

metering_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("metering")


@metering_router.post("/usage", response={200: RecordUsageResponse})
@role_floor(WRITE)
def record_usage(request, payload: RecordUsageRequest):
    """Record one usage event. One-rule contract: every event that reaches
    UBB is priced, recorded, and billed with an HTTP 200 — including the
    tipping event that crosses a limit and everything arriving after a kill.
    The stop instruction rides the response fields (stop / stop_reason /
    stop_scope); a non-200 always means "this was not recorded" (auth,
    malformed payload, unknown customer/task, pricing/validation errors)."""
    _product_check(request)

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    if payload.task_id is not None:
        get_object_or_404(Task, id=payload.task_id, tenant=request.auth.tenant, customer=customer)
    try:
        result = UsageService.record_usage(
            tenant=request.auth.tenant, customer=customer,
            **usage_kwargs(payload))
    except (PricingError, ValueError) as e:
        code, detail = usage_error(e)
        raise Problem(code, detail)
    # Kill execution is the recording core's job (#112): a crossing verdict
    # registers kill_and_announce on the recording transaction's on_commit,
    # so the kills have already fired by the time this returns.
    return with_uncosted(result)


@metering_router.post("/usage/batch", response={200: UsageBatchResponse})
@role_floor(WRITE)
def record_usage_batch(request, payload: UsageBatchRequest):
    """Batch ingestion: 1..100 INDEPENDENT items (>100 or 0 → 422).

    Each item runs the same per-item record_usage in its own atomic commit —
    deliberately NOT one mega-transaction, which would hold Task/counter locks
    for the whole batch, delay outbox dispatch, and diverge from the semantics
    of N sequential singles. Always HTTP 200 with positionally-aligned
    results[] + accepted/rejected counts; per-item idempotency makes a
    whole-batch replay return the original event ids with zero new rows, and
    a duplicate idempotency_key WITHIN one batch resolves to the first item's
    event id (the first item commits before the second runs).
    """
    _product_check(request)
    tenant = request.auth.tenant
    customers: dict = {}
    task_exists: dict = {}
    results = [record_sync_item(tenant, item, customers, task_exists)
               for item in payload.events]
    accepted = sum(1 for r in results if r.get("accepted"))
    return {"results": results, "accepted": accepted,
            "rejected": len(results) - accepted}


# --- Async ingest (estimate -> atomic hold -> durable append) ---

@metering_router.post("/usage/ingest", response={200: IngestBatchResponse})
@role_floor(WRITE)
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
        raise Problem("feature_not_enabled",
                      "metering_async is not enabled for this tenant")
    try:
        results = accept_batch(tenant, payload.events)
    except IngestAppendFailed:
        raise Problem("service_unavailable", "raw ingest append failed")
    accepted = sum(1 for r in results if r["accepted"])
    return {"results": results, "accepted": accepted,
            "rejected": len(results) - accepted}


@metering_router.get("/ops/ingest-health", auth=None, include_in_schema=False)
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
        raise Problem("unauthorized")
    # Manual parse, AFTER both token gates: keeping the param typed as `str`
    # (not `UUID`) means ninja never 422s a malformed tenant_id before the
    # token check runs — that would let an unauthenticated caller distinguish
    # "wrong shape" from "not found" and re-open the fingerprinting hole.
    parsed_tenant_id = None
    if tenant_id:
        try:
            parsed_tenant_id = UUID(tenant_id)
        except ValueError:
            raise Problem("invalid_tenant_id", "tenant_id must be a UUID")
    from apps.metering.usage.services.ingest_health import ingest_health
    from apps.billing.queries import get_negative_balance_stats, get_patrol_stats
    # #41 pin 10 / #44 §F: the aged-negatives and patrol-outcome metrics ride
    # the existing ops surface — composed HERE (the api layer may import both
    # products; the metering service must not reach into billing).
    return {**ingest_health(tenant_id=parsed_tenant_id),
            **get_negative_balance_stats(tenant_id=parsed_tenant_id),
            **get_patrol_stats(tenant_id=parsed_tenant_id)}


def _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq):
    """The #41 past-limit query filters, shared by the events listing and the
    analytics rollup so both surfaces compose identically:

    - past_limit=true  → only events carrying a stop context (landed past
      something); false → only untagged events.
    - stop_scope=X     → events with at least one context entry of scope X.
    - episode_seq=N    → events tagged into customer-wide episode N.

    The array-containment filters ride the partial GIN index on
    UsageEvent.stop_context (JSONB @>)."""
    if past_limit is not None:
        qs = qs.filter(stop_context__isnull=not past_limit)
    if stop_scope is not None:
        qs = qs.filter(stop_context__contains=[{"stop_scope": stop_scope}])
    if episode_seq is not None:
        qs = qs.filter(stop_context__contains=[{"episode_seq": episode_seq}])
    return qs


@metering_router.get("/customers/{customer_id}/usage", response=PaginatedUsageResponse)
@role_floor(READ)
def get_usage(request, customer_id: UUIDIdentifier, cursor: str = None, limit: int = 50,
              tag_key: str = None, tag_value: str = None,
              past_limit: bool = None, stop_scope: str = None,
              episode_seq: int = None):
    _product_check(request)

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)

    qs = customer.usage_events.all()
    if tag_key and tag_value:
        qs = qs.filter(tags__contains={tag_key: tag_value})
    qs = _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq)

    events, next_cursor, has_more = paginate(
        qs, cursor, limit, time_field="effective_at")

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
                "stop_context": e.stop_context,
            }
            for e in events
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@metering_router.get("/usage/{event_id}", response={200: UsageEventDetailOut, 404: ProblemOut})
@role_floor(READ)
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
        "stop_context": e.stop_context,
    }


# --- Task lifecycle ---


@metering_router.post("/tasks/{task_id}/close", response=CloseTaskResponse)
@role_floor(WRITE)
def close_task(request, task_id: UUID):
    """Close (complete) a task or subtask. Closing a PARENT auto-completes
    its active subtasks in the same transaction (#38) — cleanup is one call;
    a killed subtask keeps its state. Closing a subtask completes it alone."""
    _product_check(request)
    from django.db import transaction
    from apps.platform.tasks.services import TaskService

    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    with transaction.atomic():
        completed, _ = TaskService.complete_task(task.id)
    return {
        "task_id": str(completed.id),
        "parent_task_id": str(completed.parent_id) if completed.parent_id else None,
        "status": completed.status,
        "total_billed_cost_micros": completed.total_billed_cost_micros,
        "total_provider_cost_micros": completed.total_provider_cost_micros,
        "event_count": completed.event_count,
    }


# --- Pricing Markup ---


@metering_router.get("/pricing/markup", response=TenantMarkupOut)
@role_floor(READ)
def get_tenant_markup(request):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markup = TenantMarkup.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if markup is None:
        return {"markup_percentage_micros": 0, "fixed_uplift_micros": 0}
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_router.put("/pricing/markup", response=TenantMarkupOut)
@role_floor(ADMIN)
@records_audit("markup.set")
def upsert_tenant_markup(request, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    with transaction.atomic():
        markup, _ = TenantMarkup.objects.update_or_create(
            tenant=request.auth.tenant,
            customer=None,
            defaults={
                "markup_percentage_micros": payload.markup_percentage_micros,
                "fixed_uplift_micros": payload.fixed_uplift_micros,
            },
        )
        audit_record(
            action="markup.set",
            tenant_id=request.auth.tenant.id,
            resource_type="markup",
            resource_id=markup.id,
            metadata={
                "scope": "tenant",
                "markup_percentage_micros": markup.markup_percentage_micros,
                "fixed_uplift_micros": markup.fixed_uplift_micros,
            },
        )
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_router.get("/pricing/customers/{customer_id}/markup", response=TenantMarkupOut)
@role_floor(READ)
def get_customer_markup(request, customer_id: UUID):
    _product_check(request)
    from apps.metering.pricing.services.markup_service import MarkupService

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    markup = MarkupService.resolve(tenant=request.auth.tenant, customer=customer)
    if markup is None:
        return {"markup_percentage_micros": 0, "fixed_uplift_micros": 0}
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_router.put("/pricing/customers/{customer_id}/markup", response=TenantMarkupOut)
@role_floor(ADMIN)
@records_audit("markup.set")
def upsert_customer_markup(request, customer_id: UUID, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    with transaction.atomic():
        markup, _ = TenantMarkup.objects.update_or_create(
            tenant=request.auth.tenant,
            customer=customer,
            defaults={
                "markup_percentage_micros": payload.markup_percentage_micros,
                "fixed_uplift_micros": payload.fixed_uplift_micros,
            },
        )
        audit_record(
            action="markup.set",
            tenant_id=request.auth.tenant.id,
            resource_type="markup",
            resource_id=markup.id,
            metadata={
                "scope": "customer",
                "customer_id": str(customer.id),
                "markup_percentage_micros": markup.markup_percentage_micros,
                "fixed_uplift_micros": markup.fixed_uplift_micros,
            },
        )
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_router.delete("/pricing/customers/{customer_id}/markup",
                        response=StatusResponse)
@role_floor(ADMIN)
@records_audit("markup.deleted")
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
    with transaction.atomic():
        markup.delete()  # instance delete — the model layer bumps MarkupCache's version
        audit_record(
            action="markup.deleted",
            tenant_id=request.auth.tenant.id,
            resource_type="markup",
            resource_id=customer.id,
            metadata={"scope": "customer", "customer_id": str(customer.id)},
        )
    return {"status": "deleted"}


# --- Analytics ---


_ANALYTICS_ALLOWED_COLS = {"provider", "event_type", "product_id", "customer", "service_id", "agent_id"}


@metering_router.get("/analytics/usage", response={200: UsageAnalyticsResponse, 422: ProblemOut})
@role_floor(READ)
def usage_analytics(request, start_date: date = None, end_date: date = None,
                    customer_id: UUIDIdentifier = None, tag_key: str = None,
                    dimensions: list[str] = Query(None),
                    past_limit: bool = None, stop_scope: str = None,
                    episode_seq: int = None):
    """Usage analytics with markup margin and customer/product/tag breakdowns.

    The #41 past-limit filters (past_limit / stop_scope / episode_seq)
    compose with every breakdown — e.g. past_limit=true totals exactly what
    was spent past a stop, in both denominations."""
    _product_check(request)
    tenant = request.auth.tenant
    # #78: computed reports are cursor-exempt but parameter-bounded.
    if start_date and end_date:
        if end_date < start_date:
            raise Problem("validation_error", "end_date must not precede start_date")
        if (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "date window must not exceed 366 days")
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    qs = _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq)

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
            raise Problem("validation_error", "at most 6 dimensions")
        for dim in dimensions:
            if dim.startswith("tag:"):
                key = dim[4:]
                if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key):
                    raise Problem("validation_error", f"invalid tag dimension {dim}")
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
                raise Problem("validation_error", f"unknown dimension {dim}")
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


@metering_router.get("/analytics/usage/timeseries", response={200: UsageTimeseriesResponse, 422: ProblemOut})
@role_floor(READ)
def usage_timeseries(request, granularity: str = "day", start_date: date = None, end_date: date = None,
                     customer_id: UUIDIdentifier = None, group_by: str = None):
    """Time-series spend rollup: daily or hourly COGS per tenant/customer.

    start_date and end_date are both INCLUSIVE calendar dates, matching the
    /analytics/usage rollup so the same inputs cover the same window on both.
    """
    _product_check(request)
    if granularity not in ("hour", "day"):
        raise Problem("validation_error", "granularity must be hour or day")
    if group_by is not None and group_by not in ("provider", "event_type", "product_id", "service_id", "agent_id"):
        raise Problem("validation_error", "invalid group_by")
    # #78 bounds: hourly windows capped at ~92 days, daily at 366.
    if start_date and end_date:
        if end_date < start_date:
            raise Problem("validation_error", "end_date must not precede start_date")
        if granularity == "hour" and (end_date - start_date).days > 92:
            raise Problem("validation_error", "hourly window too large (max 92 days)")
        if granularity == "day" and (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "date window must not exceed 366 days")
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


@metering_router.get("/pricing/rate-cards", response=PaginatedBooks)
@role_floor(READ)
def list_books(request, card_type: str = None, cursor: str = None, limit: int = 50):
    """List the tenant's rate-card BOOKS (containers), newest first. Rates
    live under a book and are read via GET /pricing/rate-cards/{book_id}/rates."""
    _product_check(request)
    qs = RateCard.objects.filter(tenant=request.auth.tenant)
    if card_type:
        qs = qs.filter(card_type=card_type)
    books, next_cursor, has_more = paginate(qs, cursor, limit)
    return {"data": [_book_to_out(b) for b in books],
            "next_cursor": next_cursor, "has_more": has_more}


@metering_router.post("/pricing/rate-cards",
                      response={200: BookOut, 409: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate_card.created")
def create_book(request, payload: BookIn):
    """Create a rate-card BOOK. Rates are added under it (so every API-created
    rate is book-scoped and therefore resolvable). Creates dedupe on natural
    identity (#78): a duplicate book answers 409."""
    _gate_card_type(request, payload.card_type)
    valid_types = {c[0] for c in CARD_TYPE_CHOICES}
    if payload.card_type not in valid_types:
        raise Problem("validation_error",
                      f"card_type must be one of {sorted(valid_types)}")
    try:
        currency = _resolve_card_currency(request.auth.tenant, payload.currency)
    except ValueError as e:
        raise Problem("validation_error", str(e))
    try:
        with transaction.atomic():
            book = RateCard.objects.create(
                tenant=request.auth.tenant, card_type=payload.card_type,
                provider_key=payload.provider_key, key=payload.key, name=payload.name,
                currency=currency, is_default=payload.is_default)
            audit_record(
                action="rate_card.created",
                tenant_id=request.auth.tenant.id,
                resource_type="rate_card",
                resource_id=book.id,
                metadata={
                    "card_type": book.card_type,
                    "provider_key": book.provider_key,
                    "key": book.key,
                    "name": book.name,
                    "currency": book.currency,
                    "is_default": book.is_default,
                },
            )
    except IntegrityError:
        raise Problem("conflict", "a rate-card book with this identity already exists")
    return 200, _book_to_out(book)


@metering_router.get("/pricing/rate-cards/{book_id}/rates",
                     response={200: PaginatedRates, 404: ProblemOut})
@role_floor(READ)
def list_book_rates(request, book_id: UUID, include_history: bool = False,
                    as_of: datetime = None, cursor: str = None, limit: int = 50):
    """List the rates in a book, newest first. Active-only by default;
    ``include_history`` returns every version (superseded rows carry a
    ``valid_to``), and ``as_of`` returns the version active at that instant
    (point-in-time)."""
    _product_check(request)
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    qs = Rate.objects.filter(tenant=request.auth.tenant, rate_card=book)
    if as_of is not None:
        qs = qs.filter(valid_from__lte=as_of).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
    elif not include_history:
        qs = qs.filter(valid_to__isnull=True)
    rates, next_cursor, has_more = paginate(qs, cursor, limit)
    return 200, {"data": [_rate_to_out(r) for r in rates],
                 "next_cursor": next_cursor, "has_more": has_more}


@metering_router.post("/pricing/rate-cards/{book_id}/rates",
                      response={200: RateOut, 404: ProblemOut,
                                409: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate.added")
def add_rate(request, book_id: UUID, payload: RateIn):
    """Add a rate to a book. card_type and currency are inherited from the book
    (single source of truth); tier/enum validation mirrors the old flat create.
    Creates dedupe on natural identity (#78): a duplicate rate answers 409."""
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    if book.is_default and payload.provider != book.provider_key:
        raise Problem("validation_error",
                      f"rate provider {payload.provider!r} must match the "
                      f"default book's provider {book.provider_key!r}")
    valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
    if payload.pricing_model not in valid_models:
        raise Problem("validation_error",
                      f"pricing_model must be one of {sorted(valid_models)}")
    try:
        with transaction.atomic():
            rate = Rate.objects.create(
                tenant=request.auth.tenant, rate_card=book, card_type=book.card_type,
                metric_name=payload.metric_name, provider=payload.provider,
                event_type=payload.event_type, dimensions=payload.dimensions,
                pricing_model=payload.pricing_model,
                rate_per_unit_micros=payload.rate_per_unit_micros,
                unit_quantity=payload.unit_quantity, fixed_micros=payload.fixed_micros,
                currency=book.currency, product_id=payload.product_id,
                book_version_from=book.version)
            audit_record(
                action="rate.added",
                tenant_id=request.auth.tenant.id,
                resource_type="rate",
                resource_id=rate.id,
                metadata={
                    "book_id": str(book.id),
                    "metric_name": rate.metric_name,
                    "pricing_model": rate.pricing_model,
                    "rate_per_unit_micros": rate.rate_per_unit_micros,
                    "currency": rate.currency,
                },
            )
    except IntegrityError:
        raise Problem("conflict", "a rate with this identity already exists")
    return 200, _rate_to_out(rate)


@metering_router.post("/pricing/rate-cards/{book_id}/publish",
                      response={200: BookOut, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate_card.published")
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
        raise Problem("validation_error", str(e))
    book.refresh_from_db()
    audit_record(
        action="rate_card.published",
        tenant_id=request.auth.tenant.id,
        resource_type="rate_card",
        resource_id=book.id,
        metadata={"version": book.version,
                  "change_count": len(payload.changes)},
    )
    return 200, _book_to_out(book)


@metering_router.post("/pricing/customers/{customer_id}/rate-card", response={200: dict, 404: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate_card.assigned")
def assign_book(request, customer_id: UUID, payload: AssignIn):
    """Assign a PRICE book to a customer (one per customer per currency).
    Resolution consults the assigned book before the per-provider default."""
    _billing_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    book = get_object_or_404(RateCard, id=payload.rate_card_id,
                             tenant=request.auth.tenant, card_type="price")
    with transaction.atomic():
        RateCardAssignment.objects.update_or_create(
            tenant=request.auth.tenant, customer=customer, currency=book.currency,
            defaults={"rate_card": book})
        audit_record(
            action="rate_card.assigned",
            tenant_id=request.auth.tenant.id,
            resource_type="rate_card",
            resource_id=book.id,
            metadata={"customer_id": str(customer.id),
                      "rate_card_id": str(book.id),
                      "currency": book.currency},
        )
    return 200, {"assigned": str(book.id)}


@metering_router.delete("/pricing/rate-cards/{book_id}/rates/{rate_id}",
                        response=StatusResponse)
@role_floor(ADMIN)
@records_audit("rate.deleted")
def delete_rate(request, book_id: UUID, rate_id: UUID):
    """Retire (soft-expire) a single rate within its book. Addressed under its
    book — matching GET/POST /pricing/rate-cards/{book_id}/rates — so the path
    noun (``rates``) agrees with the identifier it takes (#86 sweep: this route
    previously took a rate id on a bare ``/pricing/rate-cards/{card_id}`` path)."""
    _product_check(request)
    rate = get_object_or_404(Rate, id=rate_id, rate_card_id=book_id,
                             tenant=request.auth.tenant, valid_to__isnull=True)
    with transaction.atomic():
        rate.valid_to = timezone.now()
        rate.save(update_fields=["valid_to", "updated_at"])
        audit_record(
            action="rate.deleted",
            tenant_id=request.auth.tenant.id,
            resource_type="rate",
            resource_id=rate.id,
            metadata={"book_id": str(book_id),
                      "rate_id": str(rate.id),
                      "valid_to": rate.valid_to.isoformat()},
        )
    return {"status": "deleted"}
