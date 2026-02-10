import redis

from django.conf import settings
from django.db import connection
from ninja import NinjaAPI
from core.auth import ApiKeyAuth

api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_v1")


@api.get("/health", auth=None)
def health(request):
    return {"status": "ok"}


@api.get("/ready", auth=None)
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
    return api.create_response(
        request,
        {"status": "ready" if all_ok else "not_ready", "checks": checks},
        status=200 if all_ok else 503,
    )
