import redis

from django.conf import settings
from django.db import connection
from ninja import Router
from core.auth import ApiKeyAuth
from core.problems import Problem
from core.responses import StatusResponse

from api.v1.schemas import ReadyResponse

root_router = Router(auth=ApiKeyAuth())

# The per-customer report that lived beside these two probes retired in #466
# (slice 6 §14): its successor is Stops and breaches at
# `/api/v1/spend-controls/` (`api/v1/spend_control_endpoints.py`), typed and
# for every tenant. Only the two health probes remain on this router.


@root_router.get("/health", auth=None, response=StatusResponse)
def health(request):
    return {"status": "ok"}


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
