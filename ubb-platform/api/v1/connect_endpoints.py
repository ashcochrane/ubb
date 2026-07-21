from ninja import Router, Schema
from django.http import HttpResponseRedirect, JsonResponse

from core.auth import ADMIN, ApiKeyAuth, READ, role_floor
from core.problems import Problem, ProblemOut
from apps.billing.connectors.stripe import connect
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit

connect_router = Router(auth=ApiKeyAuth())


class ConnectStartIn(Schema):
    return_url: str = ""


@connect_router.post("/start", response={200: dict, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("connect.started")
def connect_start(request, payload: ConnectStartIn):
    try:
        url = connect.build_authorize_url(request.auth.tenant, return_url=payload.return_url)
    except connect.ConnectError as e:
        raise Problem("invalid_config", str(e))
    # Curated metadata only — never the built authorize URL or the OAuth ``state``
    # nonce (both secrets). The return_url is the caller-supplied redirect target.
    audit_record(
        action="connect.started", tenant_id=request.auth.tenant.id,
        resource_type="connect", resource_id=request.auth.tenant.id,
        metadata={"return_url": payload.return_url})
    return 200, {"authorize_url": url}


@connect_router.get("/status", response=dict)
@role_floor(READ)
def connect_status(request):
    import stripe
    from apps.billing.stripe.services.stripe_service import api_key_for_tenant
    t = request.auth.tenant
    if t.stripe_connected_account_id and not t.charges_enabled:
        try:
            acct = stripe.Account.retrieve(
                t.stripe_connected_account_id, api_key=api_key_for_tenant(t))
            new_val = bool(getattr(acct, "charges_enabled", False))
            if new_val != t.charges_enabled:
                t.charges_enabled = new_val
                t.save(update_fields=["charges_enabled", "updated_at"])
        except Exception:
            pass
    return {
        "account_id": t.stripe_connected_account_id,
        "charges_enabled": t.charges_enabled,
        "onboarded": bool(t.stripe_connected_account_id and t.charges_enabled),
    }


def connect_callback(request):
    """Plain Django view — NO auth (browser redirect from Stripe).

    Identified solely by the single-use ``state`` nonce. Looking up the row for
    its ``return_url`` is safe even for a used/expired state; only
    ``complete_oauth`` mutates and it re-checks single-use atomically. An unknown
    state -> ``st`` is None -> ``complete_oauth`` raises -> JsonResponse 400.
    Never a 500.
    """
    from apps.platform.tenants.models import ConnectOAuthState
    code = request.GET.get("code", "")
    state = request.GET.get("state", "")
    st = ConnectOAuthState.objects.filter(state=state).first()
    ok = False
    try:
        if code and state:
            connect.complete_oauth(code=code, state=state)
            ok = True
    except connect.ConnectError:
        ok = False
    return_url = st.return_url if st else ""
    if return_url:
        sep = "&" if "?" in return_url else "?"
        return HttpResponseRedirect(f"{return_url}{sep}connected={'true' if ok else 'false'}")
    return JsonResponse({"connected": ok}, status=200 if ok else 400)
