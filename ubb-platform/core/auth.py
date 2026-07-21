from django.core.cache import cache
from django.utils import timezone
from ninja.security import HttpBearer

from apps.platform.membership.roles import role_satisfies
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
            return key_obj

        # Not an API key — try the Clerk member-token scheme. Inert (returns
        # None for every token) when Clerk is unconfigured.
        claims = verify_member_token(token)
        if claims is not None:
            member = resolve_member_for_claims(claims)
            if member is not None:
                request.tenant = member.tenant
                request.sandbox = member.tenant.is_sandbox
                return member
        return None


def require_role(request, floor):
    """Enforce a role floor on the authenticated tenant principal.

    ``request.auth`` is a Member or a TenantApiKey — both carry ``.role``. A key
    is Admin by default (and every pre-existing key migrated to Admin), so key
    traffic satisfies every floor; a member is bound by its invited role. Below
    the floor is a 403 ``forbidden``. This is the seam identity build 2 will
    apply across the wider tenant surface; here only invitation routes (Admin)
    and the members list (Read) bind a floor.
    """
    role = getattr(request.auth, "role", None)
    if not role_satisfies(role, floor):
        raise Problem("forbidden", f"this operation requires the {floor!r} role")


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
