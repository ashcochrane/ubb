from django.contrib import admin
from django.urls import path

from api.v1.api import api
from api.v1.connect_endpoints import connect_callback
from api.v1.webhooks import stripe_webhook, stripe_webhook_test
from apps.subscriptions.api.endpoints import (
    subscriptions_stripe_webhook,
    subscriptions_stripe_webhook_test,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # Machine-facing infrastructure stays out of the versioned contract
    # (plain views, registered before the API mount): the four inbound
    # Stripe receivers and the Connect browser callback.
    path("api/v1/subscriptions/webhooks/stripe", subscriptions_stripe_webhook),
    path("api/v1/subscriptions/webhooks/stripe/test", subscriptions_stripe_webhook_test),
    path("api/v1/webhooks/stripe", stripe_webhook),
    path("api/v1/webhooks/stripe/test", stripe_webhook_test),
    path("api/v1/connect/callback", connect_callback),
    # The one versioned API (#77): twelve routers on a single NinjaAPI.
    path("api/v1/", api.urls),
]
