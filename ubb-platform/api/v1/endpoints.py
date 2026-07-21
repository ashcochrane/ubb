from datetime import datetime, timezone as dt_timezone

import redis

from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from core.auth import ApiKeyAuth, ProductAccess
from core.responses import json_response

from api.v1.schemas import PastLimitReportResponse

root_router = Router(auth=ApiKeyAuth())

_metering_check = ProductAccess("metering")


@root_router.get("/health", auth=None)
def health(request):
    return {"status": "ok"}


@root_router.get("/customers/{customer_id}/past-limit-report",
         response=PastLimitReportResponse)
def past_limit_report(request, customer_id: str,
                      since: datetime = None, until: datetime = None):
    """The past-limit report (#41, spec §I): per-customer episodes — each
    with the tripping limit, tripped-at, resume time (if any), itemized
    events, and totals per limit in both denominations. Soft-floor episodes
    appear as crossed/cleared marker rows with no itemized events. since/
    until (ISO datetimes; naive = UTC) window episodes by tripped_at and
    itemized events by effective_at."""
    _metering_check(request)
    from apps.platform.customers.models import Customer
    from api.v1.past_limit import build_past_limit_report

    customer = get_object_or_404(
        Customer, id=customer_id, tenant=request.auth.tenant)
    if since is not None and timezone.is_naive(since):
        since = timezone.make_aware(since, dt_timezone.utc)
    if until is not None and timezone.is_naive(until):
        until = timezone.make_aware(until, dt_timezone.utc)
    return build_past_limit_report(request.auth.tenant, customer,
                                   since=since, until=until)


@root_router.get("/ready", auth=None)
def ready(request):
    checks = {}
    try:
        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        r = redis.from_url(settings.REDIS_URL)
        try:
            r.ping()
            checks["redis"] = "ok"
        finally:
            r.close()
    except Exception:
        checks["redis"] = "error"
    all_ok = all(v == "ok" for v in checks.values())
    return json_response(
        request,
        {"status": "ready" if all_ok else "not_ready", "checks": checks},
        status=200 if all_ok else 503,
    )
