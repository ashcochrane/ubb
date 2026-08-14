import logging
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
    PaginatedUsageResponse,
    UsageEventDetailOut,
    TenantMarkupIn, TenantMarkupOut,
    CloseTaskResponse,
    TaskDetailOut, PaginatedTasks, task_out,
    UsageAnalyticsResponse,
    UsageTimeseriesResponse,
    TaskAnalyticsOut,
    RateIn, RateOut, BookIn, BookOut, RateChangeIn, PublishIn, AssignIn,
    PaginatedBooks, PaginatedRates,
    book_out, rate_change_body, rate_out, usage_event_out,
    SLOT_PROPERTY_COLUMNS,
    DimensionRegistryIn, DimensionRegistryOut, GroupingFieldValuesOut,
    TaskTypeRegistryIn, TaskTypeRegistryOut,
)
from apps.metering.pricing.models import (
    Rate, RateCard, RateCardAssignment,
    CARD_TYPE_CHOICES, PRICING_MODEL_CHOICES,
)
from api.v1.pagination import page
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.metering.queries import GROUPED_VALUE_KEY
from apps.metering.usage.services.usage_service import (
    EffectiveAtError, UsageService)
from apps.metering.usage.models import Posting
from apps.platform.grouping_fields.models import SLOT_CHOICES
from apps.platform.grouping_fields.services import DimensionError, DimensionService

logger = logging.getLogger(__name__)

metering_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("metering")


# --- The request-item adapters over UsageService.record_usage ---------------
#
# These moved here when the async accept pipeline was deleted. They were
# lifted out of this module by #113 to be SHARED between the endpoints and
# that pipeline; with the pipeline gone the two recording routes below are
# their only callers, so the seam that justified a separate module no longer
# has two sides. Written once, here, rather than twice: the single route and
# the batch route must map fields and classify errors identically or the
# batch stops being "N sequential singles".


def usage_kwargs(item):
    """The single↔batch pass-through, written ONCE (#112): the field-for-
    field map from a request item (RecordUsageRequest — the single and batch
    items share the schema) onto record_usage's keyword surface."""
    return dict(
        request_id=item.request_id,
        idempotency_key=item.idempotency_key,
        provider_cost_micros=item.provider_cost_micros,
        billed_cost_micros=item.billed_cost_micros,
        currency=item.currency,
        metadata=item.metadata,
        event_type=item.event_type,
        provider=item.provider,
        task_id=item.task_id,
        measurements=item.measurements,
        effective_at=item.effective_at,
    )


def usage_error(e):
    """The ONE record_usage error map (#112): exception → (code, detail).
    The specific-before-general order lives HERE and only here —
    EffectiveAtError (which IS a ValueError, so it must be tested before the
    generic branch), then plain ValueError. The single endpoint raises the code
    as a Problem; the batch wraps the same code in a verdict dict.

    **A COST UBB CANNOT WORK OUT IS NO LONGER AN ERROR (#320)**, so the branch
    that was first here is gone along with the exception it named and the wire
    code it produced. The supplier has already run the call and already charged
    for it; the event is recorded with its cost said to be unresolved, and the
    caller learns that from the 200 body rather than from a 422 that throws the
    charge away."""
    if isinstance(e, EffectiveAtError):
        return e.code, str(e)
    return "validation_error", str(e)


def with_uncosted(result):
    """Surface the provenance receipt's uncosted-quantity list on a success
    body — both recording surfaces return it.

    The list says WHICH declared quantities went uncosted; `costing_status` on
    the same body says THAT the cost is unresolved. Neither is the other: a
    tenant fixing this needs the specific declaration, and a reader totalling a
    column needs the status."""
    provenance = result.get("pricing_provenance") or {}
    result["uncosted_measurement_keys"] = provenance.get(
        "uncosted_measurement_keys", [])
    return result


