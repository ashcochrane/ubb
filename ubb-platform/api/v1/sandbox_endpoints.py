"""Sandbox-only endpoints (F4.4).

Mounted at /api/v1/sandbox/. Callable ONLY with a sandbox (ubb_test_) key —
the reset wipes the calling tenant, so a live key must always 403.
"""
from ninja import Router, Schema

from apps.platform.audit.actors import get_current_actor
from apps.platform.audit.marker import records_audit
from core.auth import ADMIN, ApiKeyAuth, role_floor
from core.problems import Problem, ProblemOut

sandbox_router = Router(auth=ApiKeyAuth())


class SandboxResetIn(Schema):
    keep_config: bool = True


@sandbox_router.post("/reset", response={202: dict, 403: ProblemOut})
@role_floor(ADMIN)
@records_audit("sandbox.reset")
def reset_sandbox(request, payload: SandboxResetIn = None):
    """Asynchronously wipe the calling SANDBOX tenant's domain data.

    keep_config=true (default) preserves rate cards, markups, plans, budget /
    billing / postpaid / webhook configs; the Tenant row and its API keys
    always survive. Returns 202 — the wipe runs as a Celery task and the
    sandbox 401s (deactivated) until it completes.

    The wipe clears the sandbox's own audit entries and records this reset as
    the first entry of the fresh history (ADR-004). The reset is async, so the
    acting principal — captured at the auth seam — is threaded to the task by
    value; ``record()`` in a worker has no request-scoped actor to read.
    """
    tenant = request.auth.tenant
    if not tenant.is_sandbox:
        raise Problem("forbidden",
                      "sandbox reset requires a sandbox (ubb_test_) API key")
    keep_config = payload.keep_config if payload is not None else True
    actor = get_current_actor()
    from apps.platform.tenants.tasks import reset_sandbox_tenant
    reset_sandbox_tenant.delay(
        str(tenant.id), keep_config,
        actor_kind=(actor.kind if actor else ""),
        actor_id=(actor.id if actor else ""),
        actor_display=(actor.display if actor else ""))
    return 202, {"status": "accepted", "keep_config": keep_config}
