"""Sandbox-only endpoints (F4.4).

Mounted at /api/v1/sandbox/. Callable ONLY with a sandbox (ubb_test_) key —
the reset wipes the calling tenant, so a live key must always 403.
"""
from ninja import Router, Schema

from core.auth import ApiKeyAuth
from core.problems import Problem, ProblemOut

sandbox_router = Router(auth=ApiKeyAuth())


class SandboxResetIn(Schema):
    keep_config: bool = True


@sandbox_router.post("/reset", response={202: dict, 403: ProblemOut})
def reset_sandbox(request, payload: SandboxResetIn = None):
    """Asynchronously wipe the calling SANDBOX tenant's domain data.

    keep_config=true (default) preserves rate cards, markups, plans, budget /
    billing / postpaid / webhook configs; the Tenant row and its API keys
    always survive. Returns 202 — the wipe runs as a Celery task and the
    sandbox 401s (deactivated) until it completes.
    """
    tenant = request.auth.tenant
    if not tenant.is_sandbox:
        raise Problem("forbidden",
                      "sandbox reset requires a sandbox (ubb_test_) API key")
    keep_config = payload.keep_config if payload is not None else True
    from apps.platform.tenants.tasks import reset_sandbox_tenant
    reset_sandbox_tenant.delay(str(tenant.id), keep_config)
    return 202, {"status": "accepted", "keep_config": keep_config}