def _rejected(code, detail):
    """A batch-item rejection verdict: the typed code plus the constant stop
    trio — a rejected item was never recorded, so nothing can have stopped."""
    return {"accepted": False, "code": code, "detail": detail,
            "stop": False, "stop_reason": None, "stop_scope": None}


def record_sync_item(tenant, item, customers, task_exists):
    """One batch item == one independent POST /usage, error mapping included.

    Mirrors the single endpoint's contract byte-for-byte as per-item VERDICT
    dicts: a success mirrors the single-call success body (stop-verdict
    fields included) plus {"accepted": true}. 404s become per-item
    {"code": "not_found"}; the generic ValueError branch becomes
    {"code": "validation_error"} - every code from the registry. One-rule
    parity: a crossing verdict runs the same kill flow and the batch
    CONTINUES — later items on the killed task still land, bill, and carry
    the task_not_active stop verdict, identical to firing the same items as
    sequential singles.
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
    # Task 9: admission is a WRITE, run BEFORE the recording core — a bad
    # grouping field is THIS item's rejection, same as any other validation
    # failure below, and never reaches record_usage.
    try:
        dimension_slots = DimensionService.admit(tenant, item.dimensions, scope="event")
    except DimensionError as exc:
        return _rejected("validation_error", str(exc))
    try:
        result = UsageService.record_usage(
            tenant=tenant, customer=customer, dimension_slots=dimension_slots,
            **usage_kwargs(item))
    except ValueError as e:
        return _rejected(*usage_error(e))
    return {"accepted": True, **with_uncosted(result)}


@metering_router.post("/usage", response={200: RecordUsageResponse})
@role_floor(WRITE)
def record_usage(request, payload: RecordUsageRequest):
    """Record one usage event. One-rule contract: every event that reaches
    UBB is priced, recorded, and billed with an HTTP 200 — including the
    tipping event that crosses a limit and everything arriving after a kill.
    The stop instruction rides the response fields (stop / stop_reason /
    stop_scope); a non-200 always means "this was not recorded" (auth,
    malformed payload, unknown customer/task, validation errors).

    A cost UBB cannot work out is NOT one of those (#320): the event is
    recorded, and `costing_status` plus `uncosted_measurement_keys` on this
    body say so at the moment the gap is created."""
    _product_check(request)

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    if payload.task_id is not None:
        get_object_or_404(Task, id=payload.task_id, tenant=request.auth.tenant, customer=customer)
    # Task 9: admission is a WRITE (records GroupingFieldValue rows), so it runs
    # BEFORE the recording core, outside record_usage's own retry/replay
    # machinery — a bad grouping field is a whole-request 422, never a partial
    # record.
    try:
        dimension_slots = DimensionService.admit(
            request.auth.tenant, payload.dimensions, scope="event")
    except DimensionError as exc:
        raise Problem("validation_error", str(exc))
    try:
        result = UsageService.record_usage(
            tenant=request.auth.tenant, customer=customer,
            dimension_slots=dimension_slots,
            **usage_kwargs(payload))
    except ValueError as e:
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


def _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq):
    """The #41 past-limit query filters, shared by the events listing and the
    analytics rollup so both surfaces compose identically:

    - past_limit=true  → only events carrying a stop context (landed past
      something); false → only untagged events.
    - stop_scope=X     → events with at least one context entry of scope X.
    - episode_seq=N    → events tagged into customer-wide episode N.

    The array-containment filters ride the partial GIN index on
    Posting.stop_context (JSONB @>)."""
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
              task_id: UUIDIdentifier = None, include_subtasks: bool = False,
              past_limit: bool = None, stop_scope: str = None,
              episode_seq: int = None):
    _product_check(request)

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)

    qs = customer.postings.all()
    # FILTERING is what the open bag is for, and it is what survived the fold
    # in #273 — the parameter names are the analytics vocabulary slice 7 owns
    # and are deliberately left spelled as they are published.
    if tag_key and tag_value:
        qs = qs.filter(metadata__contains={tag_key: tag_value})
    qs = _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq)
    qs = _apply_task_filter(qs, request.auth.tenant, task_id, include_subtasks)

    return page(qs, cursor, limit, serialize=usage_event_out,
                time_field="effective_at")


@metering_router.get("/usage/{event_id}", response={200: UsageEventDetailOut, 404: ProblemOut})
@role_floor(READ)
def get_usage_event(request, event_id: UUID):
    """Fetch one usage event's full pricing receipt (audit / dispute lookup).

    Returns every priced field plus pricing_provenance — the recorded
    "why this amount" (engine version, price source, the card that priced each
    named quantity, and tier-by-tier breakdown). The usage list omits
    provenance to stay lean;
    this is where it is read back. Tenant-scoped; 404 for an unknown or
    foreign event id."""
    _product_check(request)
    from apps.metering.usage.grouping import grouping_fields_for
    from apps.metering.usage.measurements import measurements_status_for
    from apps.metering.usage.models import Posting

    # select_related on the measurement child (#270): the response reads the
    # measured quantities through it, and the detail route is a single-row
    # lookup where a second query buys nothing. #271's status reads the same
    # cached relation, so serving it costs no query either.
    e = get_object_or_404(
        Posting.objects.select_related("measurement"),
        id=event_id, tenant=request.auth.tenant)
    return 200, {
        "id": e.id,
        "request_id": e.request_id,
        "idempotency_key": e.idempotency_key,
        "event_type": e.event_type,
        "provider": e.provider,
        # Derived at the serialiser like the status below, and for the same
        # reason (#277): the row carries physical slots, and what a caller reads
        # is the tenant's own vocabulary. One registry read, and none at all for
        # a posting with no grouping values.
        "grouping_fields": grouping_fields_for(e),
        "currency": e.currency,
        "provider_cost_micros": e.provider_cost_micros,
        # Stored, unlike the two derived answers around it: the status is a
        # statement about this posting's economics and a column holds it.
        "costing_status": e.costing_status,
        "billed_cost_micros": e.billed_cost_micros,
        "measurements": e.measurements or {},
        # Derived, never stored (ADR-0006 §4) — computed here, at the
        # serialiser, which is the only place §E5 permits it to exist.
        "measurements_status": measurements_status_for(e),
        "pricing_provenance": e.pricing_provenance or {},
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
    from apps.platform.work.services import TaskService

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


@metering_router.get("/tasks", response=PaginatedTasks)
@role_floor(READ)
def list_tasks(request, cursor: str = None, limit: int = 50,
               customer_id: UUIDIdentifier = None, task_type: str = None,
               status: str = None):
    """Top-level units of work with their materialized cost rollups.

    Subtasks are omitted — they belong to their parent's detail view, so a
    listing counts JOBS, not steps."""
    _product_check(request)

    qs = Task.objects.filter(tenant=request.auth.tenant, parent__isnull=True)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if task_type:
        qs = qs.filter(task_type=task_type)
    if status:
        qs = qs.filter(status=status)
    return page(qs, cursor, limit, serialize=task_out, time_field="created_at")


@metering_router.get("/tasks/{task_id}", response={200: TaskDetailOut, 404: ProblemOut})
@role_floor(READ)
def get_task(request, task_id: UUID):
    """One unit's cost receipt plus its subtask tree.

    Reads the rollups `TaskService.accumulate_cost` maintains — including
    events that landed after a kill — so this never aggregates
    ubb_posting. One indexed row read plus its children."""
    _product_check(request)

    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    body = task_out(task)
    body["subtasks"] = [task_out(s) for s in
                        task.subtasks.all().order_by("created_at")]
    return 200, body


@metering_router.get("/analytics/tasks", response={200: TaskAnalyticsOut,
                                                  422: ProblemOut})
@role_floor(READ)
def task_analytics(request, group_by: str = "task_type", start_date: date = None,
                   end_date: date = None):
    """Cost per KIND of job: run count, mean, p95, and limit hits.

    A p95 approaching the type's ceiling is the signal that the limit is about
    to start biting real customers."""
    _product_check(request)
    from apps.platform.work.queries import task_rollup_by_type

    if start_date and end_date:
        if end_date < start_date:
            raise Problem("validation_error",
                          "end_date must not precede start_date")
        if (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "date window must not exceed 366 days")
    try:
        rows = task_rollup_by_type(
            request.auth.tenant.id, group_by=group_by,
            start_date=utc_day_start(start_date) if start_date else None,
            end_date=utc_next_day_start(end_date) if end_date else None)
    except ValueError as exc:
        raise Problem("validation_error", str(exc))
    return 200, {"group_by": group_by, "rows": rows}


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


# The four reserved dimensions (design D1) plus "customer", which is a column
# on the event rather than a slot. Tenant keys come from the registry.
_RESERVED_ANALYTICS_DIMS = ("provider", "event_type", "task_type", "subtask_type",
                            "customer")

#: How many breakdowns one analytics call may ask for. The tenant slot count,
#: read off the registry rather than restated — six was the slot count too, and
#: #276 made a hard-coded six disagree with it.
#:
#: NOT "one per requestable axis": the four reserved axes plus `customer` are
#: also requestable, so fifteen names can be asked for and ten of them can be
#: served in one call. The cap is a bound on work per request, and the slot
#: count is what it has always been pinned to.
_MAX_BREAKDOWNS = len(SLOT_CHOICES)


def _resolve_dimension(tenant, dim):
    """Map a requested grouping axis to the column to GROUP BY.

    Reserved names map to themselves; declared tenant keys map to their slot.
    Anything else — notably a correlation id like task_id (design D9) — is a
    422, so an unbounded key can never become a group-by.
    """
    from apps.platform.grouping_fields.queries import slot_map

    if dim in _RESERVED_ANALYTICS_DIMS:
        return "customer__external_id" if dim == "customer" else dim
    slot = slot_map(tenant.id).get(dim)
    if slot is None:
        raise Problem("validation_error", f"unknown grouping field {dim!r}")
    return slot


def _apply_task_filter(qs, tenant, task_id, include_subtasks):
    """Correlation-id filtering (design D9). With include_subtasks the whole
    tree is in scope — one extra indexed query for the child ids, since
    containment is a single level."""
    if task_id is None:
        return qs
    from apps.platform.work.models import Task

    ids = [task_id]
    if include_subtasks:
        ids += list(Task.objects.filter(
            tenant=tenant, parent_id=task_id).values_list("id", flat=True))
    return qs.filter(task_id__in=ids)


@metering_router.get("/analytics/usage", response={200: UsageAnalyticsResponse, 422: ProblemOut})
@role_floor(READ)
def usage_analytics(request, start_date: date = None, end_date: date = None,
                    customer_id: UUIDIdentifier = None, tag_key: str = None,
                    dimensions: list[str] = Query(None),
                    task_id: UUIDIdentifier = None, include_subtasks: bool = False,
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
    qs = Posting.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    qs = _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq)
    qs = _apply_task_filter(qs, tenant, task_id, include_subtasks)

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
    by_task_type = list(
        qs.exclude(task_type="").values("task_type").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )

    by_tag = []
    if tag_key:
        # SLICE 7 OWNS THIS SURFACE, and #273 left it exactly where it found
        # it: the keyed parameter, the response block and their spelling are
        # the analytics grouping vocabulary the ledger owns at slice 7, which
        # is what migrates the capability onto the declared grouping contract.
        # All that moved here is the column underneath, because the bag this
        # read folded into the survivor.
        by_tag = list(
            qs.filter(metadata__has_key=tag_key)
            .annotate(tag_value=KeyTextTransform(tag_key, "metadata"))
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
        if len(dimensions) > _MAX_BREAKDOWNS:
            raise Problem("validation_error",
                          f"at most {_MAX_BREAKDOWNS} dimensions")
        for dim in dimensions:
            col = _resolve_dimension(tenant, dim)
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
                # The same property the DECLARED margin rollup publishes for the
                # same thing (`GroupingFieldMarginRow.grouping_field_value`),
                # taken from the one constant its sibling timeseries rollup also
                # writes so the two cannot drift. These rows are `list[dict]`,
                # so no schema holds the name and no drift or breaking gate can
                # see it change — `test_analytics_dimensions.py` asserts the
                # whole row instead.
                r[GROUPED_VALUE_KEY] = raw_val
            breakdowns[dim] = rows

    return 200, {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": total_billed,
        "total_provider_cost_micros": total_provider,
        "usage_markup_margin_micros": total_billed - total_provider,
        "by_provider": by_provider,
        "by_event_type": by_event_type,
        "by_customer": by_customer,
        "by_task_type": by_task_type,
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
    resolved_group_by = None
    if group_by is not None:
        resolved_group_by = _resolve_dimension(request.auth.tenant, group_by)
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
        customer_id=customer_id, group_by=resolved_group_by, start_date=start_date, end_date=end_date)
    return 200, {"granularity": granularity, "group_by": group_by or "", "series": series}


# --- Rate Cards ---

_billing_check = ProductAccess("billing")


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
    return page(qs, cursor, limit, serialize=book_out)


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
    return 200, book_out(book)


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
    return 200, page(qs, cursor, limit, serialize=rate_out)


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
                measurement_key=payload.measurement_key, provider=payload.provider,
                event_type=payload.event_type, task_type=payload.task_type,
                subtask_type=payload.subtask_type,
                # Six published properties onto six of the ten columns (#276);
                # `SLOT_PROPERTY_COLUMNS` states why there are only six.
                **{column: getattr(payload, name)
                   for name, column in SLOT_PROPERTY_COLUMNS.items()},
                pricing_model=payload.pricing_model,
                rate_per_unit_micros=payload.rate_per_unit_micros,
                unit_quantity=payload.unit_quantity, fixed_micros=payload.fixed_micros,
                currency=book.currency,
                book_version_from=book.version)
            audit_record(
                action="rate.added",
                tenant_id=request.auth.tenant.id,
                resource_type="rate",
                resource_id=rate.id,
                # This key moved with the column (#275) and audit records
                # already written are NOT rewritten, on the same ground as the
                # pricing receipt: an audit row states what was done on a day,
                # and back-dating it to a vocabulary that did not exist then
                # would make it a worse record. Nothing queries this key — the
                # audit read path filters on `action` and `resource_type`, both
                # unchanged — so the split costs no reader a lookup.
                metadata={
                    "book_id": str(book.id),
                    "measurement_key": rate.measurement_key,
                    "pricing_model": rate.pricing_model,
                    "rate_per_unit_micros": rate.rate_per_unit_micros,
                    "currency": rate.currency,
                },
            )
    except IntegrityError:
        raise Problem("conflict", "a rate with this identity already exists")
    return 200, rate_out(rate)


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
        BookService.publish(book, [rate_change_body(c.dict(exclude_none=True))
                                   for c in payload.changes])
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
    return 200, book_out(book)


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


@metering_router.put("/grouping-fields",
                     response={200: DimensionRegistryOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("grouping_field.declared")
def declare_grouping_fields(request, payload: DimensionRegistryIn):
    """Declare this tenant's slicing axes — the ONE vocabulary used by both
    analytics grouping and rate selection (design D1). Idempotent: re-PUTting
    an identical declaration is a no-op. `slot` and `scope` are immutable once
    bound and `max_cardinality` may only be raised (D8)."""
    _product_check(request)
    from apps.platform.grouping_fields.queries import declared_dimensions
    from apps.platform.grouping_fields.services import DimensionError, DimensionService

    tenant = request.auth.tenant
    try:
        with transaction.atomic():
            for d in payload.dimensions:
                DimensionService.declare(tenant, key=d.key, slot=d.slot, scope=d.scope,
                                         max_cardinality=d.max_cardinality)
            audit_record(
                action="grouping_field.declared",
                tenant_id=tenant.id,
                resource_type="dimension_registry",
                resource_id=tenant.id,
                metadata={"dimensions": [
                    {"key": d.key, "slot": d.slot, "scope": d.scope,
                     "max_cardinality": d.max_cardinality}
                    for d in payload.dimensions]},
            )
    except DimensionError as exc:
        raise Problem("validation_error", str(exc))
    return 200, {"dimensions": declared_dimensions(tenant.id)}


@metering_router.get("/grouping-fields", response=DimensionRegistryOut)
@role_floor(READ)
def list_grouping_fields(request):
    """This tenant's declared Grouping Field vocabulary."""
    _product_check(request)
    from apps.platform.grouping_fields.queries import declared_dimensions
    return {"dimensions": declared_dimensions(request.auth.tenant.id)}


@metering_router.get("/grouping-fields/{key}/values",
                     response={200: GroupingFieldValuesOut, 404: ProblemOut})
@role_floor(READ)
def list_grouping_field_values(request, key: str):
    """Every value admitted for one Grouping Field — the read model a dashboard
    filter dropdown needs. Bounded by the key's max_cardinality (D4)."""
    _product_check(request)
    from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue

    if not GroupingField.objects.filter(tenant=request.auth.tenant, key=key).exists():
        raise Problem("not_found", f"{key!r} is not a declared grouping field")
    values = list(GroupingFieldValue.objects.filter(
        tenant=request.auth.tenant, key=key).order_by("value").values_list("value", flat=True))
    return 200, {"key": key, "values": values}


@metering_router.put("/task-types", response={200: TaskTypeRegistryOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("task_type.declared")
def declare_task_types(request, payload: TaskTypeRegistryIn):
    """Declare the tenant's work vocabulary and its per-kind COGS ceilings
    (design D7). Idempotent; the ceiling and required_dimensions may be updated
    on a re-PUT. Admin-floored: a task type's ceiling prices usage the same way
    markup.set/rate_card.* do, so it takes the write-default Admin floor rather
    than a Write carve-out."""
    _product_check(request)
    from apps.platform.grouping_fields.queries import slot_map
    from apps.platform.work.models import TaskType
    from apps.platform.work.queries import declared_task_types

    tenant = request.auth.tenant
    declared = set(slot_map(tenant.id))
    with transaction.atomic():
        for tt in payload.task_types:
            if tt.kind not in ("task", "subtask"):
                raise Problem("validation_error", f"invalid kind {tt.kind!r}")
            missing = [d for d in tt.required_dimensions if d not in declared]
            if missing:
                raise Problem("validation_error",
                              f"required_dimensions not declared: {missing}")
            TaskType.objects.update_or_create(
                tenant=tenant, key=tt.key, kind=tt.kind,
                defaults={
                    "default_provider_cost_limit_micros":
                        tt.default_provider_cost_limit_micros,
                    "required_dimensions": tt.required_dimensions,
                })
        audit_record(
            action="task_type.declared",
            tenant_id=tenant.id,
            resource_type="task_type_registry",
            resource_id=tenant.id,
            metadata={"task_types": [
                {"key": tt.key, "kind": tt.kind,
                 "default_provider_cost_limit_micros":
                     tt.default_provider_cost_limit_micros,
                 "required_dimensions": tt.required_dimensions}
                for tt in payload.task_types]},
        )
    return 200, {"task_types": declared_task_types(tenant.id)}


@metering_router.get("/task-types", response=TaskTypeRegistryOut)
@role_floor(READ)
def list_task_types(request):
    """The tenant's declared work vocabulary."""
    _product_check(request)
    from apps.platform.work.queries import declared_task_types
    return {"task_types": declared_task_types(request.auth.tenant.id)}
