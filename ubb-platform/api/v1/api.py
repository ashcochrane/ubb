"""The one versioned NinjaAPI (#77, ADR-002 Stage 1).

Twelve routers — eight composition-layer, four product-owned — mounted on a
single API served at ``/api/v1/``. Products expose ``Router`` objects; this
module (the composition layer) mounts them, so ADR-001's import matrix is
respected, not amended. Per-router ``auth=`` preserves the pre-restructure
split: tenant-key auth everywhere, widget JWT on ``/me``. Mount prefixes
reproduce the old per-mount external URLs byte-for-byte.

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
from api.v1.event_type_endpoints import event_type_router
from api.v1.me_endpoints import me_router
from api.v1.metering_endpoints import metering_router
from api.v1.plan_endpoints import plan_router
from api.v1.platform_endpoints import platform_router
from api.v1.sandbox_endpoints import sandbox_router
from api.v1.tenant_endpoints import tenant_router
from apps.platform.events.api.webhook_endpoints import webhook_router
from apps.platform.events.openapi import build_webhooks_section
from api.v1.problems import document_problem_media_type, install_problem_handlers
from apps.referrals.api.endpoints import referrals_router
from apps.subscriptions.api.endpoints import subscriptions_router
from apps.subscriptions.api.margin_endpoints import margin_router
from core.auth import ApiKeyAuth

class _ProblemDocumentingNinjaAPI(NinjaAPI):
    """The one schema seam (#104): the offline exporter and the runtime
    ``/api/v1/openapi.json`` both render through ``get_openapi_schema``, so
    correcting the error media type here keeps the committed document and
    the served one truthful — and identical — by construction.

    ONE THING IS DELIBERATELY NOT HERE, and it is the only place the two
    documents diverge. The known-value metadata (#208) is applied by
    ``api.v1.openapi_export`` after this seam, not inside it: it reads a
    generated JSON file at the git root, and a Django request path should not
    acquire that dependency — nor a ``sys.path`` entry — to serve a document
    ADR-002 says is not the contract. So the served schema carries the error
    dialect and the committed one carries the error dialect **and** the
    vocabulary metadata. ``openapi_export._apply_known_values`` carries the
    reasoning.

    THE DIVERGENCE IS NO LONGER EMPTY. Slice 1 (#240) marked the tenant's
    `products` field — the first ``x-ubb-concept`` in the committed contract —
    and confirmed this seam's judgement rather than overturning it: the applier
    stays out of the request path. What the two documents promise each other is
    stated by ``openapi_export.without_known_values`` and pinned by
    ``test_openapi_contract.py``, so "identical by construction" holds for
    everything except exactly what that function removes."""

    def get_openapi_schema(self, **kwargs):
        return document_problem_media_type(super().get_openapi_schema(**kwargs))


api = _ProblemDocumentingNinjaAPI(
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
api.add_router("me/", me_router)
api.add_router("tenant/", tenant_router)
api.add_router("sandbox/", sandbox_router)
api.add_router("metering/", metering_router)
api.add_router("billing/", billing_router)
api.add_router("subscriptions/", subscriptions_router)
api.add_router("margin/", margin_router)
api.add_router("referrals/", referrals_router)
# #86 sweep: de-stuttered from the legacy "webhooks/config/" mount (a pre-#77
# separately-mounted API) — the router's own /configs collection made the old
# external path /webhooks/config/configs. Now /api/v1/webhooks/configs.
api.add_router("webhooks/", webhook_router)
api.add_router("platform/", platform_router)
api.add_router("connect/", connect_router)
api.add_router("audit/", audit_router)
# Mounted at the root prefix, before root_router: their concrete paths
# (/plans, /customers/{external_id}/plan; /event-types, /providers,
# /event-categories) must bind before root_router's catch-alls, since
# django-ninja resolves routes in registration order.
#
# The Event Type catalogue is at the root for the reason plan_router is: it is
# a KERNEL concept several products read and none owns, so mounting it inside
# one product's prefix would say the opposite on the published contract —
# which ADR-0007 §3 then forbids correcting. api/v1/event_type_endpoints.py
# carries the argument.
api.add_router("", plan_router)
api.add_router("", event_type_router)
api.add_router("", root_router)
