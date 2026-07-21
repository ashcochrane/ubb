"""The one versioned NinjaAPI (#77, ADR-002 Stage 1).

Twelve routers — eight composition-layer, four product-owned — mounted on a
single API served at ``/api/v1/``. Products expose ``Router`` objects; this
module (the composition layer) mounts them, so ADR-001's import matrix is
respected, not amended. Per-router ``auth=`` preserves the pre-restructure
split: tenant-key auth everywhere, widget JWT on ``/me``. Mount prefixes
reproduce the old per-mount external URLs byte-for-byte; ``url_name_prefix``
keeps Django URL names collision-free now that twelve URL namespaces have
collapsed into one.

``openapi/v1.json`` at the git root is generated offline from this object
(``scripts/export_openapi.py``) and checked in; CI's drift gate keeps code
and document identical. The OpenAPI 3.1 ``webhooks`` section — the event
catalog with frozen payload schemas — rides ``openapi_extra`` so it appears
in the committed document and the runtime ``/api/v1/openapi.json`` alike.
"""
from ninja import NinjaAPI

from api.v1.audit_endpoints import audit_router
from api.v1.billing_endpoints import billing_router
from api.v1.connect_endpoints import connect_router
from api.v1.endpoints import root_router
from api.v1.me_endpoints import me_router
from api.v1.metering_endpoints import metering_router
from api.v1.platform_endpoints import platform_router
from api.v1.sandbox_endpoints import sandbox_router
from api.v1.tenant_endpoints import tenant_router
from apps.platform.events.api.webhook_endpoints import webhook_router
from apps.platform.events.openapi import build_webhooks_section
from api.v1.problems import install_problem_handlers
from apps.referrals.api.endpoints import referrals_router
from apps.subscriptions.api.endpoints import subscriptions_router
from apps.subscriptions.api.margin_endpoints import margin_router
from core.auth import ApiKeyAuth

api = NinjaAPI(
    title="UBB API",
    version="v1",
    description=(
        "Usage, spend-control, and margin infrastructure in front of Stripe. "
        "The committed openapi/v1.json generated from this API is the single "
        "source of truth for the tenant surface (ADR-002)."
    ),
    urls_namespace="ubb_v1",
    auth=ApiKeyAuth(),
    openapi_extra={"webhooks": build_webhooks_section()},
)

# One error dialect (#78): every error from every route renders through the
# central problem+json handlers; no endpoint builds an error body by hand.
install_problem_handlers(api)

# Mount order preserves the old config/urls.py registration order (the /me
# widget surface before the generic mounts, the root router last).
api.add_router("me/", me_router, url_name_prefix="me")
api.add_router("tenant/", tenant_router, url_name_prefix="tenant")
api.add_router("sandbox/", sandbox_router, url_name_prefix="sandbox")
api.add_router("metering/", metering_router, url_name_prefix="metering")
api.add_router("billing/", billing_router, url_name_prefix="billing")
api.add_router("subscriptions/", subscriptions_router, url_name_prefix="subscriptions")
api.add_router("margin/", margin_router, url_name_prefix="margin")
api.add_router("referrals/", referrals_router, url_name_prefix="referrals")
api.add_router("webhooks/config/", webhook_router, url_name_prefix="webhooks")
api.add_router("platform/", platform_router, url_name_prefix="platform")
api.add_router("connect/", connect_router, url_name_prefix="connect")
api.add_router("audit/", audit_router, url_name_prefix="audit")
api.add_router("", root_router)
