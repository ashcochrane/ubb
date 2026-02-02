from django.contrib import admin
from django.urls import path
from api.v1.endpoints import api
from api.v1.webhooks import stripe_webhook
from api.v1.widget_endpoints import widget_api

urlpatterns = [
    path("admin/", admin.site.urls),
    # Widget routes BEFORE generic api/v1/ to avoid shadowing
    path("api/v1/widget/", widget_api.urls),
    path("api/v1/webhooks/stripe", stripe_webhook),
    path("api/v1/", api.urls),
]
