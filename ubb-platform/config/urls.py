from django.contrib import admin
from django.urls import path
from api.v1.endpoints import api
from api.v1.webhooks import stripe_webhook
from api.v1.me_endpoints import me_api
from api.v1.tenant_endpoints import tenant_api
from api.v1.metering_endpoints import metering_api
from api.v1.billing_endpoints import billing_api
from apps.subscriptions.api.endpoints import subscriptions_api, subscriptions_stripe_webhook
from apps.referrals.api.endpoints import referrals_api
from apps.platform.events.api.webhook_endpoints import webhook_api
from api.v1.platform_endpoints import platform_api

urlpatterns = [
    path("admin/", admin.site.urls),
    # End-user routes BEFORE generic api/v1/ to avoid shadowing
    path("api/v1/me/", me_api.urls),
    path("api/v1/tenant/", tenant_api.urls),
    path("api/v1/metering/", metering_api.urls),
    path("api/v1/billing/", billing_api.urls),
    path("api/v1/subscriptions/webhooks/stripe", subscriptions_stripe_webhook),
    path("api/v1/subscriptions/", subscriptions_api.urls),
    path("api/v1/referrals/", referrals_api.urls),
    path("api/v1/webhooks/config/", webhook_api.urls),
    path("api/v1/platform/", platform_api.urls),
    path("api/v1/webhooks/stripe", stripe_webhook),
    path("api/v1/", api.urls),
]
