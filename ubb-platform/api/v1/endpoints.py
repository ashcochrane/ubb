from datetime import datetime, timezone as dt_timezone

import redis

from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from core.auth import ApiKeyAuth, ProductAccess, READ, role_floor
from core.identifiers import UUIDIdentifier
from core.problems import Problem
from core.responses import StatusResponse
from core.time_windows import REPORT_WINDOW_MAX_DAYS

from api.v1.schemas import PastLimitReportResponse, ReadyResponse

root_router = Router(auth=ApiKeyAuth())

_metering_check = ProductAccess("metering")


@root_router.get("/health", auth=None, response=StatusResponse)
def health(request):
    return {"status": "ok"}


@root_router.get("/customers/{customer_id}/past-limit-report",
         response=PastLimitReportResponse)
@role_floor(READ)
def past_limit_report(request, customer_id: UUIDIdentifier,
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
    # #78: computed reports are cursor-exempt but parameter-bounded.
    if since is not None and until is not None:
        if until < since:
            raise Problem("validation_error", "until must not precede since")
        if (until - since).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "window must not exceed 366 days")
    return build_past_limit_report(request.auth.tenant, customer,
                                   since=since, until=until)


@root_router.get("/ready", auth=None, response=ReadyResponse)
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
    if not all_ok:
        # #78: the failing readiness answer is an error and speaks the one
        # dialect; the per-dependency detail rides as an extension member.
        raise Problem("service_unavailable", "one or more dependencies failing",
                      extensions={"checks": checks})
    return {"status": "ready", "checks": checks}
