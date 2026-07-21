import functools

from django.core.cache import cache
from django.utils import timezone
from ninja.security import HttpBearer

# Re-exported so composition-layer routers — including the product-owned
# apps/<product>/api modules, which may NOT import api.* (ADR-001) — reach the
# floor helper and the role vocabulary from one place: `from core.auth import
# role_floor, READ, WRITE, ADMIN`.
from apps.platform.membership.roles import (  # noqa: F401
    ADMIN,
    READ,
    VALID_ROLES,
    WRITE,
    role_satisfies,
)
from apps.platform.audit.actors import (
    api_key_actor,
    member_actor,
    set_current_actor,
)
from apps.platform.membership.services import resolve_member_for_claims
from apps.platform.tenants.models import TenantApiKey
from core.clerk_auth import verify_member_token
from core.problems import Problem


class ApiKeyAuth(HttpBearer):
    """The tenant-principal bearer scheme (identity build 1, #79).

    One ``Authorization: Bearer <token>`` header carries either of the two
    tenant-principal credentials, distinguished by the token itself — never by a
    second header or security scheme, so the OpenAPI security of every existing
    route is unchanged:

      1. a **tenant API key** (``ubb_live_``/``ubb_test_``) — resolved first, the
         hot path for machine traffic; or
      2. a **Clerk member token** — a Clerk session JWT, verified server-side.
         First login activates the invited Member (matched by email) before the
         request proceeds.

    Either way the returned principal exposes ``.tenant`` and ``.role``, and the
    request carries ``request.tenant`` / ``request.sandbox`` exactly as before.
    An end-customer widget token is neither, so it can never authenticate a
    tenant route. When Clerk is unconfigured, path 2 is inert and behaviour is
    byte-for-byte API-key-only.
    """

    def authenticate(self, request, token):
        key_obj = TenantApiKey.verify_key(token)
        if key_obj is not None:
            request.tenant = key_obj.tenant
            # F4.4: ubb_test_ keys live on sandbox tenants, so the tenant row IS
            # the mode. Exposed for handlers that want a cheap mode check.
            request.sandbox = key_obj.tenant.is_sandbox
            # Buffer last_used_at in Redis — flushed to DB by periodic task
            cache.set(f"apikey_used:{key_obj.pk}", timezone.now().isoformat(), timeout=3600)
            # Capture the acting principal once, here, for the audit ledger
            # (ADR-004 §4). record() reads it — mutation sites never pass "who".
            set_current_actor(api_key_actor(key_obj.id, key_obj.label))
            return key_obj

        # Not an API key — try the Clerk member-token scheme. Inert (returns
        # None for every token) when Clerk is unconfigured.
        claims = verify_member_token(token)
        if claims is not None:
            member = resolve_member_for_claims(claims)
            if member is not None:
                request.tenant = member.tenant
                request.sandbox = member.tenant.is_sandbox
                set_current_actor(member_actor(member.id, member.email))
                return member
        return None


def require_role(request, floor):
    """Enforce a role floor on the authenticated tenant principal.

    ``request.auth`` is a Member or a TenantApiKey — both carry ``.role``. A key
    is Admin by default (and every pre-existing key migrated to Admin), so key
    traffic satisfies every floor; a member is bound by its invited role. Below
    the floor is a 403 ``forbidden``.
    """
    role = getattr(request.auth, "role", None)
    if not role_satisfies(role, floor):
        raise Problem("forbidden", f"this operation requires the {floor!r} role")


def role_floor(floor):
    """Declare and enforce a tenant route's minimum role (identity build 2, #80).

    The composition layer's one seam for the #74 carve table. Applied to every
    tenant-principal route, it does two things:

      * **Enforces** the floor at call time (``require_role`` → 403 ``forbidden``
        problem+json when the principal is below it). ``request.auth`` is already
        the resolved Member / TenantApiKey by the time the handler runs, so the
        check reads the principal's ``.role`` directly.
      * **Records** the floor on the view (``_role_floor``) so the carve-table
        walker (``test_role_floors.py``) can prove every route's floor matches
        #74 — a route added without a floor, or with the wrong one, fails CI.

    Enforcement lives here in the composition layer's auth module, never in a
    product: a product's ``api/`` router imports only this helper and the role
    constants from ``core`` (ADR-001 — products never consume membership
    directly). ``functools.wraps`` preserves the handler's signature, so Ninja's
    parameter parsing, ``operationId``, and docstring-derived OpenAPI summary are
    untouched — floors are runtime behaviour, invisible to the committed spec.

    The floor decorator goes *below* the route decorator::

        @tenant_router.get("/config", response=TenantConfigOut)
        @role_floor(READ)
        def get_tenant_config(request): ...
    """
    if floor not in VALID_ROLES:
        raise ValueError(f"unknown role floor {floor!r}")

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            require_role(request, floor)
            return view_func(request, *args, **kwargs)

        wrapper._role_floor = floor
        return wrapper

    return decorator


class ProductAccess:
    """Dependency that checks tenant has access to a specific product."""

    def __init__(self, required_product):
        self.required_product = required_product

    def __call__(self, request):
        if self.required_product not in request.tenant.products:
            raise Problem(
                "feature_not_enabled",
                f"Tenant does not have access to {self.required_product}",
            )
